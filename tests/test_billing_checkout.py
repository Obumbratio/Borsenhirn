"""
B4.4 — Tests de los endpoints /billing/checkout y /billing/portal.
App real + FakeBillingProvider + FakeTM (sin DB ni red).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient

from borsenhirn.billing import get_billing_provider, FakeBillingProvider
from borsenhirn.auth import deps as auth_deps
from borsenhirn.auth.verifier import StaticTokenVerifier

SECRET = "secret-b4-checkout"
TID = "00000000-0000-0000-0000-0000000000c1"


class _FakeTenant:
    def __init__(self, tid, email="u@x.com", status="active"):
        self.tenant_id = tid
        self.email = email
        self.status = status


class _FakeTM:
    def __init__(self, customer=None):
        self.customer = customer
        self.set_calls = []
    # para get_current_tenant
    def provision_for_clerk_user(self, sub, email, name):
        return _FakeTenant(TID)
    # para los endpoints de billing
    def get_tenant(self, tid):
        return _FakeTenant(tid)
    def get_stripe_customer_id(self, tid):
        return self.customer
    def set_billing(self, tid, **kw):
        self.set_calls.append(kw)
        if "customer_id" in kw:
            self.customer = kw["customer_id"]


def _token():
    return jwt.encode(
        {"sub": "user_co", "exp": datetime.now(timezone.utc) + timedelta(seconds=60)},
        SECRET, algorithm="HS256")


def _client(tm):
    from borsenhirn.api.main import app
    app.dependency_overrides[auth_deps.get_verifier] = lambda: StaticTokenVerifier(SECRET)
    app.dependency_overrides[auth_deps.get_tenant_manager] = lambda: tm
    app.dependency_overrides[get_billing_provider] = lambda: FakeBillingProvider()
    c = TestClient(app)
    return app, c


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    from borsenhirn.api.main import app
    app.dependency_overrides.clear()


def test_checkout_creates_customer_and_returns_url():
    tm = _FakeTM(customer=None)   # sin customer todavía
    _, c = _client(tm)
    r = c.post("/billing/checkout", headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200
    assert "url" in r.json() and r.json()["url"].startswith("https://")
    # creó y guardó el customer
    assert any("customer_id" in k for k in tm.set_calls)


def test_checkout_reuses_existing_customer():
    tm = _FakeTM(customer="cus_existing")
    _, c = _client(tm)
    r = c.post("/billing/checkout", headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200
    # ya tenía customer → no re-crea (no set_billing con customer_id)
    assert not any("customer_id" in k for k in tm.set_calls)


def test_portal_without_customer_409():
    tm = _FakeTM(customer=None)
    _, c = _client(tm)
    r = c.post("/billing/portal", headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 409


def test_portal_with_customer_ok():
    tm = _FakeTM(customer="cus_existing")
    _, c = _client(tm)
    r = c.post("/billing/portal", headers={"Authorization": f"Bearer {_token()}"})
    assert r.status_code == 200
    assert "url" in r.json()


def test_checkout_requires_auth():
    tm = _FakeTM()
    _, c = _client(tm)
    assert c.post("/billing/checkout").status_code == 401
