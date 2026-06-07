"""
Health snapshot del bot para monitoring externo (UptimeRobot, Grafana, etc.).

Uso:
    snapshot = get_health_snapshot(bot_state_provider, killswitch, circuit_breakers)

    # En FastAPI:
    @app.get("/health")
    def health():
        return get_health_snapshot(...)

El status general sigue convenciones Kubernetes:
    - "healthy":   todo OK.
    - "degraded":  hay algún circuit breaker abierto o warning no crítico.
    - "unhealthy": kill switch activo o error fatal.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class BotStateSnapshot:
    """Estado operacional que el caller debe poder resumir."""
    equity_now: float
    equity_day_start: Optional[float] = None
    daily_pnl: Optional[float] = None
    open_positions: int = 0
    regime: Optional[str] = None
    last_trade_at: Optional[str] = None  # ISO8601
    last_error: Optional[str] = None


def get_health_snapshot(
    bot_state: BotStateSnapshot,
    killswitch_active: List[Dict[str, Any]],
    circuit_breakers: List[Dict[str, Any]],
    version: str = "0.0.0",
) -> Dict[str, Any]:
    """
    Resume estado actual en dict JSON-serializable.

    Args:
        bot_state: snapshot del estado operacional.
        killswitch_active: resultado de KillSwitch.active_reasons() (lista de dicts).
        circuit_breakers: resultado de circuit_breaker.get_all_status().
        version: string de versión del bot.
    """
    # Determinar status
    if killswitch_active:
        status = "unhealthy"
    elif any(cb.get("state") == "open" for cb in circuit_breakers):
        status = "degraded"
    else:
        status = "healthy"

    daily_pnl_pct = None
    if bot_state.daily_pnl is not None and bot_state.equity_day_start:
        try:
            daily_pnl_pct = bot_state.daily_pnl / bot_state.equity_day_start
        except ZeroDivisionError:
            daily_pnl_pct = None

    return {
        "status": status,
        "version": version,
        "timestamp": int(time.time()),
        "bot": {
            "equity_now": round(float(bot_state.equity_now), 2),
            "equity_day_start": (round(float(bot_state.equity_day_start), 2)
                                  if bot_state.equity_day_start is not None else None),
            "daily_pnl": (round(float(bot_state.daily_pnl), 2)
                          if bot_state.daily_pnl is not None else None),
            "daily_pnl_pct": (round(float(daily_pnl_pct), 4)
                              if daily_pnl_pct is not None else None),
            "open_positions": int(bot_state.open_positions),
            "regime": bot_state.regime,
            "last_trade_at": bot_state.last_trade_at,
            "last_error": bot_state.last_error,
        },
        "kill_switches": {
            "active": len(killswitch_active),
            "reasons": killswitch_active,
        },
        "circuit_breakers": circuit_breakers,
    }


def register_fastapi_route(
    app,
    snapshot_provider: Callable[[], Dict[str, Any]],
    path: str = "/health",
):
    """
    Helper: registra /health en una app FastAPI ya existente.

    Uso:
        from borsenhirn.api.main import app
        from borsenhirn.safety.health import register_fastapi_route
        register_fastapi_route(app, lambda: get_health_snapshot(...))
    """
    @app.get(path)
    def _health():
        try:
            return snapshot_provider()
        except Exception as exc:
            logger.error("health endpoint falló: %s", exc)
            return {"status": "unhealthy", "error": str(exc)}
