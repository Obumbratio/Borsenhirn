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
from fastapi import FastAPI, Depends, Request, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import borsenhirn.db as bdb
import os
from borsenhirn.auth.deps import (
    get_current_tenant, get_active_tenant, get_tenant_manager,
)
from borsenhirn.billing import get_billing_provider, BillingError, apply_stripe_event
from borsenhirn.legal import (
    current_versions, record_acceptance, get_acceptances, is_compliant,
    get_compliant_tenant,
)
# NOTA: core.cache (redis) y core.database (sqlalchemy) se importan LAZY dentro
# de los endpoints que los usan (/status, /signal). Así la API — y en especial
# los endpoints de auth /me — se importan y corren aunque esas libs no estén
# instaladas (solo usan psycopg2/bdb).

logger = logging.getLogger(__name__)
app = FastAPI(title="Börsenhirn API", version="1.0.0")

# CORS: el frontend (Next, otro origen/puerto) hace fetch client-side con header
# Authorization → el browser manda un preflight OPTIONS. Sin esto, OPTIONS da 405
# y el browser bloquea la respuesta ("Failed to fetch"). Orígenes configurables por
# env (CORS_ALLOW_ORIGINS, coma-separado); default = los del dev local.
_cors_origins = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOW_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ── Conectar broker (BYO Alpaca, paper-first) — Paso 3a ──────────────────────
class BrokerCreds(BaseModel):
    api_key: str
    api_secret: str


def _credential_store(tenant_id: str, conn):
    """CredentialStore (vault B2) scoped al tenant. Cifra en reposo; la plataforma
    nunca custodia dinero, solo guarda las keys del user para que ÉL ejecute."""
    from borsenhirn.security import CredentialStore, Vault
    return CredentialStore(lambda: conn, Vault.from_provider(), tenant_id=tenant_id)


@app.post("/me/broker")
def connect_broker(body: BrokerCreds, tenant_id: str = Depends(get_current_tenant)):
    """
    Conecta la cuenta Alpaca (PAPER) del usuario: valida las keys contra Alpaca y,
    si sirven, las guarda cifradas en el vault (BYO broker). NO custodiamos dinero.
    """
    from execution import Executor
    try:
        acc = Executor(api_key=body.api_key, secret_key=body.api_secret,
                       paper=True).get_account()
    except Exception:
        acc = None
    if not acc:
        raise HTTPException(status_code=400,
                            detail="no pude validar las credenciales con Alpaca (paper)")
    with bdb.get_conn(role="app") as conn:
        _credential_store(tenant_id, conn).set(tenant_id, "alpaca", body.api_key, body.api_secret)
    return {"connected": True, "provider": "alpaca", "equity": acc.get("equity")}


@app.get("/me/broker")
def broker_status(tenant_id: str = Depends(get_current_tenant)):
    """¿Hay Alpaca conectado? Devuelve estado + key ENMASCARADA (nunca el secreto)."""
    creds = None
    with bdb.get_conn(role="app") as conn:
        try:
            creds = _credential_store(tenant_id, conn).get(tenant_id, "alpaca")
        except Exception as exc:   # master key/desencriptado: no exponer detalle
            logger.warning("broker_status get falló: %s", exc)
    if not creds:
        return {"connected": False, "provider": "alpaca"}
    k = creds.api_key
    masked = (k[:4] + "…" + k[-4:]) if len(k) > 8 else "…"
    return {"connected": True, "provider": "alpaca", "api_key_masked": masked}


@app.delete("/me/broker")
def disconnect_broker(tenant_id: str = Depends(get_current_tenant)):
    """Desconecta Alpaca: borra las credenciales del vault."""
    with bdb.get_conn(role="app") as conn:
        ok = _credential_store(tenant_id, conn).delete(tenant_id, "alpaca")
    return {"connected": False, "deleted": bool(ok)}


# ── Ejecución MANUAL (el usuario aprieta cada orden) — Paso 3d ───────────────
class OrderRequest(BaseModel):
    symbol: str
    side: str                 # "buy" | "sell"
    qty: int
    mode: str = "paper"       # paper-first; "live" requiere opt-in explícito (no habilitado)
    idempotency_key: str      # uuid del front, uno por click → dedup en Alpaca (client_order_id)


