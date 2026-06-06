"""
borsenhirn.billing — integración de pagos (Stripe) para el SaaS (B4).

Capa pluggable: un `BillingProvider` que crea customers / checkout / portal y
verifica webhooks. `StripeBillingProvider` (real) y `FakeBillingProvider`
(dev/tests sin red).
"""

from borsenhirn.billing.provider import (
    BillingProvider,
    BillingError,
    StripeBillingProvider,
    FakeBillingProvider,
    build_billing_provider_from_env,
    stripe_status_to_tenant_status,
)

__all__ = [
    "BillingProvider",
    "BillingError",
    "StripeBillingProvider",
    "FakeBillingProvider",
    "build_billing_provider_from_env",
    "stripe_status_to_tenant_status",
]
