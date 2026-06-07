"""
B4.2 — Tests del BillingProvider (Stripe + Fake) y el mapeo de status.

Puro: sin red. La verificación de firma del webhook se prueba computando una
firma Stripe válida offline (mismo esquema HMAC que usa construct_event).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from borsenhirn.billing import (
    StripeBillingProvider,
    FakeBillingProvider,
    BillingError,
    build_billing_provider_from_env,
    stripe_status_to_tenant_status,
)

WH_SECRET = "whsec_test_b4"


def _stripe_sig(payload: bytes, secret: str, *, ts: int | None = None) -> str:
    ts = ts or int(time.time())
    signed = f"{ts}.".encode() + payload
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


# ── mapeo de status ─────────────────────────────────────────────

@pytest.mark.parametrize("stripe_status,expected", [
    ("trialing", "active"),
    ("active", "active"),
    ("past_due", "suspended"),
    ("unpaid", "suspended"),
    ("canceled", "disabled"),
    ("incomplete_expired", "disabled"),
    ("algo_raro", "suspended"),   # default conservador
])
def test_status_mapping(stripe_status, expected):
    assert stripe_status_to_tenant_status(stripe_status) == expected


# ── FakeBillingProvider ─────────────────────────────────────────

def test_fake_customer_checkout_portal():
    p = FakeBillingProvider()
    cid = p.create_customer("u@x.com", "00000000-0000-0000-0000-000000000123")
    assert cid.startswith("cus_fake_")
    assert "checkout" in p.create_checkout_session(cid, "http://ok", "http://no")
    assert "portal" in p.create_portal_session(cid, "http://back")


def test_fake_parse_webhook_json():
    p = FakeBillingProvider()
    ev = p.parse_webhook(json.dumps({"type": "x", "id": "evt_1"}).encode(), "sig")
    assert ev["id"] == "evt_1"


# ── StripeBillingProvider.parse_webhook (firma real, offline) ───

def _provider() -> StripeBillingProvider:
    return StripeBillingProvider(
        secret_key="sk_test_dummy", webhook_secret=WH_SECRET, price_id="price_dummy")


def test_stripe_webhook_valid_signature():
    payload = json.dumps({"id": "evt_ok", "type": "customer.subscription.updated"}).encode()
    header = _stripe_sig(payload, WH_SECRET)
    event = _provider().parse_webhook(payload, header)
    assert event["id"] == "evt_ok"


def test_stripe_webhook_bad_signature():
    payload = json.dumps({"id": "evt_bad"}).encode()
    header = _stripe_sig(payload, "whsec_OTRO_secret")   # firmado con otro secret
    with pytest.raises(BillingError):
        _provider().parse_webhook(payload, header)


def test_stripe_webhook_tampered_payload():
    payload = json.dumps({"id": "evt_x"}).encode()
    header = _stripe_sig(payload, WH_SECRET)
    tampered = json.dumps({"id": "evt_x", "hacked": True}).encode()
    with pytest.raises(BillingError):
        _provider().parse_webhook(tampered, header)


def test_stripe_constructor_validates_config():
    with pytest.raises(ValueError):
        StripeBillingProvider("", WH_SECRET, "price_x")
    with pytest.raises(ValueError):
        StripeBillingProvider("sk", "", "price_x")
    with pytest.raises(ValueError):
        StripeBillingProvider("sk", WH_SECRET, "")


# ── factory ─────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for v in ("BILLING_PROVIDER", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_ID"):
        monkeypatch.delenv(v, raising=False)
    yield


def test_factory_fake_default():
    assert build_billing_provider_from_env().name == "fake"


def test_factory_stripe(monkeypatch):
    monkeypatch.setenv("BILLING_PROVIDER", "stripe")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WH_SECRET)
    monkeypatch.setenv("STRIPE_PRICE_ID", "price_x")
    assert build_billing_provider_from_env().name == "stripe"


def test_factory_unknown(monkeypatch):
    monkeypatch.setenv("BILLING_PROVIDER", "paypal")
    with pytest.raises(ValueError):
        build_billing_provider_from_env()
