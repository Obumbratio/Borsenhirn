"""Tests de borsenhirn.security.vault."""

from __future__ import annotations

import pytest

from borsenhirn.security.vault import (
    Vault,
    VaultError,
    derive_key_from_passphrase,
    generate_master_key,
)


# ── generate_master_key ──────────────────────────────────────


def test_generate_master_key_returns_string():
    key = generate_master_key()
    assert isinstance(key, str)
    assert len(key) > 30   # base64 de 32 bytes ≈ 44 chars


def test_generate_master_key_not_deterministic():
    a = generate_master_key()
    b = generate_master_key()
    assert a != b


def test_generated_key_works_with_vault():
    v = Vault(generate_master_key())
    assert v.decrypt(v.encrypt("hello")) == "hello"


# ── derive_key_from_passphrase ───────────────────────────────


def test_derive_same_passphrase_same_salt_same_key():
    a = derive_key_from_passphrase("pass", "salt-bytes-bigenough")
    b = derive_key_from_passphrase("pass", "salt-bytes-bigenough")
    assert a == b


def test_derive_different_salt_different_key():
    a = derive_key_from_passphrase("pass", "salt-version-1")
    b = derive_key_from_passphrase("pass", "salt-version-2")
    assert a != b


def test_derive_different_passphrase_different_key():
    a = derive_key_from_passphrase("pass1", "salt-bytes-bigenough")
    b = derive_key_from_passphrase("pass2", "salt-bytes-bigenough")
    assert a != b


def test_derive_rejects_short_salt():
    with pytest.raises(VaultError):
        derive_key_from_passphrase("pass", "short")   # < 8 bytes


def test_derive_rejects_low_iterations():
    with pytest.raises(VaultError):
        derive_key_from_passphrase("p", "salt-bigenough", iterations=1000)


def test_derive_accepts_bytes_inputs():
    a = derive_key_from_passphrase(b"pass", b"salt-bigenough")
    b = derive_key_from_passphrase("pass", "salt-bigenough")
    assert a == b


# ── Vault construction ──────────────────────────────────────


def test_vault_rejects_empty_key():
    with pytest.raises(VaultError):
        Vault("")
    with pytest.raises(VaultError):
        Vault(b"")


def test_vault_rejects_invalid_key():
    with pytest.raises(VaultError):
        Vault("not a real fernet key")


def test_vault_accepts_string_key():
    v = Vault(generate_master_key())
    assert v.decrypt(v.encrypt("x")) == "x"


def test_vault_accepts_bytes_key():
    key = generate_master_key().encode("ascii")
    v = Vault(key)
    assert v.decrypt(v.encrypt("x")) == "x"


def test_vault_from_env_missing_raises(monkeypatch):
    monkeypatch.delenv("BORSENHIRN_TEST_KEY", raising=False)
    with pytest.raises(VaultError):
        Vault.from_env("BORSENHIRN_TEST_KEY")


def test_vault_from_env_works(monkeypatch):
    key = generate_master_key()
    monkeypatch.setenv("BORSENHIRN_TEST_KEY", key)
    v = Vault.from_env("BORSENHIRN_TEST_KEY")
    assert v.decrypt(v.encrypt("hello")) == "hello"


# ── encrypt / decrypt ───────────────────────────────────────


def test_encrypt_decrypt_roundtrip_string():
    v = Vault(generate_master_key())
    plain = "PKABCDEF1234567890"
    assert v.decrypt(v.encrypt(plain)) == plain


def test_encrypt_decrypt_roundtrip_bytes():
    v = Vault(generate_master_key())
    assert v.decrypt(v.encrypt(b"binary input")) == "binary input"


def test_encrypt_decrypt_roundtrip_unicode():
    v = Vault(generate_master_key())
    plain = "español ñ ó á é í ú 漢字 emoji 🚀"
    assert v.decrypt(v.encrypt(plain)) == plain


def test_encrypt_long_payload():
    v = Vault(generate_master_key())
    plain = "x" * 100_000
    assert v.decrypt(v.encrypt(plain)) == plain


def test_encrypt_rejects_empty_plaintext():
    v = Vault(generate_master_key())
    with pytest.raises(VaultError):
        v.encrypt("")
    with pytest.raises(VaultError):
        v.encrypt(b"")


def test_encrypt_rejects_non_str_non_bytes():
    v = Vault(generate_master_key())
    with pytest.raises(VaultError):
        v.encrypt(12345)   # type: ignore


def test_encrypt_non_deterministic():
    v = Vault(generate_master_key())
    a = v.encrypt("misma cosa")
    b = v.encrypt("misma cosa")
    assert a != b
    assert v.decrypt(a) == v.decrypt(b)


def test_decrypt_rejects_tampered_ciphertext():
    v = Vault(generate_master_key())
    ct = bytearray(v.encrypt("secreto"))
    ct[10] ^= 0x01   # flip 1 bit
    with pytest.raises(VaultError):
        v.decrypt(bytes(ct))


def test_decrypt_with_wrong_key_fails():
    v_a = Vault(generate_master_key())
    v_b = Vault(generate_master_key())
    ct = v_a.encrypt("x")
    with pytest.raises(VaultError):
        v_b.decrypt(ct)


def test_decrypt_rejects_random_bytes():
    v = Vault(generate_master_key())
    with pytest.raises(VaultError):
        v.decrypt(b"this is not a fernet token at all")


def test_decrypt_rejects_non_bytes():
    v = Vault(generate_master_key())
    with pytest.raises(VaultError):
        v.decrypt(123)   # type: ignore


# ── Rotation ─────────────────────────────────────────────────


def test_rotate_to_new_vault():
    old = Vault(generate_master_key())
    new = Vault(generate_master_key())
    ct_old = old.encrypt("api-secret")
    ct_new = old.rotate(ct_old, new)

    assert new.decrypt(ct_new) == "api-secret"
    with pytest.raises(VaultError):
        old.decrypt(ct_new)


def test_reencrypt_same_key_changes_ciphertext():
    v = Vault(generate_master_key())
    ct1 = v.encrypt("data")
    ct2 = v.reencrypt(ct1)
    assert ct1 != ct2
    assert v.decrypt(ct2) == "data"


# ── can_decrypt ──────────────────────────────────────────────


def test_can_decrypt_true_for_own_ciphertext():
    v = Vault(generate_master_key())
    ct = v.encrypt("x")
    assert v.can_decrypt(ct) is True


def test_can_decrypt_false_for_other_vault():
    a = Vault(generate_master_key())
    b = Vault(generate_master_key())
    ct = a.encrypt("x")
    assert b.can_decrypt(ct) is False


def test_can_decrypt_false_for_garbage():
    v = Vault(generate_master_key())
    assert v.can_decrypt(b"garbage") is False
