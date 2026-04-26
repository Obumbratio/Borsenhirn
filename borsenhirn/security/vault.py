"""
Vault: encryption at rest sobre cryptography.fernet (AES-128-CBC + HMAC-SHA256).

Diseño
------
- Master key: 32 bytes random base64-urlsafe. Se guarda EN UN LUGAR DISTINTO
  a la base de datos (env var, AWS Secrets Manager, Doppler, HashiCorp Vault).
  NUNCA en Postgres ni en el repo.
- Cada llamada a encrypt() produce un ciphertext distinto (Fernet incluye un
  IV aleatorio + timestamp). Esto es deliberado: no permite distinguir si
  dos usuarios tienen la misma API key, y dificulta análisis de tráfico.
- Cada ciphertext incluye HMAC-SHA256 — si alguien lo modifica en la DB,
  decrypt() lanza VaultError. Tamper-evident.
- Soporta key rotation: con dos vaults (old + new), iterás todas las filas,
  decrypt(old) → encrypt(new), reemplazás el ciphertext. Atomic per row.
- Opcional: derivar master key de una passphrase con PBKDF2-SHA256
  (310,000 iters, configurable). Útil para desarrollo donde no querés
  manejar 32 bytes random.

Anti-patterns que evita
-----------------------
- Nunca usa AES en modo ECB.
- Nunca usa keys derivadas con MD5/SHA1.
- Nunca devuelve plaintext en logs.
- Nunca cifra con claves cortas (<256 bits de entropía efectiva).
- Decrypt valida HMAC ANTES de devolver plaintext (mitiga padding oracle).
"""

from __future__ import annotations

import base64
import logging
import os
import secrets
from typing import Optional, Union

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


class VaultError(Exception):
    """Cualquier fallo de cifrado/descifrado/validación."""


# ── Helpers de generación de claves ─────────────────────────


def generate_master_key() -> str:
    """
    Genera una master key Fernet válida (32 bytes base64-urlsafe).
    Devuelve string para que sea fácil pegar en .env.

    Uso típico:
        python -c "from borsenhirn.security import generate_master_key; \
                   print(generate_master_key())"
        # → guardás el output en BORSENHIRN_MASTER_KEY=<aquí>
    """
    return Fernet.generate_key().decode("ascii")


def derive_key_from_passphrase(
    passphrase: Union[str, bytes],
    salt: Union[str, bytes],
    iterations: int = 310_000,
) -> str:
    """
    Deriva una Fernet key (32 bytes) desde una passphrase + salt usando
    PBKDF2-SHA256. Para desarrollo / testing — en producción preferí
    `generate_master_key()` y guardar el output en un secrets manager.

    El salt debe ser estable (sino no podés decrypt) y diferente por
    ambiente. Mínimo 16 bytes recomendado.

    Args:
        passphrase: la passphrase del operador.
        salt: bytes/string que sirve de salt. Si pasás un string, se
              UTF-8 encoded.
        iterations: PBKDF2 iterations. Default 310k (OWASP 2024).

    Returns:
        Fernet key como string base64-urlsafe.
    """
    if isinstance(passphrase, str):
        passphrase = passphrase.encode("utf-8")
    if isinstance(salt, str):
        salt = salt.encode("utf-8")
    if len(salt) < 8:
        raise VaultError("salt debe ser al menos 8 bytes")
    if iterations < 100_000:
        raise VaultError("iterations debe ser >= 100_000 (OWASP recommendation)")

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=iterations,
    )
    raw = kdf.derive(passphrase)
    return base64.urlsafe_b64encode(raw).decode("ascii")


# ── Vault principal ─────────────────────────────────────────


