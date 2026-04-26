"""
bot_api.py — FastAPI wrapper para el Trading Bot de Börsenhirn.
v1.2.0 — Fixes: regime en /status, nuevo /trades/list con formato correcto

Endpoints:
    GET  /             — info del servicio
    GET  /status       — estado completo del bot + regime real
    GET  /performance  — resumen de performance
    GET  /performance/history — historial diario con filas crudas (para graficas)
    GET  /trades       — estadísticas de trades (win/loss summary)
    GET  /trades/list  — lista de trades con formato correcto para dashboard
    GET  /health       — health check
    GET  /portfolio    — portfolio history de Alpaca
    POST /cycle        — forzar un ciclo manualmente
    POST /signal       — inyectar señal externa
    DELETE /signal/{s} — eliminar señal
    GET  /signals      — listar señales activas
"""

import logging
import threading
from datetime import datetime, timezone, date
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from bot_memory_pg import BotMemory
from logger import setup_logging
import config

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Börsenhirn — Bot API",
    description="API del Trading Bot para integración con módulos Börsenhirn",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Estado global ─────────────────────────────────────────────────────────────
_bot_state = {
    "running":           False,
    "mode":              "paper",
    "last_cycle":        None,
    "current_cycle":     False,
    "external_signals":  {},
    "started_at":        None,
    "last_regime":       {},
    "regime_updated_at": None,
}
_state_lock = threading.Lock()

# Recalcular régimen máximo cada 30 minutos
REGIME_CACHE_SECONDS = 1800


# ── Modelos ───────────────────────────────────────────────────────────────────
class ExternalSignal(BaseModel):
    symbol: str
    source: str
    action: str
    confidence: float
    reason: str
    expires_in_cycles: Optional[int] = 3

class CycleRequest(BaseModel):
    force: bool = True
    symbol: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────
def _get_memory() -> BotMemory:
    return BotMemory()

def _get_trading_client(live: bool = False):
    from alpaca.trading.client import TradingClient
    if live:
        return TradingClient(config.LIVE_ALPACA_API_KEY, config.LIVE_ALPACA_SECRET_KEY, paper=False)
    return TradingClient(config.ALPACA_API_KEY, config.ALPACA_SECRET_KEY, paper=True)

def _get_regime_cached() -> dict:
    """
    Retorna el régimen de mercado con cache de 30 minutos.
    FIX: antes /status devolvía "regime": {} siempre.
    """
    with _state_lock:
        last_updated = _bot_state.get("regime_updated_at")
        cached       = _bot_state.get("last_regime", {})

    now = datetime.now(timezone.utc)

    if last_updated and cached:
        elapsed = (now - last_updated).total_seconds()
        if elapsed < REGIME_CACHE_SECONDS:
            return cached

    try:
        from data_fetcher import DataFetcher
        from market_context import get_full_context
        from regime_detector import detect_regime

        fetcher    = DataFetcher()
        market_ctx = get_full_context()
        regime     = detect_regime(fetcher, market_ctx)

        with _state_lock:
            _bot_state["last_regime"]       = regime
            _bot_state["regime_updated_at"] = now

        logger.info(f"[API] Régimen: {regime.get('regime','?')} VIX={regime.get('vix',0):.1f}")
        return regime

    except Exception as e:
        logger.warning(f"[API] No se pudo calcular régimen: {e}")
        return cached or {
            "regime": "SIDEWAYS", "confidence": 0.0, "vix": 0.0,
            "spy_trend": "FLAT", "breadth_pct": None,
            "adx": 0.0, "spy_change_pct": 0.0,
        }

