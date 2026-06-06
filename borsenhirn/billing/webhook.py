"""
Sincronización de eventos de Stripe -> estado del tenant (B4.3).

`apply_stripe_event` toma un evento YA VERIFICADO (firma chequeada por el
provider) y actualiza el tenant: mapea el estado de la suscripción a
`tenants.status` y guarda subscription_id / plan / current_period_end.

Idempotente en la práctica: `set_billing` solo fija el estado actual, así que
reprocesar el mismo evento (o uno viejo) converge al estado de la suscripción.
La firma se verifica antes, en el provider; acá ya confiamos en el evento.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from borsenhirn.billing.provider import stripe_status_to_tenant_status

_SUB_EVENTS = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}


def _extract_plan(sub_obj: Dict[str, Any]):
    try:
        return sub_obj["items"]["data"][0]["price"]["id"]
    except (KeyError, IndexError, TypeError):
        return None


def apply_stripe_event(event: Dict[str, Any], tm) -> Dict[str, Any]:
    """
    Aplica un evento de Stripe al tenant. Devuelve un dict-resumen.
    `tm` es un TenantManager (o compatible) con get_tenant_by_stripe_customer_id
    y set_billing.
    """
    etype = event.get("type", "")
    obj = (event.get("data") or {}).get("object") or {}

    if etype not in _SUB_EVENTS:
        return {"handled": False, "reason": f"evento ignorado: {etype}"}

    customer_id = obj.get("customer")
    if not customer_id:
        return {"handled": False, "reason": "evento sin customer"}

    tenant = tm.get_tenant_by_stripe_customer_id(customer_id)
    if not tenant:
        return {"handled": False, "reason": "tenant no encontrado", "customer": customer_id}

    sub_status = obj.get("status")
    new_status = stripe_status_to_tenant_status(sub_status) if sub_status else None
    cpe = obj.get("current_period_end")
    cpe_dt = datetime.fromtimestamp(cpe, tz=timezone.utc) if cpe else None

    tm.set_billing(
        tenant.tenant_id,
        subscription_id=obj.get("id"),
        status=new_status,
        plan=_extract_plan(obj),
        current_period_end=cpe_dt,
    )
    return {
        "handled": True,
        "tenant_id": tenant.tenant_id,
        "stripe_status": sub_status,
        "tenant_status": new_status,
    }


__all__ = ["apply_stripe_event"]
