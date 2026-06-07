"""
api/main.py — FastAPI wrapper del trading bot.

Endpoints públicos: /, /status, /signal, /health.
Endpoints autenticados (B3, Clerk JWT -> tenant): /me, /me/trades/count.
  - `Depends(get_current_tenant)` verifica el JWT, resuelve/provisiona el
    tenant, y devuelve el tenant_id; los handlers corren queries bajo el
    RLS context con ese tenant.
"""
import logging
from datetime import datetime, timezone
from fastapi import FastAPI, Depends, Request, HTTPException
from pydantic import BaseModel
import borsenhirn.db as bdb
import os
from borsenhirn.auth.deps import (
    get_current_tenant, get_active_tenant, get_tenant_manager,
)
from borsenhirn.billing import get_billing_provider, BillingError, apply_stripe_event
# NOTA: core.cache (redis) y core.database (sqlalchemy) se importan LAZY dentro
# de los endpoints que los usan (/status, /signal). Así la API — y en especial
# los endpoints de auth /me — se importan y corren aunque esas libs no estén
# instaladas (solo usan psycopg2/bdb).

logger = logging.getLogger(__name__)
app = FastAPI(title="Börsenhirn API", version="1.0.0")


class ExternalSignal(BaseModel):
    symbol: str
    source: str        # m1_research / m3_risk / m4_whale
    signal_type: str   # bullish / bearish / risk_high / whale_buy
    score: float = 0.5
    metadata: dict = {}


@app.get("/")
def root():
    return {"name": "Börsenhirn", "version": "1.0.0", "status": "online"}


@app.get("/status")
def get_status():
    """Estado actual del bot y la plataforma."""
    from borsenhirn.core.cache import get_bot_status, is_available
    from borsenhirn.core.database import test_connection
    return {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "postgres":   test_connection(),
        "redis":      is_available(),
        "bot_status": get_bot_status(),
    }


@app.post("/signal")
def receive_signal(signal: ExternalSignal):
    """Recibe señal externa de M1, M3 o M4 y la cachea para el bot."""
    from borsenhirn.core.cache import cache_signal
    cache_signal(signal.symbol, signal.source, signal.dict())
    logger.info(f"[API] Señal recibida: {signal.source} → {signal.symbol} ({signal.signal_type})")
    return {"status": "ok", "message": f"Señal guardada para {signal.symbol}"}


@app.get("/me")
def me(tenant_id: str = Depends(get_current_tenant)):
    """Devuelve el tenant del usuario autenticado (provisionado lazy en B3)."""
    return {"tenant_id": tenant_id}


@app.get("/me/trades/count")
def my_trades_count(tenant_id: str = Depends(get_active_tenant)):
    """Cuenta los trades del tenant — requiere suscripción activa (gating B4.5)."""
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM bot_trade_outcomes")
            n = cur.fetchone()[0]
    return {"tenant_id": tenant_id, "trades": n}


@app.post("/billing/checkout")
def billing_checkout(
    tenant_id: str = Depends(get_current_tenant),
    provider=Depends(get_billing_provider),
    tm=Depends(get_tenant_manager),
):
    """Crea una Checkout Session de Stripe. Accesible aun si está suspendido."""
    tenant = tm.get_tenant(tenant_id)
    cid = tm.get_stripe_customer_id(tenant_id)
    if not cid:
        cid = provider.create_customer(tenant.email, tenant_id)
        tm.set_billing(tenant_id, customer_id=cid)
    trial = os.getenv("STRIPE_TRIAL_DAYS")
    trial_days = int(trial) if trial and trial.isdigit() else None
    url = provider.create_checkout_session(
        cid,
        os.getenv("BILLING_SUCCESS_URL", "https://app.borsenhirn.local/billing/ok"),
        os.getenv("BILLING_CANCEL_URL", "https://app.borsenhirn.local/billing/cancel"),
        trial_days=trial_days,
    )
    return {"url": url}


@app.post("/billing/portal")
def billing_portal(
    tenant_id: str = Depends(get_current_tenant),
    provider=Depends(get_billing_provider),
    tm=Depends(get_tenant_manager),
):
    """Crea una Billing Portal Session para gestionar/cancelar la suscripción."""
    cid = tm.get_stripe_customer_id(tenant_id)
    if not cid:
        raise HTTPException(status_code=409, detail="el tenant no tiene customer de Stripe")
    url = provider.create_portal_session(
        cid, os.getenv("BILLING_PORTAL_RETURN_URL", "https://app.borsenhirn.local/billing"))
    return {"url": url}


@app.get("/me/audit")
def my_audit(tenant_id: str = Depends(get_current_tenant), limit: int = 50):
    """Lista el audit log del tenant autenticado (su propia traza, bajo RLS)."""
    limit = max(1, min(int(limit), 200))
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, actor, action, resource, at, metadata "
                "FROM audit_log ORDER BY at DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
    return {"tenant_id": tenant_id, "events": [
        {"id": r[0], "actor": r[1], "action": r[2], "resource": r[3],
         "at": r[4].isoformat() if r[4] else None, "metadata": r[5]}
        for r in rows]}


@app.post("/webhooks/stripe")
async def stripe_webhook(
    request: Request,
    provider=Depends(get_billing_provider),
    tm=Depends(get_tenant_manager),
):
    """Webhook de Stripe: verifica firma y sincroniza tenant.status (B4.3)."""
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = provider.parse_webhook(payload, sig)
    except BillingError:
        raise HTTPException(status_code=400, detail="webhook inválido")
    return apply_stripe_event(event, tm)


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("borsenhirn.api.main:app", host="0.0.0.0", port=8000, reload=True)
