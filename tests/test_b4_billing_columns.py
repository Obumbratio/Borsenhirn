"""
B4.1 — Tests de las columnas de billing + métodos del manager.

Integration contra borsenhirn_dev (gated). Usa un tenant temporal y limpia.
"""

from __future__ import annotations

import pytest

import config
from borsenhirn.tenancy.management import TenantManager

if config.DB_NAME != "borsenhirn_dev":
    pytest.skip(
        f"B4 billing requiere DB_NAME=borsenhirn_dev (actual: {config.DB_NAME!r}).",
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

CLERK_ID = "user_b4_billing_test"
CUSTOMER = "cus_test_b4_xyz"


@pytest.fixture
def mgr_and_tenant():
    import psycopg2
    conn = psycopg2.connect(
        host=config.DB_HOST, port=config.DB_PORT, dbname=config.DB_NAME,
        user=config.DB_USER, password=config.DB_PASSWORD,
    )
    mgr = TenantManager(get_conn=lambda: conn)
    t = mgr.provision_for_clerk_user(CLERK_ID, "b4@test.local", "B4 Billing")
    try:
        yield mgr, t
    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM audit_log WHERE tenant_id IN "
                        "(SELECT tenant_id FROM tenants WHERE clerk_user_id=%s)", (CLERK_ID,))
            cur.execute("DELETE FROM tenants WHERE clerk_user_id = %s", (CLERK_ID,))
        conn.commit()
        conn.close()


def test_set_billing_and_lookup_by_customer(mgr_and_tenant):
    mgr, t = mgr_and_tenant
    mgr.set_billing(t.tenant_id, customer_id=CUSTOMER,
                    subscription_id="sub_test", plan="pro", status="active")
    looked = mgr.get_tenant_by_stripe_customer_id(CUSTOMER)
    assert looked is not None and looked.tenant_id == t.tenant_id
    assert looked.status == "active"


def test_set_billing_moves_status(mgr_and_tenant):
    mgr, t = mgr_and_tenant
    mgr.set_billing(t.tenant_id, customer_id=CUSTOMER)
    mgr.set_billing(t.tenant_id, status="suspended")    # pago falló
    assert mgr.get_tenant(t.tenant_id).status == "suspended"


def test_set_billing_rejects_bad_status(mgr_and_tenant):
    mgr, t = mgr_and_tenant
    with pytest.raises(ValueError):
        mgr.set_billing(t.tenant_id, status="past_due")   # no es un status válido de tenants


def test_set_billing_noop_when_nothing(mgr_and_tenant):
    mgr, t = mgr_and_tenant
    mgr.set_billing(t.tenant_id)   # sin campos -> no rompe
    assert mgr.get_tenant(t.tenant_id) is not None
