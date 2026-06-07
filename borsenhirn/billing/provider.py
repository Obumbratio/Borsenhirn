"""
BillingProvider — abstracción de pagos (Stripe). Pluggable (B4).

    StripeBillingProvider -> usa el SDK `stripe` (producción).
    FakeBillingProvider   -> dev/tests sin red.

El webhook se verifica SIEMPRE por firma antes de confiar en el evento.
El mapeo `subscription.status` (Stripe) -> `tenants.status` vive acá.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


class BillingError(Exception):
    """Fallo de billing (webhook inválido, API de Stripe, config)."""


# Mapeo Stripe subscription.status -> tenants.status (CHECK: active/suspended/disabled/deleted)
_STATUS_MAP = {
    "trialing": "active",
    "active": "active",
    "past_due": "suspended",
    "unpaid": "suspended",
    "incomplete": "suspended",
    "paused": "suspended",
    "incomplete_expired": "disabled",
    "canceled": "disabled",
}


def stripe_status_to_tenant_status(stripe_status: str) -> str:
    """Traduce el estado de la suscripción de Stripe al status del tenant."""
    return _STATUS_MAP.get(stripe_status, "suspended")  # default conservador


@runtime_checkable
class BillingProvider(Protocol):
    name: str

    def create_customer(self, email: str, tenant_id: str) -> str: ...
    def create_checkout_session(
        self, customer_id: str, success_url: str, cancel_url: str,
        *, trial_days: Optional[int] = None,
    ) -> str: ...
    def create_portal_session(self, customer_id: str, return_url: str) -> str: ...
    def parse_webhook(self, payload: bytes, sig_header: str) -> dict: ...


class StripeBillingProvider:
    """Provider real sobre el SDK `stripe`."""
    name = "stripe"

    def __init__(self, secret_key: str, webhook_secret: str, price_id: str) -> None:
        if not secret_key:
            raise ValueError("StripeBillingProvider requiere secret_key")
        if not webhook_secret:
            raise ValueError("StripeBillingProvider requiere webhook_secret")
        if not price_id:
            raise ValueError("StripeBillingProvider requiere price_id")
        import stripe
        self._stripe = stripe
        self._stripe.api_key = secret_key
        self.webhook_secret = webhook_secret
        self.price_id = price_id

    def create_customer(self, email: str, tenant_id: str) -> str:
        try:
            c = self._stripe.Customer.create(
                email=email, metadata={"tenant_id": tenant_id})
        except Exception as exc:
            raise BillingError(f"create_customer: {exc}") from exc
        return c.id

    def create_checkout_session(
        self, customer_id: str, success_url: str, cancel_url: str,
        *, trial_days: Optional[int] = None,
    ) -> str:
        params: dict[str, Any] = dict(
            customer=customer_id, mode="subscription",
            line_items=[{"price": self.price_id, "quantity": 1}],
            success_url=success_url, cancel_url=cancel_url,
        )
        if trial_days:
            params["subscription_data"] = {"trial_period_days": trial_days}
        try:
            s = self._stripe.checkout.Session.create(**params)
        except Exception as exc:
            raise BillingError(f"create_checkout_session: {exc}") from exc
        return s.url

    def create_portal_session(self, customer_id: str, return_url: str) -> str:
        try:
            s = self._stripe.billing_portal.Session.create(
                customer=customer_id, return_url=return_url)
        except Exception as exc:
            raise BillingError(f"create_portal_session: {exc}") from exc
        return s.url

    def parse_webhook(self, payload: bytes, sig_header: str) -> dict:
        try:
            event = self._stripe.Webhook.construct_event(
                payload, sig_header, self.webhook_secret)
        except Exception as exc:
            # ValueError (payload) o SignatureVerificationError
            raise BillingError(f"webhook inválido: {exc}") from exc
        return event


class FakeBillingProvider:
    """Provider de dev/tests: sin red. Devuelve valores deterministas."""
    name = "fake"

    def __init__(self, webhook_secret: str = "whsec_fake") -> None:
        self.webhook_secret = webhook_secret
        self.customers: dict[str, str] = {}

    def create_customer(self, email: str, tenant_id: str) -> str:
        cid = f"cus_fake_{tenant_id.replace('-', '')[:12]}"
        self.customers[tenant_id] = cid
        return cid

    def create_checkout_session(
        self, customer_id: str, success_url: str, cancel_url: str,
        *, trial_days: Optional[int] = None,
    ) -> str:
        return f"https://fake.stripe.test/checkout/{customer_id}"

    def create_portal_session(self, customer_id: str, return_url: str) -> str:
        return f"https://fake.stripe.test/portal/{customer_id}"

    def parse_webhook(self, payload: bytes, sig_header: str) -> dict:
        import json
        # Dev: sin verificación de firma real (no usar en prod).
        try:
            return json.loads(payload)
        except Exception as exc:
            raise BillingError(f"payload inválido: {exc}") from exc


def build_billing_provider_from_env() -> BillingProvider:
    """
    Construye el provider según env:
        BILLING_PROVIDER=stripe -> StripeBillingProvider (STRIPE_SECRET_KEY,
                                   STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_ID)
        BILLING_PROVIDER=fake   -> FakeBillingProvider (default; dev/tests)
    """
    import os
    kind = (os.getenv("BILLING_PROVIDER") or "fake").lower()
    if kind == "stripe":
        return StripeBillingProvider(
            secret_key=os.environ.get("STRIPE_SECRET_KEY", ""),
            webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET", ""),
            price_id=os.environ.get("STRIPE_PRICE_ID", ""),
        )
    if kind == "fake":
        return FakeBillingProvider(
            webhook_secret=os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_fake"))
    raise ValueError(f"BILLING_PROVIDER desconocido: {kind!r}")


# Singleton lazy (para usar como FastAPI dependency).
_provider: Optional[BillingProvider] = None


def get_billing_provider() -> BillingProvider:
    global _provider
    if _provider is None:
        _provider = build_billing_provider_from_env()
    return _provider


def reset_billing_provider() -> None:
    global _provider
    _provider = None


__all__ = [
    "BillingProvider",
    "BillingError",
    "StripeBillingProvider",
    "FakeBillingProvider",
    "build_billing_provider_from_env",
    "get_billing_provider",
    "reset_billing_provider",
    "stripe_status_to_tenant_status",
]
