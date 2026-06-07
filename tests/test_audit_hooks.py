"""
B5.3 — Verifica que los hooks de audit DISPARAN (spy logger inyectado).
Sin DB: usa set_audit_logger para capturar las llamadas a record().
"""

from __future__ import annotations

import pytest

from borsenhirn.audit import (
    AuditLogger, set_audit_logger, reset_audit_logger, AuditAction,
)
from borsenhirn.billing import apply_stripe_event


class _Spy(AuditLogger):
    def __init__(self):
        self.calls = []
    def record(self, tenant_id, action, **kw):
        self.calls.append((tenant_id, action, kw))


@pytest.fixture
def spy():
    s = _Spy()
    set_audit_logger(s)
    try:
        yield s
    finally:
        reset_audit_logger()


# ── billing webhook ─────────────────────────────────────────────

class _FakeTenant:
    def __init__(self, tid):
        self.tenant_id = tid


class _FakeTM:
    def get_tenant_by_stripe_customer_id(self, cid):
        return _FakeTenant("00000000-0000-0000-0000-0000000000c1") if cid == "cus_k" else None
    def set_billing(self, tid, **kw):
        pass


def _sub_event(status):
    return {"type": "customer.subscription.updated",
            "data": {"object": {"id": "sub_1", "customer": "cus_k", "status": status,
                                "items": {"data": [{"price": {"id": "price_x"}}]}}}}


def test_billing_hook_fires(spy):
    apply_stripe_event(_sub_event("active"), _FakeTM())
    assert any(a == AuditAction.BILLING_UPDATED for _, a, _ in spy.calls)
    # actor del sistema (no hay request humano)
    assert any(kw.get("actor") == "stripe" for _, _, kw in spy.calls)


def test_billing_hook_skips_unknown_customer(spy):
    ev = _sub_event("active")
    ev["data"]["object"]["customer"] = "cus_desconocido"
    apply_stripe_event(ev, _FakeTM())
    assert not spy.calls


# ── credenciales: respeta tenant_id (skip si None) ──────────────

def test_credentials_audit_respects_tenant(spy):
    from borsenhirn.security.credentials import CredentialStore
    from borsenhirn.security.vault import Vault, generate_master_key
    v = Vault(generate_master_key())

    with_tenant = CredentialStore(lambda: None, v,
                                  tenant_id="00000000-0000-0000-0000-000000000001")
    with_tenant._audit(AuditAction.CRED_READ, "u1", "alpaca")
    assert spy.calls and spy.calls[-1][1] == AuditAction.CRED_READ

    n = len(spy.calls)
    no_tenant = CredentialStore(lambda: None, v, tenant_id=None)
    no_tenant._audit(AuditAction.CRED_READ, "u1", "alpaca")
    assert len(spy.calls) == n   # sin tenant -> no audita
