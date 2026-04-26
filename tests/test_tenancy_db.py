"""Tests de borsenhirn.tenancy.db (TenantContext)."""

from __future__ import annotations

import pytest

from borsenhirn.tenancy.db import (
    TenantContext,
    clear_current_tenant,
    get_current_tenant,
    open_for_tenant,
    set_current_tenant,
)


# ── Mock connection con cursor inspectable ──────────────


class FakeCursor:
    def __init__(self, parent: "FakeConn"):
        self.parent = parent

    def __enter__(self): return self
    def __exit__(self, *a): pass

    def execute(self, sql, params=()):
        self.parent.calls.append((sql.strip(), params))


class FakeConn:
    def __init__(self):
        self.calls = []

    def cursor(self):
        return FakeCursor(self)


@pytest.fixture
def conn():
    return FakeConn()


# ── set_current_tenant ──────────────────────────────────


def test_set_current_tenant_executes_set_config(conn):
    tid = "12345678-1234-1234-1234-123456789012"
    set_current_tenant(conn, tid)
    assert len(conn.calls) == 1
    sql, params = conn.calls[0]
    assert "set_config" in sql
    assert "app.current_tenant_id" in sql
    assert params == (tid,)


def test_set_current_tenant_rejects_invalid_uuid(conn):
    with pytest.raises(ValueError):
        set_current_tenant(conn, "not-a-uuid")


def test_set_updates_thread_local(conn):
    tid = "abcdef00-1234-1234-1234-123456789012"
    set_current_tenant(conn, tid)
    assert get_current_tenant() == tid


def test_clear_current_tenant_resets(conn):
    set_current_tenant(conn, "12345678-1234-1234-1234-123456789012")
    clear_current_tenant(conn)
    assert get_current_tenant() is None


# ── TenantContext (with statement) ──────────────────────


def test_tenant_context_sets_on_enter(conn):
    tid = "12345678-1234-1234-1234-123456789012"
    with TenantContext(conn, tid):
        assert get_current_tenant() == tid
    # tras __exit__ vuelve a None (no había previo)
    assert get_current_tenant() is None


def test_tenant_context_clears_on_exception(conn):
    tid = "12345678-1234-1234-1234-123456789012"
    with pytest.raises(RuntimeError):
        with TenantContext(conn, tid):
            assert get_current_tenant() == tid
            raise RuntimeError("boom")
    # incluso con excepción, se limpió
    assert get_current_tenant() is None


def test_tenant_context_nested_restores_outer(conn):
    outer = "11111111-1111-1111-1111-111111111111"
    inner = "22222222-2222-2222-2222-222222222222"
    with TenantContext(conn, outer):
        assert get_current_tenant() == outer
        with TenantContext(conn, inner):
            assert get_current_tenant() == inner
        # al salir del inner debe restaurar outer
        assert get_current_tenant() == outer


def test_tenant_context_rejects_invalid_id(conn):
    with pytest.raises(ValueError):
        TenantContext(conn, "garbage")


# ── open_for_tenant context manager ─────────────────────


def test_open_for_tenant_sets_and_yields(conn):
    tid = "33333333-3333-3333-3333-333333333333"
    captured_conn = None
    with open_for_tenant(lambda: conn, tid) as c:
        captured_conn = c
        assert get_current_tenant() == tid
    assert captured_conn is conn
    assert get_current_tenant() is None


def test_open_for_tenant_rejects_invalid(conn):
    with pytest.raises(ValueError):
        with open_for_tenant(lambda: conn, "x") as c:
            pass


# ── Thread isolation ────────────────────────────────────


def test_thread_local_isolation():
    """
    El thread-local de tenant_id se debe mantener separado entre threads.
    Esto verifica que dos threads pueden tener tenants distintos a la vez
    sin interferir.
    """
    import threading

    results = {"a": None, "b": None}
    barrier = threading.Barrier(2)

    def worker(name, tid):
        c = FakeConn()
        set_current_tenant(c, tid)
        barrier.wait()      # asegurar que ambos setean antes de leer
        results[name] = get_current_tenant()

    t1 = threading.Thread(target=worker, args=(
        "a", "11111111-1111-1111-1111-111111111111"))
    t2 = threading.Thread(target=worker, args=(
        "b", "22222222-2222-2222-2222-222222222222"))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert results["a"] == "11111111-1111-1111-1111-111111111111"
    assert results["b"] == "22222222-2222-2222-2222-222222222222"
