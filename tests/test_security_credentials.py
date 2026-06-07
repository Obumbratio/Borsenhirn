"""Tests de borsenhirn.security.credentials con conexión Postgres mock."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import pytest

from borsenhirn.security.credentials import (
    CredentialStore,
    UserCredentials,
)
from borsenhirn.security.vault import Vault, VaultError, generate_master_key


# ── Mock de psycopg2 conn / cursor ──────────────────────────


class FakeCursor:
    def __init__(self, store: "FakeDB"):
        self.store = store
        self.last_sql = ""
        self._results: List[Tuple] = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def execute(self, sql, params=()):
        self.last_sql = sql.strip()
        first = self.last_sql.split()[0].upper()
        if first == "INSERT":
            self.store.upsert(params)
            self.rowcount = 1
        elif first == "UPDATE":
            self.store.update_ct(params)
            self.rowcount = 1
        elif first == "SELECT":
            if "DISTINCT user_id" in self.last_sql:
                provider = params[0] if params else None
                self._results = [(uid,) for uid in self.store.list_users(provider)]
            elif "ORDER BY user_id, provider" in self.last_sql:
                self._results = self.store.iter_all_for_select()
            else:
                row = self.store.get_row(params)
                self._results = [row] if row else []
        elif first == "DELETE":
            ok = self.store.delete(params)
            self.rowcount = 1 if ok else 0
        else:
            self._results = []

    def fetchone(self):
        return self._results[0] if self._results else None

    def fetchall(self):
        return list(self._results)


class FakeDB:
    """In-memory simulación de la tabla user_credentials."""

    def __init__(self):
        self.rows: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def upsert(self, params):
        (user_id, provider, key_ct, sec_ct, ver) = params
        key = (user_id, provider)
        self.rows[key] = {
            "user_id": user_id, "provider": provider,
            "api_key_ciphertext": key_ct,
            "api_secret_ciphertext": sec_ct,
            "encryption_version": ver,
            "created_at": "2026-01-01",
            "updated_at": "2026-01-02",
        }

    def update_ct(self, params):
        (key_ct, sec_ct, ver, user_id, provider) = params
        key = (user_id, provider)
        if key in self.rows:
            self.rows[key].update({
                "api_key_ciphertext": key_ct,
                "api_secret_ciphertext": sec_ct,
                "encryption_version": ver,
            })

    def get_row(self, params):
        (user_id, provider) = params
        r = self.rows.get((user_id, provider))
        if not r:
            return None
        return (
            r["user_id"], r["provider"],
            r["api_key_ciphertext"], r["api_secret_ciphertext"],
            r["encryption_version"], r["created_at"], r["updated_at"],
        )

    def delete(self, params):
        (user_id, provider) = params
        return self.rows.pop((user_id, provider), None) is not None

    def list_users(self, provider=None):
        if provider:
            return sorted({u for u, p in self.rows if p == provider})
        return sorted({u for u, p in self.rows})

    def iter_all_for_select(self):
        return [
            (r["user_id"], r["provider"],
             r["api_key_ciphertext"], r["api_secret_ciphertext"])
            for r in sorted(self.rows.values(),
                            key=lambda x: (x["user_id"], x["provider"]))
        ]


class FakeConn:
    def __init__(self, db: FakeDB):
        self.db = db
        self.committed = 0
        self.rolled_back = 0

    def cursor(self):
        return FakeCursor(self.db)

    def commit(self):
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1


@pytest.fixture
def fake_db():
    return FakeDB()


@pytest.fixture
def fake_conn(fake_db):
    return FakeConn(fake_db)


@pytest.fixture
def vault():
    return Vault(generate_master_key())


@pytest.fixture
def store(fake_conn, vault):
    return CredentialStore(get_conn=lambda: fake_conn, vault=vault)


# ── set ──────────────────────────────────────────────────────


def test_set_persists_encrypted(store, fake_db, vault):
    store.set("user1", "alpaca", "PKABC", "SECRET123")
    assert ("user1", "alpaca") in fake_db.rows
    row = fake_db.rows[("user1", "alpaca")]
    # NUNCA debe haber plaintext en la "DB"
    assert row["api_key_ciphertext"] != b"PKABC"
    assert vault.decrypt(row["api_key_ciphertext"]) == "PKABC"
    assert vault.decrypt(row["api_secret_ciphertext"]) == "SECRET123"


def test_set_rejects_empty_user(store):
    with pytest.raises(ValueError):
        store.set("", "alpaca", "k", "s")


def test_set_rejects_empty_credentials(store):
    with pytest.raises(ValueError):
        store.set("u", "alpaca", "", "s")
    with pytest.raises(ValueError):
        store.set("u", "alpaca", "k", "")


def test_set_idempotent_overwrites(store, fake_db, vault):
    store.set("user1", "alpaca", "K1", "S1")
    store.set("user1", "alpaca", "K2", "S2")
    creds = store.get("user1", "alpaca")
    assert creds.api_key == "K2"
    assert creds.api_secret == "S2"


# ── get ──────────────────────────────────────────────────────


def test_get_missing_returns_none(store):
    assert store.get("nope", "alpaca") is None


def test_get_returns_decrypted(store):
    store.set("u1", "alpaca", "PKABC", "SECRET")
    creds = store.get("u1", "alpaca")
    assert isinstance(creds, UserCredentials)
    assert creds.api_key == "PKABC"
    assert creds.api_secret == "SECRET"
    assert creds.user_id == "u1"
    assert creds.provider == "alpaca"


def test_get_default_provider(store):
    store.set("u1", "alpaca", "K", "S")
    creds = store.get("u1")  # default provider="alpaca"
    assert creds is not None
    assert creds.api_key == "K"


def test_get_with_wrong_vault_raises(fake_conn, fake_db):
    """Si la master key cambió y nadie rotó, get() debe fallar duro."""
    v_old = Vault(generate_master_key())
    v_new = Vault(generate_master_key())
    s_old = CredentialStore(lambda: fake_conn, v_old)
    s_old.set("u1", "alpaca", "K", "S")

    s_new = CredentialStore(lambda: fake_conn, v_new)
    with pytest.raises(VaultError):
        s_new.get("u1", "alpaca")


# ── delete ───────────────────────────────────────────────────


def test_delete_existing_returns_true(store):
    store.set("u1", "alpaca", "K", "S")
    assert store.delete("u1", "alpaca") is True


def test_delete_missing_returns_false(store):
    assert store.delete("nope", "alpaca") is False


def test_delete_actually_removes(store, fake_db):
    store.set("u1", "alpaca", "K", "S")
    store.delete("u1", "alpaca")
    assert store.get("u1", "alpaca") is None


# ── list ─────────────────────────────────────────────────────


def test_list_users_empty(store):
    assert store.list_users() == []


def test_list_users_returns_sorted(store):
    store.set("user-c", "alpaca", "K", "S")
    store.set("user-a", "alpaca", "K", "S")
    store.set("user-b", "alpaca", "K", "S")
    users = store.list_users("alpaca")
    assert users == ["user-a", "user-b", "user-c"]


def test_list_users_filters_by_provider(store):
    store.set("u1", "alpaca", "K", "S")
    store.set("u2", "ibkr", "K", "S")
    assert store.list_users("alpaca") == ["u1"]
    assert store.list_users("ibkr") == ["u2"]


# ── iter_all_ciphertexts (rotation) ─────────────────────────


def test_iter_all_ciphertexts_yields_raw_bytes(store):
    store.set("u1", "alpaca", "K1", "S1")
    store.set("u2", "alpaca", "K2", "S2")
    items = list(store.iter_all_ciphertexts())
    assert len(items) == 2
    for user_id, provider, key_ct, sec_ct in items:
        assert isinstance(key_ct, bytes)
        assert isinstance(sec_ct, bytes)


def test_replace_ciphertexts_works(store, vault):
    store.set("u1", "alpaca", "OLD_K", "OLD_S")
    new_key_ct = vault.encrypt("NEW_K")
    new_sec_ct = vault.encrypt("NEW_S")
    store.replace_ciphertexts("u1", "alpaca", new_key_ct, new_sec_ct)
    creds = store.get("u1", "alpaca")
    assert creds.api_key == "NEW_K"
    assert creds.api_secret == "NEW_S"


# ── End-to-end rotation (simula scripts/rotate_master_key.py) ─


def test_full_rotation_flow(fake_conn, fake_db):
    old_vault = Vault(generate_master_key())
    new_vault = Vault(generate_master_key())

    # Sembrar con vault vieja
    old_store = CredentialStore(lambda: fake_conn, old_vault)
    old_store.set("user-1", "alpaca", "K1", "S1")
    old_store.set("user-2", "alpaca", "K2", "S2")

    # Rotar
    new_store = CredentialStore(lambda: fake_conn, new_vault)
    for user_id, provider, key_ct, sec_ct in old_store.iter_all_ciphertexts():
        # Decrypt con vieja, encrypt con nueva
        key_pt = old_vault.decrypt(key_ct)
        sec_pt = old_vault.decrypt(sec_ct)
        new_key_ct = new_vault.encrypt(key_pt)
        new_sec_ct = new_vault.encrypt(sec_pt)
        new_store.replace_ciphertexts(user_id, provider, new_key_ct, new_sec_ct)

    # Confirmar que la nueva vault las puede leer
    c1 = new_store.get("user-1", "alpaca")
    c2 = new_store.get("user-2", "alpaca")
    assert c1.api_key == "K1" and c1.api_secret == "S1"
    assert c2.api_key == "K2" and c2.api_secret == "S2"

    # Confirmar que la vieja vault YA NO puede leer
    with pytest.raises(VaultError):
        old_store.get("user-1", "alpaca")
