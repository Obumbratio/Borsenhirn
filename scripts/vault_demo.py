"""
Smoke test + demo del módulo borsenhirn.security.

Cubre:
    - Generar master key.
    - Encrypt / decrypt roundtrip.
    - Detección de tampering.
    - Detección de master key incorrecta.
    - Derivación desde passphrase (PBKDF2).
    - (Opcional) Test contra Postgres si hay BORSENHIRN_TEST_DB=1.

Uso:
    python scripts/vault_demo.py
    BORSENHIRN_TEST_DB=1 python scripts/vault_demo.py    # incluye DB
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from borsenhirn.security import (
    Vault,
    VaultError,
    derive_key_from_passphrase,
    generate_master_key,
)

SEP = "=" * 64


def section(title: str) -> None:
    print(f"\n{SEP}\n  {title}\n{SEP}")


def test_basic_roundtrip() -> bool:
    section("[1] Encrypt / decrypt roundtrip")
    key = generate_master_key()
    print(f"  master_key generada: {key[:8]}... (len={len(key)})")
    v = Vault(key)

    plaintexts = [
        "PKABCDEF1234567890",
        "secret-with-symbols-!@#$%^&*()",
        "español: ñ ó á é í ú",
        "x" * 500,
    ]
    for pt in plaintexts:
        ct = v.encrypt(pt)
        roundtripped = v.decrypt(ct)
        assert roundtripped == pt, f"FAIL: roundtrip distinto para {pt[:20]!r}"
        print(f"  OK roundtrip ({len(pt):>4} chars → {len(ct)} bytes ciphertext)")

    # Cada encrypt produce ciphertext distinto (IV aleatorio)
    ct1 = v.encrypt("misma cosa")
    ct2 = v.encrypt("misma cosa")
    assert ct1 != ct2, "FAIL: dos encrypts del mismo plaintext fueron iguales"
    assert v.decrypt(ct1) == v.decrypt(ct2) == "misma cosa"
    print("  OK no-determinismo (mismo plaintext → ciphertexts distintos)")
    return True


def test_tamper_detection() -> bool:
    section("[2] Tamper detection")
    v = Vault(generate_master_key())
    ct = v.encrypt("super secreto")

    # Modificar 1 byte del ciphertext
    tampered = bytearray(ct)
    tampered[10] ^= 0x01
    try:
        v.decrypt(bytes(tampered))
        print("  FAIL: tampered ciphertext debería haber lanzado VaultError")
        return False
    except VaultError as e:
        print(f"  OK tampering detectado: {str(e)[:80]}")
    return True


def test_wrong_master_key() -> bool:
    section("[3] Wrong master key rejected")
    v_a = Vault(generate_master_key())
    v_b = Vault(generate_master_key())
    ct = v_a.encrypt("only A can read this")
    try:
        v_b.decrypt(ct)
        print("  FAIL: vault B no debería poder leer ciphertext de A")
        return False
    except VaultError:
        print("  OK vault B rechaza ciphertext de A")
    return True


def test_passphrase_derivation() -> bool:
    section("[4] PBKDF2 passphrase derivation")
    key1 = derive_key_from_passphrase("correct horse battery staple",
                                       salt="borsenhirn-prod-2026")
    key2 = derive_key_from_passphrase("correct horse battery staple",
                                       salt="borsenhirn-prod-2026")
    assert key1 == key2, "FAIL: misma passphrase + salt → keys distintas"
    key3 = derive_key_from_passphrase("correct horse battery staple",
                                       salt="borsenhirn-prod-2027")
    assert key1 != key3, "FAIL: salt distinto → key igual (no debería)"
    print("  OK derivación determinística por (passphrase, salt)")

    # Que la key derivada efectivamente funcione como Fernet key
    v = Vault(key1)
    assert v.decrypt(v.encrypt("hola")) == "hola"
    print("  OK key derivada funciona end-to-end")
    return True


def test_rotation() -> bool:
    section("[5] Master key rotation")
    old = Vault(generate_master_key())
    new = Vault(generate_master_key())
    ct_old = old.encrypt("api-key-secret")
    ct_new = old.rotate(ct_old, new)

    # New vault puede leer; old vault NO puede leer la rotada
    assert new.decrypt(ct_new) == "api-key-secret"
    print("  OK new vault decrypts ciphertext rotado")

    try:
        old.decrypt(ct_new)
        print("  FAIL: old vault no debería leer ciphertext rotado")
        return False
    except VaultError:
        print("  OK old vault rechaza ciphertext rotado")
    return True


def test_validation() -> bool:
    section("[6] Validación de inputs")
    v = Vault(generate_master_key())

    # plaintext vacío → reject
    try:
        v.encrypt("")
        print("  FAIL: encrypt('') debería rechazar")
        return False
    except VaultError:
        print("  OK encrypt vacío rechazado")

    # master key vacía
    try:
        Vault("")
        print("  FAIL: Vault('') debería rechazar")
        return False
    except VaultError:
        print("  OK Vault con key vacía rechazado")

    # master key inválida
    try:
        Vault("definitely not a fernet key")
        print("  FAIL: Vault con key inválida debería rechazar")
        return False
    except VaultError:
        print("  OK Vault con key inválida rechazado")

    # iterations bajos en PBKDF2
    try:
        derive_key_from_passphrase("x", salt="salt-large", iterations=100)
        print("  FAIL: iterations=100 debería rechazar")
        return False
    except VaultError:
        print("  OK PBKDF2 con iterations bajos rechazado")

    return True


def test_db_integration() -> bool:
    """Solo si BORSENHIRN_TEST_DB=1."""
    if not os.environ.get("BORSENHIRN_TEST_DB"):
        return True
    section("[7] Integración con Postgres")
    try:
        import psycopg2
    except ImportError:
        print("  SKIP: psycopg2 no instalado")
        return True

    import config
    from borsenhirn.security import CredentialStore

    conn = psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT,
        dbname=config.DB_NAME, user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    # Verificar tabla
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.user_credentials')")
        if cur.fetchone()[0] is None:
            print("  FAIL: tabla user_credentials no existe")
            print("  → aplicá: psql -f borsenhirn/security/migrations.sql")
            return False
    print("  OK tabla user_credentials existe")

    vault = Vault(generate_master_key())
    store = CredentialStore(lambda: conn, vault)

    test_user = "00000000-0000-0000-0000-000000000001"
    store.set(test_user, "alpaca", "PKTESTKEY", "TESTSECRET")
    print("  OK set credentials")

    creds = store.get(test_user, "alpaca")
    assert creds.api_key == "PKTESTKEY"
    assert creds.api_secret == "TESTSECRET"
    print("  OK get credentials roundtrip")

    users = store.list_users("alpaca")
    assert test_user in users
    print(f"  OK list_users devolvió {len(users)} usuario(s)")

    deleted = store.delete(test_user, "alpaca")
    assert deleted
    print("  OK delete credentials")

    conn.close()
    return True


def main() -> int:
    results = []
    for fn in [test_basic_roundtrip, test_tamper_detection,
                test_wrong_master_key, test_passphrase_derivation,
                test_rotation, test_validation, test_db_integration]:
        try:
            ok = fn()
        except Exception as exc:
            print(f"\n  EXCEPCIÓN en {fn.__name__}: {exc}")
            ok = False
        results.append((fn.__name__, ok))

    print(f"\n{SEP}\n  RESUMEN\n{SEP}")
    all_ok = True
    for name, ok in results:
        status = "OK  " if ok else "FAIL"
        print(f"  {status}  {name}")
        all_ok = all_ok and ok

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
