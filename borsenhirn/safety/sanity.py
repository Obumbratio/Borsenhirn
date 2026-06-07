"""
Sanity checks pre-orden.

Validaciones robustas que deben correr ANTES de enviar cualquier orden a
Alpaca. Complementan risk_manager.py — no lo reemplazan. El flujo es:

    1. strategy.generate_signal(df) -> signal
    2. risk_manager.validate_order(signal) -> OK / reject
    3. SanityChecker.validate(signal, ctx) -> OK / reject  ← ESTA CAPA
    4. execution.send_order(...)

Si cualquier check falla, la orden NO se envía y se loguea el motivo.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class SanityResult:
    ok: bool
    reason: str = ""
    check: str = ""
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SanityConfig:
    max_position_pct: float = 0.06         # % capital por posición
    max_qty_per_order: int = 10_000         # hard cap defensivo
    min_price: float = 0.5                  # descartar penny / datos corruptos
    max_price: float = 100_000.0            # descartar datos absurdos
    wash_trade_min_gap_sec: int = 300       # 5 min entre sell y buy mismo símbolo
    watchlist_required: bool = True         # si True, símbolo debe estar en watchlist


@dataclass
class OrderContext:
    """
    Información necesaria para validar una orden. Inyectada por el caller;
    este módulo no consulta DB/Alpaca directamente.
    """
    symbol: str
    action: str               # "buy" | "sell"
    qty: int
    price: float
    portfolio_value: float
    watchlist: List[str]
    current_positions: Dict[str, int]         # symbol -> qty
    recent_trades: List[Dict[str, Any]] = field(default_factory=list)
    # recent_trades items: {"symbol","action","timestamp"}


class SanityChecker:
    """
    Conjunto de validaciones pre-orden. Cada check devuelve un SanityResult.
    La función principal `validate` los corre en orden y devuelve el primer
    fallo, o OK si todos pasan.
    """

    def __init__(self, config: Optional[SanityConfig] = None):
        self.cfg = config or SanityConfig()

    # ── Checks individuales ───────────────────────────────

    def check_action(self, ctx: OrderContext) -> SanityResult:
        if ctx.action not in ("buy", "sell"):
            return SanityResult(
                ok=False, check="action",
                reason=f"Acción inválida: {ctx.action!r}",
            )
        return SanityResult(ok=True, check="action")

    def check_price(self, ctx: OrderContext) -> SanityResult:
        p = ctx.price
        if p is None or p != p:  # NaN
            return SanityResult(ok=False, check="price",
                                reason="Precio NaN/None")
        if p < self.cfg.min_price or p > self.cfg.max_price:
            return SanityResult(
                ok=False, check="price",
                reason=f"Precio fuera de rango: {p}",
                data={"price": p, "min": self.cfg.min_price,
                      "max": self.cfg.max_price},
            )
        return SanityResult(ok=True, check="price")

    def check_quantity(self, ctx: OrderContext) -> SanityResult:
        if ctx.qty <= 0:
            return SanityResult(
                ok=False, check="quantity",
                reason=f"qty <= 0 ({ctx.qty})",
            )
        if ctx.qty > self.cfg.max_qty_per_order:
            return SanityResult(
                ok=False, check="quantity",
                reason=f"qty {ctx.qty} > cap {self.cfg.max_qty_per_order}",
            )
        # qty * price no puede exceder max_position_pct * portfolio
        notional = ctx.qty * ctx.price
        max_notional = ctx.portfolio_value * self.cfg.max_position_pct
        if notional > max_notional * 1.01:  # pequeño margen float
            return SanityResult(
                ok=False, check="position_size",
                reason=f"notional {notional:.0f} > límite "
                       f"{max_notional:.0f} ({self.cfg.max_position_pct:.0%} eq)",
                data={"notional": notional, "max_notional": max_notional},
            )
        return SanityResult(ok=True, check="quantity")

    def check_watchlist(self, ctx: OrderContext) -> SanityResult:
        if not self.cfg.watchlist_required:
            return SanityResult(ok=True, check="watchlist")
        if ctx.symbol not in ctx.watchlist:
            return SanityResult(
                ok=False, check="watchlist",
                reason=f"Símbolo {ctx.symbol!r} no está en watchlist",
            )
        return SanityResult(ok=True, check="watchlist")

    def check_no_duplicate_buy(self, ctx: OrderContext) -> SanityResult:
        if ctx.action != "buy":
            return SanityResult(ok=True, check="duplicate_buy")
        held = ctx.current_positions.get(ctx.symbol, 0)
        if held > 0:
            return SanityResult(
                ok=False, check="duplicate_buy",
                reason=f"Ya hay posición abierta en {ctx.symbol} ({held} shares)",
                data={"held_qty": held},
            )
        return SanityResult(ok=True, check="duplicate_buy")

    def check_sell_has_position(self, ctx: OrderContext) -> SanityResult:
        if ctx.action != "sell":
            return SanityResult(ok=True, check="sell_position")
        held = ctx.current_positions.get(ctx.symbol, 0)
        if held <= 0:
            return SanityResult(
                ok=False, check="sell_position",
                reason=f"Sell sin posición en {ctx.symbol}",
            )
        if ctx.qty > held:
            return SanityResult(
                ok=False, check="sell_position",
                reason=f"Sell qty {ctx.qty} > held {held}",
                data={"held": held},
            )
        return SanityResult(ok=True, check="sell_position")

    def check_no_wash_trade(self, ctx: OrderContext) -> SanityResult:
        """Evita compra inmediata tras venta del mismo símbolo."""
        if ctx.action != "buy":
            return SanityResult(ok=True, check="wash_trade")
        now = time.time()
        min_gap = self.cfg.wash_trade_min_gap_sec
        for t in reversed(ctx.recent_trades):
            if t.get("symbol") != ctx.symbol:
                continue
            if t.get("action") != "sell":
                continue
            ts = t.get("timestamp")
            if ts is None:
                continue
            ts_epoch = ts if isinstance(ts, (int, float)) else ts.timestamp()
            if now - ts_epoch < min_gap:
                return SanityResult(
                    ok=False, check="wash_trade",
                    reason=f"Vendiste {ctx.symbol} hace "
                           f"{now - ts_epoch:.0f}s (< {min_gap}s)",
                    data={"seconds_since_sell": now - ts_epoch},
                )
            break  # solo miramos la última venta del símbolo
        return SanityResult(ok=True, check="wash_trade")

    # ── Orquestador ───────────────────────────────────────

    def validate(self, ctx: OrderContext) -> SanityResult:
        """
        Corre todos los checks en orden. Devuelve el primer fallo o OK.
        """
        checks = [
            self.check_action,
            self.check_price,
            self.check_quantity,
            self.check_watchlist,
            self.check_no_duplicate_buy,
            self.check_sell_has_position,
            self.check_no_wash_trade,
        ]
        for check_fn in checks:
            r = check_fn(ctx)
            if not r.ok:
                logger.warning(
                    "Sanity FAIL [%s]: %s", r.check, r.reason,
                )
                return r
        return SanityResult(ok=True, check="all", reason="OK")