def _user_executor(tenant_id: str):
    """Executor con las creds del PROPIO user (vault B2), paper. 409 si no conectó."""
    creds = None
    with bdb.get_conn(role="app") as conn:
        try:
            creds = _credential_store(tenant_id, conn).get(tenant_id, "alpaca")
        except Exception as exc:
            logger.warning("user_executor: vault get falló: %s", exc)
    if not creds:
        raise HTTPException(status_code=409,
                            detail="conectá tu cuenta de Alpaca primero (POST /me/broker)")
    from execution import Executor
    return Executor(api_key=creds.api_key, secret_key=creds.api_secret, paper=True)


@app.post("/me/orders")
def place_order(body: OrderRequest, tenant_id: str = Depends(get_compliant_tenant)):
    """
    Ejecuta UNA orden — solo cuando el usuario la dispara (el botón). Sin loops,
    sin auto-submit. Usa las creds del PROPIO user (BYO), paper-first. Idempotente
    por `idempotency_key` (= client_order_id de Alpaca). Gating fuerte
    (`get_compliant_tenant`: suscripción activa + legal aceptado).
    """
    import config
    symbol = (body.symbol or "").strip().upper()
    side = (body.side or "").strip().lower()

    # ── Validaciones pre-envío ──
    if not symbol or not symbol.isalpha() or len(symbol) > 6:
        raise HTTPException(status_code=400, detail="símbolo inválido")
    if side not in ("buy", "sell"):
        raise HTTPException(status_code=400, detail="side debe ser 'buy' o 'sell'")
    if not isinstance(body.qty, int) or body.qty <= 0:
        raise HTTPException(status_code=400, detail="qty debe ser un entero > 0")
    max_qty = int(getattr(config, "SANITY_MAX_QTY_PER_ORDER", 10000))
    if body.qty > max_qty:
        raise HTTPException(status_code=400,
                            detail=f"qty {body.qty} supera el tope de sanidad ({max_qty})")
    if not body.idempotency_key or len(body.idempotency_key) > 128:
        raise HTTPException(status_code=400, detail="idempotency_key requerida (uuid)")
    # ── Paper-first: live exige opt-in explícito (no habilitado en 3d) ──
    if body.mode != "paper":
        raise HTTPException(status_code=403,
                            detail="trading real no habilitado (paper-first); live requiere opt-in explícito")

    ex = _user_executor(tenant_id)
    coid = body.idempotency_key
    meta = {"symbol": symbol, "side": side, "qty": body.qty, "mode": "paper"}

    # ── Idempotencia: ¿ya hay una orden con ese client_order_id? ──
    existing = ex.get_order_by_client_order_id(coid)
    if existing:
        return {**existing, **meta, "idempotent": True}

    # ── Mandar UNA orden; si Alpaca rechaza → 502 (sin crash) ──
    try:
        res = ex.place_order(symbol, body.qty, side, client_order_id=coid)
    except Exception as exc:
        # ¿rechazo por client_order_id duplicado (doble click en carrera)? → devolver la existente
        dup = ex.get_order_by_client_order_id(coid)
        if dup:
            return {**dup, **meta, "idempotent": True}
        raise HTTPException(status_code=502, detail=f"Alpaca rechazó la orden: {exc}")

    # ── Auditar (B5) ──
    try:
        from borsenhirn.audit import get_audit_logger
        get_audit_logger().record(tenant_id, "order.submit", resource=symbol,
                                  metadata={**meta, "order_id": res.get("order_id")})
    except Exception:
        pass
    return {**res, **meta, "idempotent": False}


@app.get("/me/positions")
def my_positions(tenant_id: str = Depends(get_active_tenant)):
    """
    Posiciones del usuario + alertas TP/SL (ALERTA + botón). READ-ONLY: NO ejecuta.
    Cada alerta describe el escenario y pre-llena un `sugerido`; ejecutar = el user
    aprieta POST /me/orders. Nunca dice "vendé" ni auto-ejecuta.
    """
    from borsenhirn.signals.exits import position_alerts
    ex = _user_executor(tenant_id)
    out = []
    for p in ex.get_positions():
        qty = p.get("qty") or 0.0
        avg = p.get("avg_entry_price") or 0.0
        current = (p.get("market_value", 0.0) / qty) if qty else 0.0
        pnl_pct = ((current - avg) / avg * 100) if avg else 0.0
        out.append({
            "symbol": p.get("symbol"),
            "qty": qty,
            "avg_entry": round(avg, 2),
            "current": round(current, 2),
            "pnl_pct": round(pnl_pct, 2),
            "alertas": position_alerts(symbol=p.get("symbol"), qty=qty,
                                       avg_entry=avg, current=current),
        })
    return {"positions": out}