class Vault:
    """
    Symmetric encryption at rest para secretos de usuario.

    Uso:
        vault = Vault.from_env("BORSENHIRN_MASTER_KEY")
        # o
        vault = Vault(master_key=generate_master_key())

        ciphertext = vault.encrypt("mi-alpaca-secret-key")
        plaintext = vault.decrypt(ciphertext)
        assert plaintext == "mi-alpaca-secret-key"

    Thread-safe: Fernet internamente usa primitivas thread-safe.
    """

    # Versión del esquema de cifrado. Si cambiamos el algoritmo en el
    # futuro, esto permite migración gradual.
    CURRENT_VERSION = 1

    def __init__(self, master_key: Union[str, bytes]) -> None:
        if not master_key:
            raise VaultError("master_key vacío")
        if isinstance(master_key, str):
            master_key = master_key.encode("ascii")
        try:
            self._fernet = Fernet(master_key)
        except (ValueError, TypeError) as exc:
            raise VaultError(
                f"master_key inválida (debe ser 32 bytes base64-urlsafe): {exc}"
            ) from exc

    @classmethod
    def from_env(cls, env_var: str = "BORSENHIRN_MASTER_KEY") -> "Vault":
        """Construye un Vault leyendo la master key desde una env var."""
        key = os.environ.get(env_var)
        if not key:
            raise VaultError(
                f"env var {env_var} no está seteada. "
                f"Generá una con generate_master_key() y agregala a tu .env."
            )
        return cls(key)

    # ── Operaciones core ──────────────────────────────────

    def encrypt(self, plaintext: Union[str, bytes]) -> bytes:
        """
        Cifra plaintext y devuelve bytes (apto para columna bytea de Postgres).

        El output incluye IV aleatorio + HMAC, así que dos llamadas con el
        mismo input devuelven outputs distintos.
        """
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
        if not isinstance(plaintext, (bytes, bytearray)):
            raise VaultError(f"plaintext debe ser str o bytes, got {type(plaintext)}")
        if len(plaintext) == 0:
            raise VaultError("no se cifra plaintext vacío (probablemente bug)")
        return self._fernet.encrypt(bytes(plaintext))

    def decrypt(self, ciphertext: Union[str, bytes]) -> str:
        """
        Descifra ciphertext y devuelve string UTF-8.

        Valida HMAC antes de devolver — si el ciphertext fue modificado en la
        DB o la master key es incorrecta, lanza VaultError. NO se loggea el
        plaintext jamás (ni siquiera en error).
        """
        if isinstance(ciphertext, str):
            ciphertext = ciphertext.encode("ascii")
        if not isinstance(ciphertext, (bytes, bytearray)):
            raise VaultError(f"ciphertext debe ser bytes, got {type(ciphertext)}")
        try:
            decrypted = self._fernet.decrypt(bytes(ciphertext))
        except InvalidToken as exc:
            # InvalidToken = HMAC fail O master key wrong O token expirado
            raise VaultError(
                "decrypt fallido: token inválido (master key incorrecta, "
                "ciphertext corrupto, o token tampered)"
            ) from exc
        try:
            return decrypted.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VaultError(
                "decrypt fallido: bytes resultantes no son UTF-8"
            ) from exc

    # ── Helpers de rotación ───────────────────────────────

    def rotate(self, old_ciphertext: bytes, new_vault: "Vault") -> bytes:
        """
        Reencripta `old_ciphertext` (cifrado con esta vault) usando otra vault.

        Útil para rotar master key sin downtime:
            old_vault = Vault.from_env("OLD_MASTER")
            new_vault = Vault.from_env("NEW_MASTER")
            for row in db.iter_credentials():
                new_ct = old_vault.rotate(row.ciphertext, new_vault)
                db.update_ciphertext(row.id, new_ct)
        """
        plaintext = self.decrypt(old_ciphertext)
        return new_vault.encrypt(plaintext)

    def reencrypt(self, ciphertext: bytes) -> bytes:
        """
        Reencripta con la misma key (genera nuevo IV).

        Útil después de rotación periódica si querés que ningún ciphertext
        viejo en backups quede igual al actual (defensa en profundidad).
        """
        return self.rotate(ciphertext, self)

    # ── Validación rápida (no decrypt completo) ────────────

    def can_decrypt(self, ciphertext: bytes) -> bool:
        """True si esta vault puede decrypt — útil para detectar drift."""
        try:
            self.decrypt(ciphertext)
            return True
        except VaultError:
            return False
