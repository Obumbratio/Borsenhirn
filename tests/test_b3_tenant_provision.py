"""
B3.1 — Provisión lazy de tenant por clerk_user_id (modelo 1 user = 1 tenant).

Integration test contra borsenhirn_dev (gated por RUN_DB_INTEGRATION).
Usa credenciales admin (provisión escribe en `tenants`). Limpia el tenant
temporal en teardown.
"""

from __future__ import annotations

import pytest

import config
from borsenhirn.tenancy.management import TenantManager

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"B3 provision requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

CLERK_ID = "user_b3test_provision_xyz"


@pytest.fixture
def admin_conn():
    import psycopg2
    conn = psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT, dbname=config.DB_NAME,
        user=config.DB_USER, password=config.DB_PASSWORD,
    )
    try:
        yield conn
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tenants WHERE clerk_user_id = %s", (CLERK_ID,))
        conn.commit()
        conn.close()


def test_provision_creates_and_maps(admin_conn):
    mgr = TenantManager(get_conn=lambda: admin_conn)

    assert mgr.get_tenant_by_clerk_id(CLERK_ID) is None   # no existe aún

    t = mgr.provision_for_clerk_user(CLERK_ID, "b3@test.local", "B3 Test User")
    assert t.tenant_id
    assert t.email == "b3@test.local"

    # quedó mapeado por clerk_user_id
    looked = mgr.get_tenant_by_clerk_id(CLERK_ID)
    assert looked is not None and looked.tenant_id == t.tenant_id
    assert t.metadata.get("clerk_user_id") == CLERK_ID


def test_provision_is_idempotent(admin_conn):
    mgr = TenantManager(get_conn=lambda: admin_conn)
    t1 = mgr.provision_for_clerk_user(CLERK_ID, "b3@test.local", "B3 Test User")
    t2 = mgr.provision_for_clerk_user(CLERK_ID, "otro@test.local", "Otro Nombre")
    # segundo llamado NO crea otro tenant: devuelve el mismo.
    assert t1.tenant_id == t2.tenant_id


def test_provision_rejects_bad_email(admin_conn):
    mgr = TenantManager(get_conn=lambda: admin_conn)
    with pytest.raises(ValueError):
        mgr.provision_for_clerk_user("user_other", "no-es-email", "X")
