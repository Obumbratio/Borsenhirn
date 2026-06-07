"""
B4.3 — Tests del sync de webhook (apply_stripe_event) + el endpoint
/webhooks/stripe. Sin DB ni red (FakeTM + FakeBillingProvider).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from borsenhirn.billing import apply_stripe_event, get_billing_provider, FakeBillingProvider
from borsenhirn.auth import deps as auth_deps

TID = "00000000-0000-0000-0000-0000000000c1"
KNOWN_CUSTOMER = "cus_known"


class _FakeTenant:
    def __init__(self, tid):
        self.tenant_id = tid


class _FakeTM:
    def __init__(self):
        self.calls = []
    def get_tenant_by_stripe_customer_id(self, cid):
        return _FakeTenant(TID) if cid == KNOWN_CUSTOMER else None
    def set_billing(self, tenant_id, **kw):
        self.calls.append((tenant_id, kw))


def _sub_event(status, *, etype="customer.subscription.updated",
               customer=KNOWN_CUSTOMER, sub_id="sub_1", price="price_x"):
    return {
        "type": etype,
        "data": {"object": {
            "id": sub_id, "customer": customer, "status": status,
            "items": {"data": [{"price": {"id": price}}]},
            "current_period_end": 1_900_000_000,
        }},
    }


# ── apply_stripe_event (sync) ───────────────────────────────────

@pytest.mark.parametrize("stripe_status,tenant_status", [
    ("active", "active"),
    ("trialing", "active"),
    ("past_due", "suspended"),
    ("canceled", "disabled"),
])
def test_apply_sets_status(stripe_status, tenant_status):
    tm = _FakeTM()
    res = apply_stripe_event(_sub_event(stripe_status), tm)
    assert res["handled"] is True
    assert res["tenant_status"] == tenant_status
    assert tm.calls and tm.calls[0][0] == TID
    assert tm.calls[0][1]["status"] == tenant_status
    assert tm.calls[0][1]["subscription_id"] == "sub_1"
    assert tm.calls[0][1]["plan"] == "price_x"


def test_apply_unknown_customer_not_handled():
    tm = _FakeTM()
    res = apply_stripe_event(_sub_event("active", customer="cus_desconocido"), tm)
    assert res["handled"] is False
    assert not tm.calls


def test_apply_ignored_event_type():
    tm = _FakeTM()
    res = apply_stripe_event({"type": "invoice.paid", "data": {"object": {}}}, tm)
    assert res["handled"] is False
    assert not tm.calls


# ── endpoint /webhooks/stripe (app real) ────────────────────────

@pytest.fixture
def client():
    from borsenhirn.api.main import app
    fake_tm = _FakeTM()
    app.dependency_overrides[get_billing_provider] = lambda: FakeBillingProvider()
    app.dependency_overrides[auth_deps.get_tenant_manager] = lambda: fake_tm
    try:
        c = TestClient(app)
        c._fake_tm = fake_tm   # type: ignore[attr-defined]
        yield c
    finally:
        app.dependency_overrides.clear()


def test_webhook_endpoint_syncs(client):
    body = json.dumps(_sub_event("active")).encode()
    r = client.post("/webhooks/stripe", content=body,
                    headers={"stripe-signature": "t=1,v1=x"})
    assert r.status_code == 200
    assert r.json()["handled"] is True
    assert r.json()["tenant_status"] == "active"
    assert client._fake_tm.calls  # set_billing fue llamado


def test_webhook_endpoint_ignored_event_200(client):
    body = json.dumps({"type": "invoice.paid", "data": {"object": {}}}).encode()
    r = client.post("/webhooks/stripe", content=body,
                    headers={"stripe-signature": "t=1,v1=x"})
    assert r.status_code == 200
    assert r.json()["handled"] is False
