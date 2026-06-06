"""
B2 — Tests de la capa de secret providers (master key fuera de .env).

Puro stdlib: sin DB ni red. Corren en la baseline normal.
"""

from __future__ import annotations

import pytest

from borsenhirn.security.secret_provider import (
    EnvSecretProvider,
    FileSecretProvider,
    CommandSecretProvider,
    SecretError,
    resolve_secret,
    load_master_key,
    default_chain,
)
from borsenhirn.security import Vault, VaultError, generate_master_key

KEY = "BORSENHIRN_TESTSECRET"


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    # Asegura que ninguna de las 3 fuentes esté seteada de arrastre.
    for suffix in ("", "_FILE", "_CMD"):
        monkeypatch.delenv(KEY + suffix, raising=False)
    yield


# ── EnvSecretProvider ───────────────────────────────────────────

def test_env_provider_reads_value(monkeypatch):
    monkeypatch.setenv(KEY, "valor-env")
    assert EnvSecretProvider().get(KEY) == "valor-env"


def test_env_provider_none_when_unset():
    assert EnvSecretProvider().get(KEY) is None


def test_env_provider_none_when_empty(monkeypatch):
    monkeypatch.setenv(KEY, "")
    assert EnvSecretProvider().get(KEY) is None


# ── FileSecretProvider ──────────────────────────────────────────

def test_file_provider_reads_and_strips(monkeypatch, tmp_path):
    f = tmp_path / "secret.txt"
    f.write_text("  valor-archivo\n")
    monkeypatch.setenv(f"{KEY}_FILE", str(f))
    assert FileSecretProvider().get(KEY) == "valor-archivo"


def test_file_provider_none_when_not_configured():
    assert FileSecretProvider().get(KEY) is None


def test_file_provider_raises_when_path_missing(monkeypatch, tmp_path):
    monkeypatch.setenv(f"{KEY}_FILE", str(tmp_path / "no-existe"))
    with pytest.raises(SecretError):
        FileSecretProvider().get(KEY)


# ── CommandSecretProvider ───────────────────────────────────────

def test_command_provider_uses_stdout(monkeypatch):
    monkeypatch.setenv(f"{KEY}_CMD", "printf 'valor-cmd'")
    assert CommandSecretProvider().get(KEY) == "valor-cmd"


def test_command_provider_none_when_not_configured():
    assert CommandSecretProvider().get(KEY) is None


def test_command_provider_raises_on_failure(monkeypatch):
    monkeypatch.setenv(f"{KEY}_CMD", "exit 7")
    with pytest.raises(SecretError):
        CommandSecretProvider().get(KEY)


# ── resolve_secret (prioridad: file > command > env) ────────────

def test_resolve_priority_file_beats_command_and_env(monkeypatch, tmp_path):
    f = tmp_path / "s.txt"; f.write_text("desde-archivo")
    monkeypatch.setenv(f"{KEY}_FILE", str(f))
    monkeypatch.setenv(f"{KEY}_CMD", "printf 'desde-cmd'")
    monkeypatch.setenv(KEY, "desde-env")
    assert resolve_secret(KEY) == "desde-archivo"


def test_resolve_priority_command_beats_env(monkeypatch):
    monkeypatch.setenv(f"{KEY}_CMD", "printf 'desde-cmd'")
    monkeypatch.setenv(KEY, "desde-env")
    assert resolve_secret(KEY) == "desde-cmd"


def test_resolve_falls_back_to_env(monkeypatch):
    monkeypatch.setenv(KEY, "desde-env")
    assert resolve_secret(KEY) == "desde-env"


def test_resolve_default_when_missing():
    assert resolve_secret(KEY, default="x") == "x"


def test_resolve_required_raises_when_missing():
    with pytest.raises(SecretError):
        resolve_secret(KEY, required=True)


def test_default_chain_order():
    assert [p.name for p in default_chain()] == ["file", "command", "env"]


# ── Integración con Vault ───────────────────────────────────────

def test_vault_from_provider_env(monkeypatch):
    mk = generate_master_key()
    monkeypatch.setenv("BORSENHIRN_MASTER_KEY", mk)
    v = Vault.from_provider()
    ct = v.encrypt("hola")
    assert v.decrypt(ct) == "hola"


def test_vault_from_provider_file(monkeypatch, tmp_path):
    mk = generate_master_key()
    f = tmp_path / "mk"; f.write_text(mk)
    monkeypatch.delenv("BORSENHIRN_MASTER_KEY", raising=False)
    monkeypatch.setenv("BORSENHIRN_MASTER_KEY_FILE", str(f))
    v = Vault.from_provider()
    assert v.decrypt(v.encrypt("x")) == "x"


def test_vault_from_provider_missing_raises(monkeypatch):
    for s in ("", "_FILE", "_CMD"):
        monkeypatch.delenv("BORSENHIRN_MASTER_KEY" + s, raising=False)
    with pytest.raises(VaultError):
        Vault.from_provider()


def test_load_master_key_required(monkeypatch):
    for s in ("", "_FILE", "_CMD"):
        monkeypatch.delenv("BORSENHIRN_MASTER_KEY" + s, raising=False)
    with pytest.raises(SecretError):
        load_master_key()
