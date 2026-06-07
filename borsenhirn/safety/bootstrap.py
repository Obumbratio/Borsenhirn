"""
Bootstrap del safety stack.

Encapsula la construcción de AlertManager + KillSwitch + SanityChecker
desde `config.py`, y expone helpers de alto nivel para usar desde main.py
con mínimas modificaciones al código existente.

Uso típico en main.py:

    from borsenhirn.safety.bootstrap import SafetyStack
    from borsenhirn import db as bdb
    from borsenhirn.tenancy import DEFAULT_TENANT_UUID
    import logger as _logger

    def _safety_get_conn():
        return bdb.get_app_pool().getconn()

    safety = SafetyStack.init_from_config(
        _safety_get_conn, tenant_id=DEFAULT_TENANT_UUID,
    )
    _logger.register_external_alerter(safety.alert_from_logger)

    # En el loop:
    snap = safety.build_snapshot(
        equity_now=portfolio_value,
        equity_day_start=day_start_equity,
        daily_pnl=daily_pnl,
        equity_history_7d=equity_7d_list,
    )
    if safety.check_and_halt(snap):
        # hay kill activo, skip trading este ciclo
        time.sleep(60)
        continue

    # Antes de un BUY:
    oid = safety.safe_submit_buy(
        executor, symbol, qty, price,
        positions_list=positions_list,
        recent_trades=recent_trades_buffer,
        portfolio_value=portfolio_value,
        reason=signal["reason"],
    )
    if oid is None:
        continue  # bloqueado por sanity
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Deque, Dict, List, Optional

from borsenhirn.safety.alerts import (
    AlertLevel,
    AlertManager,
    SmtpConfig,
    build_default_manager,
)
from borsenhirn.safety.killswitch import (
    KillReason,
    KillSnapshot,
    KillSwitch,
    KillSwitchConfig,
)
from borsenhirn.safety.sanity import (
    OrderContext,
    SanityChecker,
    SanityConfig,
)
from borsenhirn.safety.state_store_pg import (
    PostgresStateStore,
    make_dashboard_db_write,
)

logger = logging.getLogger(__name__)


@dataclass
class SafetyStack:
    """
    Contenedor del safety stack. Construilo con `init_from_config`.
    El objeto tiene estado mutable (contador de failures, conexión a alerts).
    """
    alert_mgr: AlertManager
    killswitch: KillSwitch
    sanity: SanityChecker
    watchlist: List[str] = field(default_factory=list)
    consecutive_order_failures: int = 0

    # ── Init ─────────────────────────────────────────────
    @classmethod
    def init_from_config(
        cls,
        get_conn_fn: Callable,
        tenant_id: Optional[str] = None,
    ) -> "SafetyStack":
        """
        Construye todos los componentes leyendo de `config.py`.
        `get_conn_fn` debe devolver una conexión psycopg2 abierta.
        `tenant_id` se propaga a los stores de Postgres (RLS) si != None.
        Default None mantiene backwards compat para callers admin.
        """
        import config  # import tardío para evitar ciclos

        # ── AlertManager ────
        smtp = None
        if config.SMTP_USER and config.SMTP_PASSWORD:
            smtp = SmtpConfig(
                host=config.SMTP_HOST,
                port=config.SMTP_PORT,
                user=config.SMTP_USER,
                password=config.SMTP_PASSWORD,
                use_tls=config.SMTP_USE_TLS,
            )
        alert_mgr = build_default_manager(
            discord_webhook_url=config.DISCORD_WEBHOOK_URL or None,
            smtp=smtp,
            email_to=config.ALERT_EMAIL_TO or None,
            db_write_fn=make_dashboard_db_write(get_conn_fn, tenant_id=tenant_id),
            dedupe_window_sec=config.ALERT_DEDUPE_WINDOW_SEC,
            min_level=AlertLevel.INFO,
        )

        # ── KillSwitch ────
        ks_store = PostgresStateStore(get_conn_fn, tenant_id=tenant_id)
        ks = KillSwitch(
            store=ks_store,
            alert_send=lambda subject, body, **meta:
                alert_mgr.critical(subject, body, **meta),
            config=KillSwitchConfig(
                max_daily_loss_pct=config.KS_MAX_DAILY_LOSS_PCT,
                max_drawdown_7d_pct=config.KS_MAX_DRAWDOWN_7D_PCT,
                max_consecutive_failures=config.KS_MAX_CONSECUTIVE_FAILURES,
            ),
        )

        # ── Sanity ────
        sanity = SanityChecker(SanityConfig(
            max_position_pct=config.MAX_POSITION_PCT,
            max_qty_per_order=config.SANITY_MAX_QTY_PER_ORDER,
            min_price=config.SANITY_MIN_PRICE,
            max_price=config.SANITY_MAX_PRICE,
            wash_trade_min_gap_sec=config.SANITY_WASH_GAP_SEC,
            watchlist_required=True,
        ))

        stack = cls(
            alert_mgr=alert_mgr,
            killswitch=ks,
            sanity=sanity,
            watchlist=list(config.WATCHLIST),
        )
        return stack

    # ── Bridge hacia logger.send_alert ──────────────────────
    def alert_from_logger(self, level: str, message: str) -> None:
        """
        Callback que registramos en logger.py. Permite que TODAS las
        llamadas existentes a `send_alert(msg)` en main.py lleguen también
        a Discord/Email sin tocar el código.
        """
        try:
            lvl = AlertLevel(level) if level in AlertLevel.__members__ else AlertLevel.INFO
            self.alert_mgr.send(lvl, message[:120], message, meta=None)
        except Exception as exc:
            logger.debug("alert_from_logger: %s", exc)

    # ── Kill switch helpers ─────────────────────────────────
    def build_snapshot(
        self,
        equity_now: float,
        equity_day_start: Optional[float],
        daily_pnl: Optional[float],
        equity_history_7d: Optional[List[float]] = None,
    ) -> KillSnapshot:
        return KillSnapshot(
            equity_now=equity_now,
            equity_day_start=equity_day_start,
            daily_pnl=daily_pnl,
            equity_history_7d=equity_history_7d,
            consecutive_order_failures=self.consecutive_order_failures,
        )

    def check_and_halt(self, snapshot: KillSnapshot) -> bool:
        """
        Corre los checks y devuelve True si el bot está en HALT.
        Si algún check dispara, ya se persiste y se envía alerta CRITICAL.
        """
        self.killswitch.check_all(snapshot)
        return self.killswitch.is_halted()

    def is_halted(self) -> bool:
        return self.killswitch.is_halted()

    # ── Submit de órdenes con sanity ────────────────────────
    def safe_submit_buy(
        self,
        executor,
        symbol: str,
        qty: int,
        price: float,
        positions_list: List[Dict[str, Any]],
        recent_trades: Deque[Dict[str, Any]],
        portfolio_value: float,
        reason: str = "",
    ) -> Optional[str]:
        """
        Valida un BUY con sanity, lo envía al executor, y actualiza contadores.

        Devuelve el order_id si se envió, None si fue bloqueado o falló.
        """
        ctx = OrderContext(
            symbol=symbol,
            action="buy",
            qty=qty,
            price=price,
            portfolio_value=portfolio_value,
            watchlist=self.watchlist,
            current_positions={p["symbol"]: int(float(p.get("qty", 0)))
                               for p in positions_list},
            recent_trades=list(recent_trades),
        )
        res = self.sanity.validate(ctx)
        if not res.ok:
            self.alert_mgr.warn(
                f"BUY bloqueado [{res.check}]",
                res.reason,
                symbol=symbol, qty=qty, price=round(price, 2),
            )
            return None
        oid = executor.submit_order(symbol, qty, "buy")
        if oid:
            self.consecutive_order_failures = 0
            recent_trades.append({
                "symbol": symbol, "action": "buy",
                "timestamp": time.time(),
            })
        else:
            self.consecutive_order_failures += 1
            self.alert_mgr.warn(
                f"BUY rechazado por broker: {symbol}",
                f"executor.submit_order devolvió None. qty={qty} price={price:.2f}",
            )
        return oid

    def register_sell(self, symbol: str, oid: Optional[str]) -> None:
        """
        Llamar después de cada SELL (scanner, TP, SL, trailing, MI PLAN).
        Actualiza contador de failures y el buffer de recent_trades.
        """
        if oid is None:
            self.consecutive_order_failures += 1
        else:
            self.consecutive_order_failures = 0

    def register_sell_success(self, symbol: str,
                              recent_trades: Deque[Dict[str, Any]]) -> None:
        """
        Versión que además registra en el buffer (usar tras confirmar oid).
        """
        self.consecutive_order_failures = 0
        recent_trades.append({
            "symbol": symbol, "action": "sell",
            "timestamp": time.time(),
        })


def make_recent_trades_buffer(maxlen: int = 100) -> Deque[Dict[str, Any]]:
    """Helper para mantener trades recientes en memoria para sanity wash-check."""
    return deque(maxlen=maxlen)


def extract_equity_history_7d(memory) -> List[float]:
    """
    Intenta reconstruir una lista de equity de los últimos 7 días desde
    bot_memory_pg.get_performance_history. Si el método no existe o falla,
    devuelve lista vacía (killswitch de drawdown 7d se inhabilita).
    """
    try:
        hist = memory.get_performance_history(days=7)
    except Exception:
        return []
    out: List[float] = []
    for row in hist or []:
        # row puede ser dict o tupla; intentamos ambos
        if isinstance(row, dict):
            v = row.get("equity") or row.get("portfolio_value")
        elif isinstance(row, (list, tuple)) and len(row) > 0:
            v = row[-1]
        else:
            v = None
        try:
            if v is not None:
                out.append(float(v))
        except (TypeError, ValueError):
            continue
    return out
