"""
Rota la master key del Vault sin downtime.

Estrategia:
    1. Genera o lee NUEVA master key (env var BORSENHIRN_NEW_MASTER_KEY).
    2. Lee la VIEJA master key (BORSENHIRN_MASTER_KEY).
    3. Itera todas las filas de user_credentials.
    4. Por cada fila: descripta con vieja + reencripta con nueva, UPDATE
       atómico de la fila, marca rotated_at.
    5. Reporta progreso + total.

DESPUÉS de correr este script:
    - Mover BORSENHIRN_NEW_MASTER_KEY → BORSENHIRN_MASTER_KEY en .env
    - Reiniciar el bot/api.
    - Confirmar con un get() que las credenciales abren bien.
    - Solo entonces destruir la vieja master key.

Uso:
    # 1. Generar nueva master
    NEW_KEY=$(python -c "from borsenhirn.security import generate_master_key; print(generate_master_key())")
    export BORSENHIRN_NEW_MASTER_KEY="$NEW_KEY"

    # 2. Correr rotación (dry-run primero)
    python scripts/rotate_master_key.py --dry-run
    python scripts/rotate_master_key.py --confirm

    # 3. Validar
    python scripts/vault_demo.py

    # 4. Promover en .env (mover NEW_MASTER_KEY a MASTER_KEY)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402
from logger import setup_logging  # noqa: E402
from borsenhirn.security import (  # noqa: E402
    CredentialStore,
    Vault,
    VaultError,
)

setup_logging()
logger = logging.getLogger(__name__)


def get_db_conn():
    """Helper que abre una conexión psycopg2 nueva."""
    import psycopg2
    return psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        dbname=config.DB_NAME, user=config.DB_USER,
        password=config.DB_PASSWORD,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="no escribe nada — solo cuenta filas y verifica decrypt")
    p.add_argument("--confirm", action="store_true",
                   help="ejecuta la rotación de verdad")
    p.add_argument("--old-env", default="BORSENHIRN_MASTER_KEY")
    p.add_argument("--new-env", default="BORSENHIRN_NEW_MASTER_KEY")
    args = p.parse_args()

    if not args.dry_run and not args.confirm:
        print("ERROR: pasá --dry-run o --confirm. Refusing to operate ambiguously.")
        sys.exit(2)

    old_key = os.environ.get(args.old_env)
    new_key = os.environ.get(args.new_env)
    if not old_key or not new_key:
        print(f"ERROR: necesito ambos env vars: {args.old_env} y {args.new_env}")
        sys.exit(2)
    if old_key == new_key:
        print("ERROR: old y new key son iguales — no rotation possible")
        sys.exit(2)

    try:
        old_vault = Vault(old_key)
        new_vault = Vault(new_key)
    except VaultError as exc:
        print(f"ERROR: master key inválida: {exc}")
        sys.exit(2)

    conn = get_db_conn()
    old_store = CredentialStore(lambda: conn, old_vault)
    new_store = CredentialStore(lambda: conn, new_vault)

    total = 0
    success = 0
    failed = 0
    failures = []

    for (user_id, provider, key_ct, sec_ct) in old_store.iter_all_ciphertexts():
        total += 1
        try:
            key_pt = old_vault.decrypt(key_ct)
            sec_pt = old_vault.decrypt(sec_ct)
        except VaultError as exc:
            logger.error("Fila user=%s provider=%s no decrypt con old key: %s",
                         user_id, provider, exc)
            failed += 1
            failures.append((user_id, provider, str(exc)))
            continue

        if args.dry_run:
            logger.info("[DRY] would rotate user=%s provider=%s", user_id, provider)
            success += 1
            continue

        try:
            new_key_ct = new_vault.encrypt(key_pt)
            new_sec_ct = new_vault.encrypt(sec_pt)
            new_store.replace_ciphertexts(user_id, provider,
                                            new_key_ct, new_sec_ct)
            # Marcar rotated_at
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE user_credentials SET rotated_at=now() "
                    "WHERE user_id=%s AND provider=%s",
                    (user_id, provider),
                )
            conn.commit()
            success += 1
            logger.info("Rotated user=%s provider=%s", user_id, provider)
        except Exception as exc:
            conn.rollback()
            logger.error("Fila user=%s provider=%s falló al reencriptar: %s",
                         user_id, provider, exc)
            failed += 1
            failures.append((user_id, provider, str(exc)))

    conn.close()

    bar = "=" * 64
    mode = "DRY RUN" if args.dry_run else "EXECUTED"
    print(f"\n{bar}\n  ROTACIÓN ({mode})\n{bar}")
    print(f"  Total filas:  {total}")
    print(f"  Success:      {success}")
    print(f"  Failed:       {failed}")
    if failures:
        print("\n  Failures:")
        for uid, prov, err in failures:
            print(f"    user={uid} provider={prov}")
            print(f"      → {err}")
    print(bar)

    if not args.dry_run and success > 0 and failed == 0:
        print("\n  Próximo paso:")
        print("  1. Verificar con: BORSENHIRN_MASTER_KEY=$BORSENHIRN_NEW_MASTER_KEY \\")
        print("                    python scripts/vault_demo.py")
        print("  2. Mover NEW_MASTER_KEY → MASTER_KEY en .env")
        print("  3. Reiniciar bot/api")
        print("  4. Solo entonces destruir la vieja master key")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
