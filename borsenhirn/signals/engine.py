"""
SignalEngine (cerebro compartido) — produce la señal/análisis del ciclo, SIN ejecutar.

`analyze()` devuelve un `CycleSignals`: régimen + contexto de mercado + el resultado
del scanner (candidatos de compra/venta), ya con los filtros de análisis aplicados
(últimos 30min, BEAR). NO manda órdenes, NO escribe outcomes de trades. La ejecución
la hace el `AutoExecutor` (interno, auto-trade) o —en el producto— el usuario
(ejecución manual). Ver docs/RESECUENCIACION_PLAN.md (Paso 1).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any, Callable, Dict, List, Optional, Set

import config
from market_context import get_full_context, format_context_summary
from regime_detector import detect_regime

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")


@dataclass
class CycleSignals:
    """Lo que produce un ciclo de análisis. Sin efectos de ejecución."""
    regime: str
    regime_info: Dict[str, Any]
    market_ctx: Dict[str, Any]
    scan: Dict[str, List[dict]]   # {"buys": [...], "sells": [...]}


class SignalEngine:
    """
    Produce la señal del ciclo (read-only): contexto de mercado + régimen + scanner.
    No ejecuta nada. Reusa el modelo/scanner/fetcher ya construidos.
    """

    def __init__(self, *, model, fetcher, scanner):
        self.model = model
        self.fetcher = fetcher
        self.scanner = scanner

    def analyze(
        self,
        *,
        memory,
        held: Set[str],
        plan_symbol: Optional[str],
        prev_regime: Optional[str],
        alert: Callable[[str], None],
    ) -> CycleSignals:
        """
        Un pase de análisis. `prev_regime`/`alert` se usan para narrar el cambio
        de régimen en el mismo punto que el código original (antes del scanner).
        Devuelve `CycleSignals`; el caller persiste `regime` como nuevo prev.
        """
        # ── Contexto de mercado externo (una sola vez por ciclo) ──
        market_ctx = get_full_context(config.SYMBOL)
        logger.info(format_context_summary(market_ctx))

        # ── Régimen de mercado ────────────────────────────────
        regime_info = detect_regime(self.fetcher, market_ctx)
        regime      = regime_info["regime"]
        if regime != prev_regime:
            prev = prev_regime or "—"
            logger.info(f"[REGIME] Cambio: {prev} → {regime} | "
                        f"conf={regime_info['confidence']:.0%} | "
                        f"VIX={regime_info['vix']:.1f} | "
                        f"ADX={regime_info['adx']:.1f} | "
                        f"breadth={regime_info['breadth_pct']:.1%}"
                        if regime_info["breadth_pct"] is not None else
                        f"[REGIME] Cambio: {prev} → {regime}")
            alert(f"[REGIME] {prev} → {regime} | "
                  f"VIX={regime_info['vix']:.1f} | "
                  f"SPY {regime_info['spy_trend']} | "
                  f"conf={regime_info['confidence']:.0%}")

        # ── Scanner multi-simbolo ─────────────────────────
        # Excluir el simbolo del plan del watchlist (evita conflictos de wash trade)
        watchlist = [s for s in config.WATCHLIST if s != plan_symbol]
        scan = self.scanner.scan(
            watchlist, config.TIMEFRAME,
            held_symbols=held, market_ctx=market_ctx, memory=memory
        )

        # ── Sugerencia 4.1: no abrir nuevas posiciones en los ultimos 30min ──
        et_now    = datetime.now(_ET)
        last_30min = et_now >= et_now.replace(hour=15, minute=30, second=0, microsecond=0)
        if last_30min:
            logger.info("[SCANNER] Ultimos 30min del mercado — solo sells, no nuevas compras.")
            scan["buys"] = []

        # ── Filtro BEAR: solo simbolos defensivos cuando mercado esta en pánico ──
        vix_now = regime_info.get("vix", 0)
        if regime == "BEAR" and vix_now > 25:
            bear_safe  = set(config.BEAR_SAFE_SYMBOLS)
            antes      = len(scan["buys"])
            scan["buys"] = [e for e in scan["buys"] if e["symbol"] in bear_safe]
            filtrados  = antes - len(scan["buys"])
            if filtrados > 0:
                logger.info(
                    f"[REGIME] BEAR+VIX={vix_now:.0f}: {filtrados} compras bloqueadas "
                    f"— solo defensivos permitidos ({len(scan['buys'])} restantes)"
                )

        return CycleSignals(
            regime=regime, regime_info=regime_info,
            market_ctx=market_ctx, scan=scan,
        )


__all__ = ["CycleSignals", "SignalEngine"]
