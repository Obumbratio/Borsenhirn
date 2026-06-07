"""
B5.2 — e2e del audit_log contra borsenhirn_dev (gated).

Verifica: record real bajo un tenant temporal, lectura, aislamiento por RLS, y
append-only (el rol app no puede UPDATE/DELETE). Limpia en teardown.
"""

from __future__ import annotations

import pytest

import config
import borsenhirn.db as bdb
from borsenhirn.audit import AuditLogger, AuditAction
from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"B5 audit requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

TENANT = "00000000-0000-0000-0000-0000000000a5"


@pytest.fixture
def temp_tenant():
    with bdb.get_conn(role="admin") as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tenants (tenant_id, slug, email, display_name) "
                "VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id) DO NOTHING",
                (TENANT, "audit-b5", "audit@test.local", "Audit B5"))
        conn.commit()
    try:
        yield TENANT
    finally:
        with bdb.get_conn(role="admin") as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM audit_log WHERE tenant_id = %s", (TENANT,))
                cur.execute("DELETE FROM tenants WHERE tenant_id = %s", (TENANT,))
            conn.commit()
        bdb.close_all_pools()


def _count_under(tenant_id, action):
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM audit_log WHERE action = %s", (action,))
            return cur.fetchone()[0]


def test_record_and_read_under_tenant(temp_tenant):
    AuditLogger().record(temp_tenant, AuditAction.CRED_READ,
                         resource="alpaca", metadata={"ip": "1.2.3.4"})
    assert _count_under(temp_tenant, AuditAction.CRED_READ) == 1


def test_audit_isolated_by_rls(temp_tenant):
    AuditLogger().record(temp_tenant, AuditAction.KS_HALT)
    # el default tenant NO ve el audit del temp
    assert _count_under(DEFAULT_TENANT_UUID, AuditAction.KS_HALT) == 0


def test_append_only_app_role_cannot_update_or_delete(temp_tenant):
    import psycopg2
    AuditLogger().record(temp_tenant, AuditAction.BILLING_UPDATED)
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, temp_tenant):
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("UPDATE audit_log SET actor = 'hacker'")
        conn.rollback()
        with conn.cursor() as cur:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                cur.execute("DELETE FROM audit_log")
        conn.rollback()
