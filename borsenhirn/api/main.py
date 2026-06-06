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
from borsenhirn.auth.deps import get_current_tenant, get_tenant_manager
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
def my_trades_count(tenant_id: str = Depends(get_current_tenant)):
    """Cuenta los trades del tenant autenticado — corre bajo RLS context."""
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM bot_trade_outcomes")
            n = cur.fetchone()[0]
    return {"tenant_id": tenant_id, "trades": n}


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
