"""
B10 — e2e del snapshot/scan contra borsenhirn_dev (gated).

Registra eventos de audit para un tenant temporal y confirma que build_snapshot
los cuenta y que el detector dispara la regla con un umbral bajo. Limpia.
"""

from __future__ import annotations

import pytest

import config
import borsenhirn.db as bdb
from borsenhirn.audit import AuditLogger, AuditAction
from borsenhirn.anomaly import build_snapshot, AnomalyDetector
from borsenhirn.anomaly.detector import rule_credential_access_spike

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"B10 anomaly requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

TENANT = "00000000-0000-0000-0000-0000000000aa"


@pytest.fixture
def temp_tenant():
    with bdb.get_conn(role="admin") as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO tenants (tenant_id, slug, email, display_name) "
                        "VALUES (%s,%s,%s,%s) ON CONFLICT (tenant_id) DO NOTHING",
                        (TENANT, "anom-b10", "anom@test.local", "Anomaly B10"))
        conn.commit()
    try:
        yield TENANT
    finally:
        with bdb.get_conn(role="admin") as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM audit_log WHERE tenant_id=%s", (TENANT,))
                cur.execute("DELETE FROM tenants WHERE tenant_id=%s", (TENANT,))
            conn.commit()
        bdb.close_all_pools()


def test_snapshot_counts_audit_events(temp_tenant):
    audit = AuditLogger()
    for _ in range(5):
        audit.record(temp_tenant, AuditAction.CRED_READ, resource="alpaca")

    snap = build_snapshot(temp_tenant)
    assert snap["audit_counts"].get("credentials.read") == 5

    # con un umbral artificialmente bajo (regla pura sobre el snapshot real), dispara
    import borsenhirn.anomaly.detector as det
    findings = det.AnomalyDetector(rules=[
        lambda s: [det.AnomalyFinding("t", "warn", "x")]
        if s["audit_counts"].get("credentials.read", 0) >= 5 else []
    ], snapshot_fn=build_snapshot).scan(temp_tenant)
    assert findings
