"""
AutoExecutor — cara INTERNA (auto-trade). ⛔ NO-producto, no importar desde cliente.

Toma un `CycleSignals` (del cerebro compartido `borsenhirn.signals.SignalEngine`) y
AUTO-EJECUTA en el broker (paper) + bookkeeping + aprendizaje (símbolo/régimen). Es la
mitad de ejecución que antes vivía en `engine.py::run_cycle`, movida acá VERBATIM
(Paso 1.5 de docs/RESECUENCIACION_PLAN.md). Las salidas (TP/SL/trailing) y
`update_highest_price` quedan acá porque dependen del orden de `held`.

El producto de cliente NO usa esto: ejecuta una orden SOLO cuando el usuario aprieta
el botón (ejecución manual, Paso 3).
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Set

import config
from indicators import add_all_indicators
from my_plan import load_plan, save_plan

logger = logging.getLogger(__name__)

# Lookback por timeframe para la estrategia del plan (copia local: este módulo no
# debe importar de engine.py para no crear un ciclo engine→autotrader→engine).
LOOKBACK_DAYS = {"1Min": 3, "5Min": 7, "15Min": 14, "1Hour": 60, "4Hour": 160, "1Day": 400}


@dataclass
class CycleCtx:
    """Estado mutable de UN ciclo que el AutoExecutor va modificando al ejecutar."""
    trades_today: int
    wins_today: int
    losses_today: int
    held: Set[str]
    positions_list: list
    plan: dict
    plan_strategy: Any
    plan_symbol: Optional[str]
    safe_capital: float
    portfolio_value: float


class AutoExecutor:
    """
    Cara INTERNA (auto-trade): toma un `CycleSignals` y AUTO-EJECUTA en el broker
    (paper) + bookkeeping + aprendizaje (símbolo/régimen). NO es producto de cliente
    — el cliente usa ejecución MANUAL (el usuario aprieta cada botón, Paso 3).
    """

    def __init__(self, *, executor, memory, safety, fetcher, risk, risk_engine,
                 recent_trades_buffer, tenant_id, alert, log_trade):
        self.executor = executor
        self.memory = memory
        self.safety = safety
        self.fetcher = fetcher
        self.risk = risk
        self.risk_engine = risk_engine
        self.recent_trades_buffer = recent_trades_buffer
        self.tenant_id = tenant_id
        self.alert = alert            # callable(message, level="INFO")
        self.log_trade = log_trade    # callable(action, symbol, price, qty, reason)

    def execute(self, signals, ctx: CycleCtx) -> None:
        """Auto-ejecuta los sells/salidas/buys del ciclo + el plan del usuario."""
        memory   = self.memory
        safety   = self.safety
        fetcher  = self.fetcher
        executor = self.executor
        risk     = self.risk
        regime     = signals.regime
        market_ctx = signals.market_ctx
        scan       = signals.scan

        # ── Ejecutar SELLS primero (liberar capital) ──────
        for entry in scan["sells"]:
            symbol = entry["symbol"]
            pos    = next((p for p in ctx.positions_list if p["symbol"] == symbol), None)
            if not pos:
                continue
            qty   = int(float(pos["qty"]))
            price = entry["price"]
            oid   = executor.submit_order(symbol, qty, "sell")
            safety.register_sell(symbol, oid)
            if oid:
                safety.register_sell_success(symbol, self.recent_trades_buffer)
                ctx.trades_today += 1
                entry_px = memory.get_entry_price(symbol)
                if entry_px:
                    pnl = memory.record_trade_outcome(
                        symbol, entry_px, price, qty, entry["signal"]["reason"]
                    )
                    won = pnl > 0
                    ctx.wins_today   += (1 if won else 0)
                    ctx.losses_today += (1 if not won else 0)
                    # Bloque 3: actualizar score del simbolo y estadistica por regimen
                    memory.update_symbol_score(symbol, won, pnl)
                    entry_ctx = memory.get_entry_ctx(symbol)
                    entry_regime = entry_ctx["regime"] if entry_ctx else regime
                    memory.update_regime_stat(entry_regime, won, pnl)
                    memory.clear_entry_price(symbol)
                    memory.clear_entry_ctx(symbol)
                    self.log_trade("sell", symbol, price, qty,
                              f"[SCANNER] {entry['signal']['reason']} | PnL=${pnl:+.2f}")
                    self.alert(f"SELL {qty}x{symbol} @ ${price:.2f} | PnL=${pnl:+.2f}")
                else:
                    self.log_trade("sell", symbol, price, qty,
                              f"[SCANNER] {entry['signal']['reason']}")
                    self.alert(f"SELL {qty}x{symbol} @ ${price:.2f}")
                ctx.held.discard(symbol)

        # ── Take-profit / Trailing stop / Stop-loss desde precio de entrada ─
        for pos in ctx.positions_list:
            sym = pos["symbol"]
            if sym == ctx.plan_symbol or sym not in ctx.held:
                continue
            entry_px = memory.get_entry_price(sym)
            if not entry_px:
                continue
            cur_price = fetcher.get_current_price(sym)
            if cur_price <= 0:
                continue
            pct_chg = (cur_price - entry_px) / entry_px

            # Actualizar precio maximo alcanzado (para trailing stop)
            highest = memory.update_highest_price(sym, cur_price)
            trailing_stop_px = highest * (1 - config.TRAILING_STOP_PCT)
            pct_from_high    = (cur_price - highest) / highest  # negativo si bajo del maximo

            # Trailing stop: solo actua si ya ganamos al menos TRAILING_STOP_PCT
            # (evita vender antes de que la posicion suba algo)
            trailing_triggered = (
                pct_chg > config.TRAILING_STOP_PCT and   # ya subio al menos 3%
                cur_price <= trailing_stop_px             # y ahora bajo 3% desde el maximo
            )

            if pct_chg >= config.TAKE_PROFIT_PCT:
                qty = int(float(pos["qty"]))
                oid = executor.submit_order(sym, qty, "sell")
                if oid:
                    ctx.trades_today += 1
                    pnl = memory.record_trade_outcome(
                        sym, entry_px, cur_price, qty,
                        f"Take-profit {pct_chg:.1%}"
                    )
                    ctx.wins_today += 1
                    memory.update_symbol_score(sym, True, pnl)
                    entry_ctx = memory.get_entry_ctx(sym)
                    memory.update_regime_stat(
                        entry_ctx["regime"] if entry_ctx else regime, True, pnl
                    )
                    memory.clear_entry_price(sym)
                    memory.clear_entry_ctx(sym)
                    self.log_trade("sell", sym, cur_price, qty,
                              f"Take-profit {pct_chg:.1%} | PnL=${pnl:+.2f}")
                    self.alert(f"TAKE-PROFIT {qty}x{sym} @ ${cur_price:.2f} "
                               f"| +{pct_chg:.1%} | PnL=${pnl:+.2f}")
                    ctx.held.discard(sym)

            elif trailing_triggered:
                qty = int(float(pos["qty"]))
                oid = executor.submit_order(sym, qty, "sell")
                if oid:
                    ctx.trades_today += 1
                    pnl = memory.record_trade_outcome(
                        sym, entry_px, cur_price, qty,
                        f"Trailing stop {pct_from_high:.1%} desde max ${highest:.2f}"
                    )
                    won = pnl > 0
                    ctx.wins_today   += (1 if won else 0)
                    ctx.losses_today += (1 if not won else 0)
                    memory.update_symbol_score(sym, won, pnl)
                    entry_ctx = memory.get_entry_ctx(sym)
                    memory.update_regime_stat(
                        entry_ctx["regime"] if entry_ctx else regime, won, pnl
                    )
                    memory.clear_entry_price(sym)
                    memory.clear_entry_ctx(sym)
                    self.log_trade("sell", sym, cur_price, qty,
                              f"Trailing stop | max=${highest:.2f} | {pct_chg:.1%} desde entrada | PnL=${pnl:+.2f}")
                    self.alert(f"TRAILING STOP {qty}x{sym} @ ${cur_price:.2f} "
                               f"| max=${highest:.2f} | PnL=${pnl:+.2f}")
                    ctx.held.discard(sym)

            elif pct_chg <= -config.STOP_LOSS_FROM_ENTRY_PCT:
                qty = int(float(pos["qty"]))
                oid = executor.submit_order(sym, qty, "sell")
                if oid:
                    ctx.trades_today += 1
                    pnl = memory.record_trade_outcome(
                        sym, entry_px, cur_price, qty,
                        f"Stop-loss entrada {pct_chg:.1%}"
                    )
                    ctx.losses_today += 1
                    memory.update_symbol_score(sym, False, pnl)
                    entry_ctx = memory.get_entry_ctx(sym)
                    memory.update_regime_stat(
                        entry_ctx["regime"] if entry_ctx else regime, False, pnl
                    )
                    memory.clear_entry_price(sym)
                    memory.clear_entry_ctx(sym)
                    self.log_trade("sell", sym, cur_price, qty,
                              f"Stop-loss entrada {pct_chg:.1%} | PnL=${pnl:+.2f}")
                    self.alert(f"STOP-LOSS {qty}x{sym} @ ${cur_price:.2f} "
                               f"| {pct_chg:.1%} | PnL=${pnl:+.2f}")
                    ctx.held.discard(sym)

        # ── Ejecutar BUYS (hasta MAX_OPEN_POSITIONS) ──────
        for entry in scan["buys"]:
            if len(ctx.held) >= config.MAX_OPEN_POSITIONS:
                logger.info(f"[SCANNER] Max posiciones ({config.MAX_OPEN_POSITIONS}) alcanzado.")
                break
            if ctx.trades_today >= config.MAX_TRADES_PER_DAY:
                logger.info("[SCANNER] Max trades diarios alcanzado.")
                break
            symbol = entry["symbol"]
            price  = entry["price"]
            if price <= 0:
                continue
            qty = max(config.MIN_SHARES_PER_BUY, int(ctx.safe_capital * config.MAX_POSITION_PCT / price))
            ok, msg = risk.validate_order(entry["signal"], price, 0)
            if not ok:
                logger.info(f"[SCANNER] {symbol} BUY bloqueado: {msg}")
                continue
            m3 = self.risk_engine.evaluate(symbol)
            if m3["verdict"] == "HIGH":
                logger.info(f"[M3] {symbol} bloqueado — score={m3['score']:.2f} {m3['verdict_es']}")
                continue
            logger.info(f"[M3] {symbol} aprobado {m3['emoji']} score={m3['score']:.2f}")
            oid = safety.safe_submit_buy(
                executor, symbol, qty, price,
                positions_list=ctx.positions_list,
                recent_trades=self.recent_trades_buffer,
                portfolio_value=ctx.portfolio_value,
                reason=entry["signal"]["reason"],
            )
            if oid:
                ctx.trades_today += 1
                memory.set_entry_price(symbol, price)
                # Bloque 1: guardar contexto completo al momento de compra
                vix_at_entry = (market_ctx.get("vix", {}).get("value") or 0.0)
                memory.save_entry_ctx(
                    symbol,
                    rsi      = entry["signal"].get("rsi", 50.0),
                    regime   = regime,
                    vix      = vix_at_entry,
                    ma_trend = entry["signal"].get("ma_trend", "neutral"),
                    ml_prob  = entry["signal"].get("ml_prob", 0.5),
                    entry_price = price,
                )
                self.log_trade("buy", symbol, price, qty,
                          f"[SCANNER] {entry['signal']['reason']}")
                self.alert(f"BUY {qty}x{symbol} @ ${price:.2f} | "
                           f"{entry['signal']['reason'][:50]}")
                ctx.held.add(symbol)

        # ── MI PLAN (activo del usuario, capital separado) ─
        if ctx.plan_strategy:
            ctx.plan = load_plan(self.tenant_id)
            self._handle_plan(ctx)

    def _handle_plan(self, ctx: CycleCtx) -> None:
        """Ejecuta un ciclo completo de la estrategia del plan del usuario."""
        fetcher  = self.fetcher
        executor = self.executor
        memory   = self.memory
        safety   = self.safety
        plan          = ctx.plan
        plan_strategy = ctx.plan_strategy
        portfolio_value = ctx.portfolio_value
        symbol = plan.get("symbol", "QQQ")
        plan_capital = portfolio_value * plan.get("capital_pct", 0.3)

        try:
            end_dt   = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=LOOKBACK_DAYS.get(config.TIMEFRAME, 60))
            df_raw   = fetcher.get_historical(symbol, start_dt, end_dt, config.TIMEFRAME)

            if df_raw.empty or len(df_raw) < 30:
                logger.warning(f"[MI PLAN] Sin datos para {symbol}.")
                return

            df     = add_all_indicators(df_raw.copy())
            signal = plan_strategy.generate_signal(df)
            price  = fetcher.get_current_price(symbol)
            if price <= 0:
                price = float(df.iloc[-1]["close"])

            position = executor.get_position(symbol)
            pos_qty  = position.get("qty", 0.0)

            logger.info(f"[MI PLAN] {symbol} | Señal: {signal['action'].upper()} | {signal['reason']}")

            if signal["action"] == "buy" and pos_qty == 0:
                qty = max(config.MIN_SHARES_PER_BUY, int(plan_capital / price))
                if qty > 0 and ctx.trades_today < config.MAX_TRADES_PER_DAY:
                    oid = safety.safe_submit_buy(
                        executor, symbol, qty, price,
                        positions_list=ctx.positions_list or [],
                        recent_trades=self.recent_trades_buffer,
                        portfolio_value=portfolio_value,
                        reason=f"[MI PLAN] {signal['reason']}",
                    )
                    if oid:
                        ctx.trades_today += 1
                        plan["entry_price"]  = price
                        plan["shares_held"]  = qty
                        save_plan(plan, self.tenant_id)
                        self.log_trade("buy", symbol, price, qty, f"[MI PLAN] {signal['reason']}")
                        self.alert(f"MI PLAN BUY {qty}x{symbol} @ ${price:.2f} | {signal['reason']}")

            elif signal["action"] == "sell" and pos_qty > 0:
                oid = executor.submit_order(symbol, int(pos_qty), "sell")
                if oid:
                    ctx.trades_today += 1
                    entry = plan.get("entry_price") or price
                    pnl   = memory.record_trade_outcome(
                        symbol, entry, price, int(pos_qty), f"[MI PLAN] {signal['reason']}"
                    )
                    if pnl > 0:
                        ctx.wins_today += 1
                    else:
                        ctx.losses_today += 1
                    plan["entry_price"] = None
                    plan["shares_held"] = 0
                    save_plan(plan, self.tenant_id)
                    memory.clear_entry_price(symbol)  # por si el scanner tambien tenia entrada
                    self.log_trade("sell", symbol, price, int(pos_qty),
                                    f"[MI PLAN] {signal['reason']} | PnL=${pnl:+.2f}")
                    self.alert(f"MI PLAN SELL {int(pos_qty)}x{symbol} @ ${price:.2f} | PnL=${pnl:+.2f}")

        except Exception as e:
            logger.error(f"[MI PLAN] Error: {e}", exc_info=True)


__all__ = ["AutoExecutor", "CycleCtx"]