def _run_single_cycle():
    with _state_lock:
        if _bot_state["current_cycle"]:
            return
        _bot_state["current_cycle"] = True
    try:
        from main import run
        run(train=False, once=True, live=(_bot_state["mode"] == "live"))
        with _state_lock:
            _bot_state["last_cycle"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        logger.error(f"[API] Error en ciclo: {e}", exc_info=True)
    finally:
        with _state_lock:
            _bot_state["current_cycle"] = False


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {"service": "Börsenhirn Bot API", "version": "1.2.0", "status": "online"}


@app.get("/status")
def get_status():
    try:
        mem     = _get_memory()
        daily   = mem.get_daily_state()
        perf    = mem.get_performance_summary(days=7)
        stats   = mem.get_win_stats(last_n=10)
        top_sym = mem.get_top_symbols(5)
        bot_sym = mem.get_bottom_symbols(3)

        account_data = {}
        try:
            client = _get_trading_client()
            acc    = client.get_account()
            eq     = float(acc.equity)
            leq    = float(acc.last_equity)
            account_data = {
                "equity":          round(eq, 2),
                "buying_power":    round(float(acc.buying_power), 2),
                "cash":            round(float(acc.cash), 2),
                "portfolio_value": round(float(acc.portfolio_value), 2),
                "day_pl":          round(eq - leq, 2),
                "day_pl_pct":      round((eq - leq) / leq * 100, 4) if leq > 0 else 0,
            }
        except Exception as e:
            logger.warning(f"[API] Cuenta Alpaca no disponible: {e}")

        # FIX: régimen real con cache, ya no es {}
        regime_data = _get_regime_cached()

        with _state_lock:
            state_copy = dict(_bot_state)
            signals    = dict(_bot_state["external_signals"])

        return {
            "bot": {
                "running":        state_copy["running"],
                "mode":           state_copy["mode"],
                "live_mode":      state_copy["mode"] == "live",
                "timeframe":      config.TIMEFRAME,
                "watchlist_size": len(config.WATCHLIST),
                "last_cycle":     state_copy["last_cycle"],
                "cycle_running":  state_copy["current_cycle"],
            },
            "account": account_data,
            "memory": {
                "trades_today":   daily["trades_today"],
                "wins_today":     daily["wins_today"],
                "losses_today":   daily["losses_today"],
                "daily_pnl":      daily.get("daily_pnl", 0),
                "open_positions": list(daily["entry_prices"].keys()),
                "open_count":     len(daily["entry_prices"]),
            },
            "regime":         regime_data,
            "performance_7d": perf,
            "last_10_trades": stats,
            "symbol_scores": {
                "top":    [{"symbol": s["symbol"], "score": float(s["score"]),
                            "wins": s["wins"], "losses": s["losses"],
                            "total_pnl": float(s["total_pnl"])} for s in top_sym],
                "bottom": [{"symbol": s["symbol"], "score": float(s["score"]),
                            "wins": s["wins"], "losses": s["losses"],
                            "total_pnl": float(s["total_pnl"])} for s in bot_sym],
            },
            "external_signals": signals,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"[API] /status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/portfolio")
def get_portfolio(period: str = "1D"):
    try:
        client = _get_trading_client()

        acc             = client.get_account()
        equity          = float(acc.equity)
        last_equity     = float(acc.last_equity)
        cash            = float(acc.cash)
        buying_power    = float(acc.buying_power)
        portfolio_value = float(acc.portfolio_value)
        day_pl          = equity - last_equity
        day_pl_pct      = (day_pl / last_equity * 100) if last_equity > 0 else 0

        positions = []
        try:
            for p in client.get_all_positions():
                cur_px = float(p.current_price) if p.current_price else 0
                positions.append({
                    "symbol":          p.symbol,
                    "qty":             float(p.qty),
                    "avg_entry":       float(p.avg_entry_price),
                    "current_price":   cur_px,
                    "market_value":    float(p.market_value),
                    "unrealized_pl":   float(p.unrealized_pl),
                    "unrealized_plpc": round(float(p.unrealized_plpc) * 100, 2),
                    "side":            str(p.side),
                })
        except Exception as e:
            logger.warning(f"[API] Posiciones no disponibles: {e}")

        equity_history = []
        try:
            from alpaca.trading.requests import GetPortfolioHistoryRequest
            timeframe_map = {
                "1D": "5Min", "1W": "1H",
                "1M": "1D",   "3M": "1D", "1Y": "1D",
            }
            tf      = timeframe_map.get(period, "5Min")
            req     = GetPortfolioHistoryRequest(period=period, timeframe=tf, extended_hours=False)
            history = client.get_portfolio_history(req)

            if history and history.timestamp:
                pl_list = history.profit_loss or [0] * len(history.timestamp)
                for ts, eq, pl in zip(history.timestamp, history.equity, pl_list):
                    if eq and float(eq) > 0:
                        equity_history.append({
                            "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                            "equity":    round(float(eq), 2),
                            "pl":        round(float(pl or 0), 2),
                        })
        except Exception as e:
            logger.warning(f"[API] Portfolio history no disponible: {e}")
            equity_history = [{
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "equity":    round(equity, 2),
                "pl":        round(day_pl, 2),
            }]

        return {
            "account": {
                "equity":          round(equity, 2),
                "last_equity":     round(last_equity, 2),
                "cash":            round(cash, 2),
                "buying_power":    round(buying_power, 2),
                "portfolio_value": round(portfolio_value, 2),
                "day_pl":          round(day_pl, 2),
                "day_pl_pct":      round(day_pl_pct, 4),
            },
            "positions":      positions,
            "equity_history": equity_history,
            "period":         period,
            "timestamp":      datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"[API] /portfolio error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trades")
def get_recent_trades(limit: int = 20):
    """Estadísticas de trades (win/loss summary). Para lista completa usar /trades/list"""
    try:
        mem   = _get_memory()
        stats = mem.get_win_stats(last_n=limit)
        return {"stats": stats, "limit": limit,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/trades/list")
def get_trades_list(limit: int = 50):
    """
    FIX: Lista de trades con formato correcto para el dashboard:
    [{action, symbol, price, qty, pnl, timestamp, reason, buy_price, win}]
    """
    try:
        mem = _get_memory()
        with mem._cur() as cur:
            cur.execute("""
                SELECT
                    created_at  AS timestamp,
                    symbol,
                    sell_price  AS price,
                    qty,
                    pnl,
                    win,
                    reason_sell AS reason,
                    buy_price
                FROM bot_trade_outcomes
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            rows = cur.fetchall()

        trades = []
        for r in rows:
            ts = r["timestamp"]
            if hasattr(ts, "isoformat"):
                ts = ts.isoformat()
            trades.append({
                "action":    "sell",
                "symbol":    r["symbol"],
                "price":     float(r["price"]),
                "qty":       int(r["qty"]),
                "pnl":       float(r["pnl"]),
                "win":       bool(r["win"]),
                "reason":    r["reason"] or "",
                "buy_price": float(r["buy_price"]),
                "timestamp": ts,
            })

        return trades

    except Exception as e:
        logger.error(f"[API] /trades/list error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cycle")
def force_cycle(request: CycleRequest, background_tasks: BackgroundTasks):
    with _state_lock:
        if _bot_state["current_cycle"]:
            return {"status": "skipped", "message": "Ciclo ya en progreso.",
                    "timestamp": datetime.now(timezone.utc).isoformat()}
    background_tasks.add_task(_run_single_cycle)
    return {"status": "queued", "message": "Ciclo encolado.",
            "timestamp": datetime.now(timezone.utc).isoformat()}


@app.post("/signal")
def inject_signal(signal: ExternalSignal):
    if signal.action not in ("buy", "sell", "hold"):
        raise HTTPException(status_code=400, detail=f"Acción inválida: {signal.action}")
    if not 0.0 <= signal.confidence <= 1.0:
        raise HTTPException(status_code=400, detail="Confidence debe estar entre 0.0 y 1.0")
    with _state_lock:
        _bot_state["external_signals"][signal.symbol] = {
            "source":            signal.source,
            "action":            signal.action,
            "confidence":        signal.confidence,
            "reason":            signal.reason,
            "expires_in_cycles": signal.expires_in_cycles,
            "cycles_remaining":  signal.expires_in_cycles,
            "injected_at":       datetime.now(timezone.utc).isoformat(),
        }
    return {"status": "accepted", "symbol": signal.symbol, "action": signal.action,
            "message": f"Señal de {signal.source} registrada.",
            "timestamp": datetime.now(timezone.utc).isoformat()}


@app.delete("/signal/{symbol}")
def clear_signal(symbol: str):
    with _state_lock:
        removed = _bot_state["external_signals"].pop(symbol, None)
    return {"status": "removed" if removed else "not_found", "symbol": symbol}


@app.get("/signals")
def list_signals():
    with _state_lock:
        return {"signals": dict(_bot_state["external_signals"]),
                "count": len(_bot_state["external_signals"]),
                "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/performance")
def get_performance(days: int = 30):
    try:
        mem  = _get_memory()
        perf = mem.get_performance_summary(days=days)
        return {"summary": perf, "days": days,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/performance/history")
def get_performance_history(days: int = 30):
    """Historial diario de performance con filas crudas (para graficas).
    Incluye el dia actual si el bot esta corriendo."""
    try:
        mem  = _get_memory()
        hist = mem.get_performance_history(days=days)

        # Si hoy no esta en el historial, intentar construirlo desde el estado en vivo
        today_str = date.today().isoformat()
        has_today = any(r["date"] == today_str for r in hist)

        if not has_today:
            daily = mem.get_daily_state()
            try:
                client  = _get_trading_client()
                acc     = client.get_account()
                equity  = float(acc.equity)
                last_eq = float(acc.last_equity)
                day_pnl = equity - last_eq
                hist.append({
                    "date":     today_str,
                    "equity":   round(equity, 2),
                    "pnl":      round(day_pnl, 2),
                    "trades":   daily.get("trades_today", 0),
                    "wins":     daily.get("wins_today", 0),
                    "losses":   daily.get("losses_today", 0),
                    "win_rate": round(daily["wins_today"] / daily["trades_today"], 3)
                                if daily.get("trades_today", 0) > 0 else None,
                })
            except Exception as e:
                logger.warning(f"[API] No se pudo agregar dia actual al historial: {e}")

        return {"history": hist, "days": days,
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
def health_check():
    try:
        _get_memory().get_daily_state()
        return {"status": "healthy", "postgres": "connected",
                "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as e:
        return {"status": "unhealthy", "postgres": "error", "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("  BÖRSENHIRN BOT API v1.2.0 — iniciando...")
    logger.info("  http://localhost:8000")
    logger.info("  Docs: http://localhost:8000/docs")
    logger.info("=" * 50)
    uvicorn.run("bot_api:app", host="0.0.0.0", port=8000, reload=False, log_level="info")