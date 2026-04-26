"""
CredentialStore: persistencia encriptada de claves de broker por usuario.

Diseño:
    - Una fila por (user_id, provider). Provider típicamente "alpaca".
    - api_key y api_secret cifrados independientemente con Vault.
    - Versionado de schema de cifrado (encryption_version) para soportar
      migraciones a futuro sin romper rows viejas.
    - get/set/delete son idempotentes y atómicos por fila.

Este módulo NO toca Postgres directo — recibe un get_conn callable.
Eso desacopla y facilita tests con mocks / SQLite in-memory.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from borsenhirn.security.vault import Vault, VaultError

logger = logging.getLogger(__name__)


@dataclass
class UserCredentials:
    """Plaintext credentials de un usuario para un provider."""
    user_id: str
    provider: str
    api_key: str
    api_secret: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    encryption_version: int = 1


class CredentialStore:
    """
    CRUD encriptado de credenciales de broker.

    El plaintext NUNCA se persiste — solo bytes cifrados. El plaintext
    solo aparece en memoria durante set() y get().

    Uso:
        vault = Vault.from_env("BORSENHIRN_MASTER_KEY")
        store = CredentialStore(get_conn, vault)

        store.set("user-uuid", "alpaca", "PK...", "secret...")
        creds = store.get("user-uuid", "alpaca")
        # creds.api_key, creds.api_secret en plaintext
    """

    DEFAULT_PROVIDER = "alpaca"

    def __init__(
        self,
        get_conn: Callable[[], Any],
        vault: Vault,
    ) -> None:
        self.get_conn = get_conn
        self.vault = vault

    # ── set ───────────────────────────────────────────────

    def set(
        self,
        user_id: str,
        provider: str,
        api_key: str,
        api_secret: str,
    ) -> None:
        """
        Inserta o actualiza credenciales para (user_id, provider).
        Idempotente.
        """
        if not user_id or not provider:
            raise ValueError("user_id y provider son requeridos")
        if not api_key or not api_secret:
            raise ValueError("api_key y api_secret no pueden ser vacíos")

        key_ct = self.vault.encrypt(api_key)
        sec_ct = self.vault.encrypt(api_secret)

        sql = """
            INSERT INTO user_credentials
                (user_id, provider, api_key_ciphertext, api_secret_ciphertext,
                 encryption_version, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, now(), now())
            ON CONFLICT (user_id, provider) DO UPDATE SET
                api_key_ciphertext = EXCLUDED.api_key_ciphertext,
                api_secret_ciphertext = EXCLUDED.api_secret_ciphertext,
                encryption_version = EXCLUDED.encryption_version,
                updated_at = now()
        """
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    user_id, provider,
                    key_ct, sec_ct,
                    self.vault.CURRENT_VERSION,
                ))
            conn.commit()
            logger.info("Credentials set for user=%s provider=%s",
                        user_id, provider)
        except Exception as exc:
            conn.rollback()
            logger.error("CredentialStore.set falló: %s", exc)
            raise

    # ── get ───────────────────────────────────────────────

    def get(
        self,
        user_id: str,
        provider: str = DEFAULT_PROVIDER,
    ) -> Optional[UserCredentials]:
        """
        Devuelve plaintext credentials o None si no existen.

        Si el ciphertext está corrupto o la master key es incorrecta,
        lanza VaultError (NO devuelve None — eso ocultaría el problema).
        """
        sql = """
            SELECT user_id, provider, api_key_ciphertext, api_secret_ciphertext,
                   encryption_version, created_at, updated_at
              FROM user_credentials
             WHERE user_id = %s AND provider = %s
        """
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (user_id, provider))
                row = cur.fetchone()
        except Exception as exc:
            logger.error("CredentialStore.get falló: %s", exc)
            raise

        if not row:
            return None

        (uid, prov, key_ct, sec_ct, ver, created, updated) = row
        # Soporte para futuras versiones
        if ver != self.vault.CURRENT_VERSION:
            logger.warning(
                "Credentials user=%s usan encryption_version=%d, "
                "Vault.CURRENT_VERSION=%d. Considera rotar.",
                user_id, ver, self.vault.CURRENT_VERSION,
            )

        api_key = self.vault.decrypt(bytes(key_ct))
        api_secret = self.vault.decrypt(bytes(sec_ct))
        return UserCredentials(
            user_id=str(uid),
            provider=prov,
            api_key=api_key,
            api_secret=api_secret,
            created_at=str(created) if created else None,
            updated_at=str(updated) if updated else None,
            encryption_version=ver,
        )

    # ── delete ────────────────────────────────────────────

    def delete(self, user_id: str, provider: str = DEFAULT_PROVIDER) -> bool:
        """Devuelve True si borró algo, False si no existía."""
        sql = "DELETE FROM user_credentials WHERE user_id = %s AND provider = %s"
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (user_id, provider))
                deleted = cur.rowcount
            conn.commit()
            if deleted:
                logger.info("Credentials borradas user=%s provider=%s",
                            user_id, provider)
            return deleted > 0
        except Exception as exc:
            conn.rollback()
            logger.error("CredentialStore.delete falló: %s", exc)
            raise

    # ── list ──────────────────────────────────────────────

    def list_users(self, provider: Optional[str] = None) -> List[str]:
        """Devuelve solo los user_id (NO desencripta nada)."""
        if provider:
            sql = "SELECT DISTINCT user_id FROM user_credentials WHERE provider = %s ORDER BY user_id"
            params: tuple = (provider,)
        else:
            sql = "SELECT DISTINCT user_id FROM user_credentials ORDER BY user_id"
            params = ()
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return [str(r[0]) for r in cur.fetchall()]
        except Exception as exc:
            logger.error("CredentialStore.list_users falló: %s", exc)
            raise

    # ── iterate (para rotación) ───────────────────────────

    def iter_all_ciphertexts(self):
        """
        Generator que produce (user_id, provider, key_ct, secret_ct).
        Diseñado para rotación de master key — NO desencripta.
        """
        sql = """
            SELECT user_id, provider, api_key_ciphertext, api_secret_ciphertext
              FROM user_credentials
             ORDER BY user_id, provider
        """
        conn = self.get_conn()
        with conn.cursor() as cur:
            cur.execute(sql)
            for row in cur.fetchall():
                yield (str(row[0]), row[1], bytes(row[2]), bytes(row[3]))

    def replace_ciphertexts(
        self,
        user_id: str,
        provider: str,
        new_key_ct: bytes,
        new_secret_ct: bytes,
    ) -> None:
        """
        Reemplaza solo los ciphertexts (sin desencripar). Usado por
        scripts/rotate_master_key.py.
        """
        sql = """
            UPDATE user_credentials
               SET api_key_ciphertext = %s,
                   api_secret_ciphertext = %s,
                   encryption_version = %s,
                   updated_at = now()
             WHERE user_id = %s AND provider = %s
        """
        conn = self.get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(sql, (
                    new_key_ct, new_secret_ct,
                    self.vault.CURRENT_VERSION,
                    user_id, provider,
                ))
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.error("replace_ciphertexts falló: %s", exc)
            raise
