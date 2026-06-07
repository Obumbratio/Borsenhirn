"""Tests de borsenhirn.tenancy.management (TenantManager) con DB mock."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Tuple

import pytest

from borsenhirn.tenancy.management import TenantManager
from borsenhirn.tenancy.tenant import (
    SYSTEM_TENANT_ID,
    Tenant,
    TenantStatus,
    is_valid_tenant_id,
    new_tenant_id,
)


# ── Fake Postgres backend ──────────────────────────────


class FakeCursor:
    def __init__(self, db: "FakeDB"):
        self.db = db
        self._results: List[Tuple] = []
        self.rowcount = 0

    def __enter__(self): return self
    def __exit__(self, *a): pass

    def execute(self, sql, params=()):
        sql_norm = " ".join(sql.split())
        first = sql_norm.split()[0].upper()
        if first == "INSERT":
            self.db.insert(params)
            self._results = [self.db.last_insert]
            self.rowcount = 1
        elif first == "UPDATE":
            n = self.db.update(sql_norm, params)
            self.rowcount = n
        elif first == "SELECT":
            if "COUNT(" in sql_norm.upper():
                self._results = [(self.db.count(params, sql_norm),)]
            elif "WHERE tenant_id =" in sql_norm:
                self._results = self.db.find_by_id(params)
            elif "WHERE slug =" in sql_norm:
                self._results = self.db.find_by_slug(params)
            elif "lower(email) = lower" in sql_norm:
                self._results = self.db.find_by_email(params)
            elif "WHERE status =" in sql_norm:
                self._results = self.db.list_by_status(params)
            else:
                self._results = self.db.list_all(params)
        else:
            self._results = []

    def fetchone(self):
        return self._results[0] if self._results else None

    def fetchall(self):
        return list(self._results)


class FakeDB:
    def __init__(self):
        self.rows: Dict[str, Dict[str, Any]] = {}
        self.last_insert: Tuple = ()

    def insert(self, params):
        (tid, slug, email, name, status, meta_json) = params
        meta = json.loads(meta_json) if isinstance(meta_json, str) else meta_json
        row = {
            "tenant_id": tid, "slug": slug, "email": email,
            "display_name": name, "status": status,
            "created_at": datetime(2026, 1, 1),
            "updated_at": datetime(2026, 1, 1),
            "suspended_at": None, "metadata": meta,
        }
        self.rows[tid] = row
        self.last_insert = self._row_to_tuple(row)

    def update(self, sql, params):
        (status, reason, tid) = params
        if tid not in self.rows:
            return 0
        self.rows[tid]["status"] = status
        if status == "suspended":
            self.rows[tid]["suspended_at"] = datetime.now()
        else:
            self.rows[tid]["suspended_at"] = None
        self.rows[tid]["metadata"] = {
            **(self.rows[tid].get("metadata") or {}),
            "last_status_change_reason": reason,
        }
        return 1

    def count(self, params, sql):
        if "WHERE status =" in sql:
            return sum(1 for r in self.rows.values() if r["status"] == params[0])
        return len(self.rows)

    def find_by_id(self, params):
        r = self.rows.get(params[0])
        return [self._row_to_tuple(r)] if r else []

    def find_by_slug(self, params):
        for r in self.rows.values():
            if r["slug"] == params[0]:
                return [self._row_to_tuple(r)]
        return []

    def find_by_email(self, params):
        for r in self.rows.values():
            if r["email"].lower() == params[0].lower():
                return [self._row_to_tuple(r)]
        return []

    def list_by_status(self, params):
        status, limit, offset = params
        rows = [r for r in self.rows.values() if r["status"] == status]
        return [self._row_to_tuple(r) for r in rows[offset:offset + limit]]

    def list_all(self, params):
        limit, offset = params
        rows = list(self.rows.values())
        return [self._row_to_tuple(r) for r in rows[offset:offset + limit]]

    def _row_to_tuple(self, r):
        return (r["tenant_id"], r["slug"], r["email"], r["display_name"],
                r["status"], r["created_at"], r["updated_at"],
                r["suspended_at"], json.dumps(r.get("metadata") or {}))


class FakeConn:
    def __init__(self, db: FakeDB):
        self.db = db
        self.committed = 0

    def cursor(self): return FakeCursor(self.db)
    def commit(self): self.committed += 1
    def rollback(self): pass


@pytest.fixture
def db(): return FakeDB()


@pytest.fixture
def manager(db):
    conn = FakeConn(db)
    return TenantManager(get_conn=lambda: conn)


# ── create_tenant ────────────────────────────────────────


def test_create_tenant_basic(manager):
    t = manager.create_tenant(
        email="uriel@example.com",
        display_name="Uriel Castaño",
    )
    assert is_valid_tenant_id(t.tenant_id)
    assert t.email == "uriel@example.com"
    assert t.status == TenantStatus.ACTIVE
    assert t.slug.startswith("uriel-")


def test_create_tenant_with_explicit_slug(manager):
    t = manager.create_tenant(
        email="x@y.com", display_name="X",
        slug="my-custom-slug",
    )
    assert t.slug == "my-custom-slug"


def test_create_tenant_with_metadata(manager):
    t = manager.create_tenant(
        email="x@y.com", display_name="X",
        metadata={"signup_source": "landing", "plan": "free"},
    )
    assert t.metadata["signup_source"] == "landing"


def test_create_tenant_rejects_bad_email(manager):
    with pytest.raises(ValueError):
        manager.create_tenant(email="not-email", display_name="X")


def test_create_tenant_rejects_empty_name(manager):
    with pytest.raises(ValueError):
        manager.create_tenant(email="x@y.com", display_name="")


def test_create_tenant_rejects_bad_slug(manager):
    with pytest.raises(ValueError):
        manager.create_tenant(
            email="x@y.com", display_name="X",
            slug="Bad Slug!",
        )


# ── get_tenant ───────────────────────────────────────────


def test_get_tenant_existing(manager):
    t1 = manager.create_tenant(email="a@b.com", display_name="A")
    t2 = manager.get_tenant(t1.tenant_id)
    assert t2 is not None
    assert t2.tenant_id == t1.tenant_id


def test_get_tenant_missing(manager):
    assert manager.get_tenant(new_tenant_id()) is None


def test_get_tenant_rejects_bad_uuid(manager):
    with pytest.raises(ValueError):
        manager.get_tenant("not-uuid")


def test_get_tenant_by_slug(manager):
    t = manager.create_tenant(
        email="a@b.com", display_name="A", slug="abc-123",
    )
    found = manager.get_tenant_by_slug("abc-123")
    assert found is not None
    assert found.tenant_id == t.tenant_id


def test_get_tenant_by_email_case_insensitive(manager):
    t = manager.create_tenant(email="MixedCase@Example.com",
                              display_name="X")
    found = manager.get_tenant_by_email("mixedcase@example.com")
    assert found is not None
    assert found.tenant_id == t.tenant_id


# ── list / count ─────────────────────────────────────────


def test_list_tenants_empty(manager):
    assert manager.list_tenants() == []


def test_list_tenants_returns_all(manager):
    for i in range(5):
        manager.create_tenant(email=f"u{i}@x.com", display_name=f"U{i}")
    assert len(manager.list_tenants()) == 5


def test_count_filtered_by_status(manager):
    t1 = manager.create_tenant(email="a@b.com", display_name="A")
    t2 = manager.create_tenant(email="c@d.com", display_name="C")
    manager.suspend(t2.tenant_id, "test")
    assert manager.count_tenants(TenantStatus.ACTIVE) == 1
    assert manager.count_tenants(TenantStatus.SUSPENDED) == 1
    assert manager.count_tenants() == 2


# ── suspend / disable / reactivate ───────────────────────


def test_suspend_changes_status(manager):
    t = manager.create_tenant(email="a@b.com", display_name="A")
    ok = manager.suspend(t.tenant_id, reason="non-payment")
    assert ok
    refreshed = manager.get_tenant(t.tenant_id)
    assert refreshed.status == TenantStatus.SUSPENDED
    assert not refreshed.can_trade()


def test_disable_then_reactivate(manager):
    t = manager.create_tenant(email="a@b.com", display_name="A")
    manager.disable(t.tenant_id, "user requested")
    assert manager.get_tenant(t.tenant_id).status == TenantStatus.DISABLED
    manager.reactivate(t.tenant_id, "user came back")
    assert manager.get_tenant(t.tenant_id).status == TenantStatus.ACTIVE


def test_soft_delete_marks_status(manager):
    t = manager.create_tenant(email="a@b.com", display_name="A")
    manager.soft_delete(t.tenant_id, "GDPR request")
    assert manager.get_tenant(t.tenant_id).status == TenantStatus.DELETED


def test_update_status_missing_returns_false(manager):
    ok = manager.suspend(new_tenant_id(), "test")
    assert ok is False


# ── Slug derivation ──────────────────────────────────────


def test_derive_slug_from_email():
    slug = TenantManager._derive_slug("uriel.castano@gmail.com",
                                      "abc12345-1234-1234-1234-123456789012")
    assert slug.startswith("uriel-castano")
    assert slug.endswith("abc1")


def test_derive_slug_handles_short_local_part():
    slug = TenantManager._derive_slug("a@b.com",
                                      "abc12345-1234-1234-1234-123456789012")
    # Aún corto pero al menos cumple min length 3
    assert len(slug) >= 3