class LegalAccept(BaseModel):
    document: str   # 'terms' | 'privacy'
    version: str


@app.get("/legal/current")
def legal_current():
    """Versiones vigentes de los documentos legales (público)."""
    return {"versions": current_versions(),
            "documents": {"terms": "legal/TERMS.md", "privacy": "legal/PRIVACY.md",
                          "disclaimer": "legal/DISCLAIMER.md"}}


@app.post("/me/legal/accept")
def legal_accept(body: LegalAccept, tenant_id: str = Depends(get_current_tenant)):
    """Registra la aceptación de un documento legal (versión vigente)."""
    cur = current_versions()
    if body.document not in cur:
        raise HTTPException(status_code=400, detail="documento desconocido")
    if body.version != cur[body.document]:
        raise HTTPException(
            status_code=409,
            detail=f"versión no vigente (actual: {cur[body.document]})")
    actor = "system"
    try:
        from borsenhirn.audit import get_actor
        actor = get_actor()
    except Exception:
        pass
    record_acceptance(tenant_id, body.document, body.version, actor=actor)
    return {"ok": True, "compliant": is_compliant(tenant_id)}


@app.get("/me/legal")
def my_legal(tenant_id: str = Depends(get_current_tenant)):
    """Qué aceptó el tenant + si está al día con las versiones vigentes."""
    return {"current": current_versions(),
            "accepted": get_acceptances(tenant_id),
            "compliant": is_compliant(tenant_id)}


@app.get("/me/trades/count")
def my_trades_count(tenant_id: str = Depends(get_compliant_tenant)):
    """Cuenta los trades — requiere suscripción activa Y aceptación legal (B4.5/B7)."""
    with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM bot_trade_outcomes")
            n = cur.fetchone()[0]
    return {"tenant_id": tenant_id, "trades": n}


@app.get("/signals")
def signals(tenant_id: str = Depends(get_active_tenant)):
    """
    Señal/análisis IMPERSONAL (igual para TODOS los usuarios). Nace CERRADO:
    requiere auth (Clerk) + suscripción activa (`get_active_tenant`). El contenido
    NO depende del tenant — es el cerebro compartido (modelo global + score neutral,
    Opción C). El `tenant_id` se usa solo para gatear el acceso, no para personalizar.
    Ver docs/RESECUENCIACION_PLAN.md (Paso 2).
    """
    from borsenhirn.signals.client_feed import get_client_signals
    return get_client_signals()


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


@app.get("/me/export")
def my_export(tenant_id: str = Depends(get_current_tenant)):
    """Exporta todos los datos del tenant (portabilidad/GDPR, B9). Bajo RLS."""
    from borsenhirn.backups import export_tenant
    return export_tenant(tenant_id)


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


def _require_admin(x_admin_key: str | None) -> None:
    """Auth admin por API key (B8). 403 si falta/no coincide o si está deshabilitado."""
    import config
    if not config.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="admin API deshabilitada (sin ADMIN_API_KEY)")
    if not x_admin_key or x_admin_key != config.ADMIN_API_KEY:
        raise HTTPException(status_code=403, detail="X-Admin-Key inválida")


@app.get("/admin/killswitch/global")
def admin_global_status(x_admin_key: str = Header(default=None)):
    _require_admin(x_admin_key)
    from borsenhirn.safety.global_killswitch import is_global_halt
    return {"global_halt": is_global_halt()}


@app.post("/admin/killswitch/global")
def admin_global_halt(reason: str = "", x_admin_key: str = Header(default=None)):
    """Activa el kill-switch GLOBAL (para a TODOS los tenants)."""
    _require_admin(x_admin_key)
    from borsenhirn.safety.global_killswitch import trip_global, is_global_halt
    trip_global(reason or "manual admin halt", actor="admin")
    return {"global_halt": is_global_halt()}


@app.post("/admin/killswitch/global/clear")
def admin_global_clear(note: str = "", x_admin_key: str = Header(default=None)):
    _require_admin(x_admin_key)
    from borsenhirn.safety.global_killswitch import clear_global, is_global_halt
    clear_global(note, actor="admin")
    return {"global_halt": is_global_halt()}


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("borsenhirn.api.main:app", host="0.0.0.0", port=8000, reload=True)
