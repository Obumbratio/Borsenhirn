"""
Motor de trading por tenant — `BotEngine` (orquestador) + `AutoExecutor` (cara interna).

ARQUITECTURA (Paso 1 de docs/RESECUENCIACION_PLAN.md — "un cerebro, dos caras"):
- `borsenhirn.signals.SignalEngine` (cerebro COMPARTIDO): produce la señal/análisis
  del ciclo (régimen + contexto + scanner), read-only, sin ejecutar.
- `AutoExecutor` (cara INTERNA, auto-trade): toma la señal y AUTO-EJECUTA en paper
  + bookkeeping + aprendizaje. NO es producto de cliente. (Paso 1.5 lo moverá a
  `borsenhirn/internal/autotrader/`.) El producto de cliente usará ejecución MANUAL
  (un endpoint que ejecuta solo cuando el usuario aprieta — Paso 3).
- `BotEngine`: orquesta el ciclo de vida (rollover/cuenta/kill-switch/mercado) y
  cablea `signal_engine.analyze() → auto_executor.execute()`. `run_cycle()` no duerme.

Aislamiento per-tenant: cada engine rutea sus alertas a SU propio `safety.alert_mgr`
(`_alert`), escribe el trade log a una ruta scoped por tenant (`_log_trade`), y
lee/guarda el plan por tenant. El DEFAULT conserva rutas/archivos globales.
"""

import os
import csv
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from typing import Any, Optional, Set, Tuple

import config
from data_fetcher import DataFetcher
from indicators import add_all_indicators
from ml_model import TradingModel
from risk_manager import RiskManager
from execution import Executor
from my_plan import load_plan, save_plan, PlanStrategy
from bot_memory_pg import BotMemory
from scanner import MarketScanner
from m3_risk import RiskEngine
from borsenhirn import db as bdb
from borsenhirn.signals import SignalEngine

# ── Safety layer (kill switches + sanity + alertas) ───────────
from borsenhirn.safety.bootstrap import (
    SafetyStack, make_recent_trades_buffer, extract_equity_history_7d,
)

logger = logging.getLogger(__name__)

SLEEP_MAP    = {"1Min":60,"5Min":300,"15Min":900,"1Hour":3600,"4Hour":14400,"1Day":86400}
LOOKBACK_DAYS = {"1Min":3,"5Min":7,"15Min":14,"1Hour":60,"4Hour":160,"1Day":400}

_ET = ZoneInfo("America/New_York")


def _safety_get_conn():
    """
    Devuelve un context manager del app pool para la SafetyStack.

    IMPORTANTE: devuelve `bdb.get_conn(...)` (un context manager), NO una
    conn cruda. El store (`PostgresStateStore`/`make_dashboard_db_write`)
    lo entra/sale por cada operacion via su helper `_acquire`, asi la conn
    VUELVE al pool al terminar. Esto evita el leak que agotaba el pool tras
    ~10 iteraciones del loop (cada `is_halted()` sacaba una conn sin
    devolverla). Ver B1 Bloque 7.
    """
    return bdb.get_conn(role="app")


def is_market_open() -> bool:
    """Retorna True solo durante horario regular NYSE (9:30am–4:00pm ET, lun–vie)."""
    now = datetime.now(_ET)
    if now.weekday() >= 5:          # sabado=5, domingo=6
        return False
    open_t  = now.replace(hour=9,  minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0,  second=0, microsecond=0)
    return open_t <= now <= close_t


def wait_next_bar(tf):
    s   = SLEEP_MAP.get(tf, 3600)
    now = datetime.now(timezone.utc)
    sl  = s - (now.timestamp() % s)
    pt  = datetime.now(ZoneInfo("America/Los_Angeles"))
    nxt = pt + timedelta(seconds=sl)
    logger.info(f"[SLEEP] Ciclo completo. Próximo ciclo en {sl:.0f}s "
                f"({nxt.strftime('%I:%M %p')} PT)")
    time.sleep(sl)


@dataclass
class _CycleCtx:
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

    Paso 1.5 mueve esta clase a `borsenhirn/internal/autotrader/` (carpeta marcada
    como interna/no-producto) + guardrail de que el API de cliente no la importe.
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

    def execute(self, signals, ctx: _CycleCtx) -> None:
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

    def _handle_plan(self, ctx: _CycleCtx) -> None:
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


class BotEngine:
    """
    Orquestador del ciclo scoped a un tenant. `__init__` hace el setup (memoria,
    safety, broker, modelo, scanner) y construye el `SignalEngine` (cerebro) + el
    `AutoExecutor` (cara interna). `run_cycle()` corre UN ciclo: lifecycle →
    señal → auto-ejecución.
    """

    def __init__(
        self,
        tenant_id: str,
        credentials: Optional[Tuple[str, str]] = None,
        *,
        train: bool = False,
        live: bool = False,
    ):
        self.tenant_id = tenant_id
        self.live = live
        modo = "LIVE — CUENTA REAL" if live else "PAPER TRADING"
        logger.info("=" * 55)
        logger.info(f"  TRADING BOT INICIADO  [{modo}]")
        logger.info(f"  {config.SYMBOL} | {config.TIMEFRAME} | tenant={tenant_id}")
        logger.info("=" * 55)

        self.memory = BotMemory(tenant_id=tenant_id)
        self.memory.log_summary()

        # ── Safety stack: AlertManager + KillSwitch + SanityChecker ──
        # Las alertas de ESTE engine van a su propia alert_mgr (vía self._alert),
        # nunca al slot global de logger — así no se cruzan entre tenants.
        self.safety = SafetyStack.init_from_config(
            _safety_get_conn, tenant_id=tenant_id,
        )
        self.recent_trades_buffer = make_recent_trades_buffer(maxlen=200)
        if self.safety.is_halted():
            reasons = [r["key"] for r in self.safety.killswitch.active_reasons()]
            logger.warning(f"[SAFETY] Bot inicia con kill switch ACTIVO: {reasons}")
            self.safety.alert_mgr.critical(
                "Bot arrancó en HALT",
                f"Kill switches activos al arranque: {reasons}. "
                f"Limpia con `python scripts/ks_admin.py clear --key <key>` "
                f"para retomar trading.",
            )
        logger.info(f"[SAFETY] stack listo | canales: "
                    f"{[c.name for c in self.safety.alert_mgr.channels]}")

        # ── Broker (DataFetcher + Executor) ──────────────────────
        if credentials is not None:
            api_key, api_secret = credentials
            self.fetcher  = DataFetcher(api_key=api_key, secret_key=api_secret)
            self.executor = Executor(api_key=api_key, secret_key=api_secret,
                                     paper=not live)
        elif live:
            if not config.LIVE_ALPACA_API_KEY or config.LIVE_ALPACA_API_KEY == "YOUR_LIVE_API_KEY_HERE":
                raise ValueError("LIVE_ALPACA_API_KEY no configurada en .env")
            self.fetcher  = DataFetcher(api_key=config.LIVE_ALPACA_API_KEY,
                                        secret_key=config.LIVE_ALPACA_SECRET_KEY)
            self.executor = Executor(api_key=config.LIVE_ALPACA_API_KEY,
                                     secret_key=config.LIVE_ALPACA_SECRET_KEY, paper=False)
        else:
            self.fetcher  = DataFetcher()
            self.executor = Executor()

        self.model = TradingModel()
        self.risk  = RiskManager()

        if train or not os.path.exists(config.MODEL_PATH):
            logger.info("Entrenando modelo ML...")
            end_dt   = datetime.now(timezone.utc)
            start_dt = end_dt - timedelta(days=730)
            df_h     = self.fetcher.get_historical(config.SYMBOL, start_dt, end_dt, config.TIMEFRAME)
            if not df_h.empty:
                m = self.model.train(add_all_indicators(df_h))
                self.memory.record_ml_metrics(
                    accuracy=m.get("accuracy", 0),
                    precision=m.get("precision", 0),
                    recall=m.get("recall", 0),
                    f1=m.get("f1", 0),
                    n_samples=m.get("n_samples", 0),
                )
                self._alert(f"Modelo entrenado. Accuracy={m.get('accuracy',0):.4f}")
        else:
            self.model.load_model()

        # ── Cargar plan del usuario si existe ────────────────────
        self.plan          = load_plan(tenant_id)
        self.plan_strategy = None
        if self.plan and self.plan.get("activo"):
            self.plan_strategy = PlanStrategy(plan=self.plan, model=self.model)
            logger.info(f"MI PLAN activo: {self.plan.get('symbol')} | "
                        f"{self.plan.get('strategy_type')} | "
                        f"Capital plan={self.plan.get('capital_pct',0.3)*100:.0f}% | "
                        f"Capital seguro={self.plan.get('safe_capital_pct',0.7)*100:.0f}%")
            self._alert(f"MI PLAN activado: {self.plan.get('symbol')} "
                        f"({self.plan.get('capital_pct',0.3)*100:.0f}% capital)")
        else:
            logger.info("Sin plan de usuario activo. Modo normal (solo SPY).")

        self.scanner = MarketScanner(model=self.model, fetcher=self.fetcher)
        self.risk_engine = RiskEngine()
        acc = self.executor.get_account()
        if acc:
            logger.info(f"Equity: ${acc.get('equity',0):.2f} | BP: ${acc.get('buying_power',0):.2f}")
            self.risk.update(acc.get("portfolio_value", config.CAPITAL), 0.0, 0)

        logger.info(f"Watchlist: {config.WATCHLIST} | Max posiciones: {config.MAX_OPEN_POSITIONS}")

        # ── Limpieza de posiciones al inicio ─────────────────────
        # Si hay más posiciones abiertas que MAX_OPEN_POSITIONS, cerrar las peores
        startup_positions = self.executor.get_positions()
        if len(startup_positions) > config.MAX_OPEN_POSITIONS:
            excess = len(startup_positions) - config.MAX_OPEN_POSITIONS
            logger.warning(
                f"[STARTUP] {len(startup_positions)} posiciones abiertas > "
                f"MAX_OPEN_POSITIONS={config.MAX_OPEN_POSITIONS}. "
                f"Cerrando las {excess} peores."
            )
            # Ordenar por unrealized PnL ascendente (peores primero)
            sorted_positions = sorted(startup_positions,
                                      key=lambda p: p.get("unrealized_pl", 0.0))
            for pos in sorted_positions[:excess]:
                sym = pos["symbol"]
                pnl = pos.get("unrealized_pl", 0.0)
                logger.warning(
                    f"[STARTUP] Cerrando {sym} (unrealized PnL=${pnl:+.2f})"
                )
                self.executor.close_position(sym)

        # Restaurar estado del dia desde memoria (sobrevive reinicios y crashes)
        saved = self.memory.get_daily_state()
        self.trades_today     = saved["trades_today"]
        self.wins_today       = saved["wins_today"]
        self.losses_today     = saved["losses_today"]
        self.day_start_equity = saved["day_start_equity"]
        if self.trades_today > 0:
            logger.info(f"[MEMORIA] Restaurado: trades_today={self.trades_today} "
                        f"wins={self.wins_today} losses={self.losses_today}")

        self.current_day     = datetime.now(timezone.utc).date()
        self.daily_pnl       = 0.0
        self.portfolio_value = config.CAPITAL
        self.current_regime  = None   # último régimen confirmado (para detectar cambios)
        self._alert(f"Bot iniciado | Watchlist={config.WATCHLIST} @ {config.TIMEFRAME}"
                    + (f" + MI PLAN {self.plan.get('symbol')}" if self.plan_strategy else ""))

        # ── Cerebro (señal, compartido) + cara interna (auto-ejecución) ──
        self.signal_engine = SignalEngine(
            model=self.model, fetcher=self.fetcher, scanner=self.scanner,
        )
        self.auto_executor = AutoExecutor(
            executor=self.executor, memory=self.memory, safety=self.safety,
            fetcher=self.fetcher, risk=self.risk, risk_engine=self.risk_engine,
            recent_trades_buffer=self.recent_trades_buffer, tenant_id=self.tenant_id,
            alert=self._alert, log_trade=self._log_trade,
        )

    # ── Helpers tenant-scoped (alertas / trade log / plan) ──────────
    def _alert(self, message: str, level: str = "INFO") -> None:
        """
        Emite una alerta scoped a ESTE tenant: la loguea y la rutea a la
        AlertManager propia (Discord/Email/Dashboard del tenant). No usa el
        `send_alert` global, así dos tenants nunca comparten canal.
        """
        logger.info(f"ALERTA [{level}]: {message}")
        try:
            self.safety.alert_from_logger(level, message)
        except Exception as exc:   # una alerta nunca debe tumbar el ciclo
            logger.error(f"_alert: {exc}")

    def _trades_log_path(self) -> str:
        """Ruta del CSV de trades, scoped por tenant (DEFAULT usa la global)."""
        from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID
        if self.tenant_id == DEFAULT_TENANT_UUID:
            return config.TRADES_LOG
        base, ext = os.path.splitext(config.TRADES_LOG)
        return f"{base}.{self.tenant_id}{ext}"

    def _log_trade(self, action, symbol, price, qty, reason) -> None:
        """Escribe una fila al CSV de trades del tenant (la DB ya aísla por RLS)."""
        path = self._trades_log_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        exists = os.path.isfile(path)
        row = {"timestamp": datetime.now(timezone.utc).isoformat(), "action": action,
               "symbol": symbol, "price": price, "qty": qty,
               "value": round(price * qty, 2), "reason": reason}
        with open(path, "a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=row.keys())
            if not exists:
                w.writeheader()
            w.writerow(row)
        logger.info(f"TRADE | {action.upper()} {qty}x{symbol} @ {price:.2f}")

    def run_cycle(self) -> dict:
        """
        Ejecuta UN ciclo: lifecycle (rollover/cuenta/kill-switch/mercado) →
        `signal_engine.analyze()` (señal) → `auto_executor.execute()` (auto-trade).
        No duerme. Devuelve {status: halted|market_closed|ok, ...}.
        """
        memory   = self.memory
        risk     = self.risk
        model    = self.model
        fetcher  = self.fetcher
        executor = self.executor
        safety   = self.safety

        now = datetime.now(timezone.utc)
        if now.date() != self.current_day:
            # Guardar resumen del dia anterior antes de resetear
            if self.trades_today > 0 or self.day_start_equity is not None:
                memory.record_day_end(
                    equity=self.portfolio_value,
                    pnl=self.daily_pnl,
                    trades=self.trades_today,
                    wins=self.wins_today,
                    losses=self.losses_today,
                )
                perf = memory.get_performance_summary(days=30)
                if perf:
                    logger.info(
                        f"[MEMORIA] Cierre de dia | "
                        f"PnL hoy=${self.daily_pnl:+.2f} | "
                        f"Win rate (30d)={perf['win_rate']:.0%} | "
                        f"PnL acum (30d)=${perf['total_pnl']:+.2f}"
                    )

            self.current_day      = now.date()
            self.trades_today     = 0
            self.wins_today       = 0
            self.losses_today     = 0
            self.day_start_equity = None
            self.daily_pnl        = 0.0
            risk.reset_daily()

            # Retrain semanal automatico del modelo ML
            if memory.should_retrain(interval_days=7):
                logger.info("[MEMORIA] Reentrenando modelo ML (retrain semanal)...")
                try:
                    end_rt   = datetime.now(timezone.utc)
                    start_rt = end_rt - timedelta(days=730)
                    df_rt    = fetcher.get_historical(config.SYMBOL, start_rt, end_rt, config.TIMEFRAME)
                    if not df_rt.empty:
                        m = model.train(add_all_indicators(df_rt))
                        memory.mark_trained()
                        memory.record_ml_metrics(
                            accuracy=m.get("accuracy", 0),
                            precision=m.get("precision", 0),
                            recall=m.get("recall", 0),
                            f1=m.get("f1", 0),
                            n_samples=m.get("n_samples", 0),
                        )
                        self._alert(f"Modelo reentrenado. Accuracy={m.get('accuracy',0):.4f}")
                except Exception as e:
                    logger.error(f"Retrain fallido: {e}")

            # Recargar plan en cada nuevo dia (puede haber sido modificado)
            self.plan = load_plan(self.tenant_id)
            if self.plan and self.plan.get("activo"):
                self.plan_strategy = PlanStrategy(plan=self.plan, model=model)
            else:
                self.plan_strategy = None

        # ── Cuenta y equity ───────────────────────────────
        acc = executor.get_account()
        if acc:
            if self.day_start_equity is None:
                self.day_start_equity = acc.get("equity", config.CAPITAL)
            self.daily_pnl = acc.get("equity", self.day_start_equity) - self.day_start_equity
            self.portfolio_value = acc.get("portfolio_value", config.CAPITAL)
            risk.update(self.portfolio_value, self.daily_pnl, self.trades_today)

        portfolio_value  = self.portfolio_value
        day_start_equity = self.day_start_equity
        daily_pnl        = self.daily_pnl

        plan         = self.plan
        safe_pct     = plan.get("safe_capital_pct", 1.0) if (plan and plan.get("activo")) else 1.0
        safe_capital = portfolio_value * safe_pct

        # ── Kill switch: revisión al inicio de cada ciclo ────
        equity_7d = extract_equity_history_7d(memory)
        snap = safety.build_snapshot(
            equity_now=portfolio_value,
            equity_day_start=day_start_equity,
            daily_pnl=daily_pnl,
            equity_history_7d=equity_7d,
        )
        if safety.check_and_halt(snap):
            reasons = [r["key"] for r in safety.killswitch.active_reasons()]
            logger.warning(f"[SAFETY] HALT activo: {reasons} — "
                           f"bot en modo seguro, NO se envían órdenes.")
            return {"status": "halted", "reasons": reasons}

        # ── Log de inicio de ciclo ───────────────────────
        pt_now = datetime.now(ZoneInfo("America/Los_Angeles"))
        logger.info(
            f"[CICLO] {pt_now.strftime('%I:%M %p')} PT | "
            f"Equity: ${portfolio_value:,.2f} | "
            f"Posiciones: {len(executor.get_positions())}/{config.MAX_OPEN_POSITIONS} | "
            f"Trades hoy: {self.trades_today}"
        )

        # ── Horario de mercado ────────────────────────────
        if not is_market_open():
            logger.info("Mercado cerrado — esperando apertura (9:30am–4:00pm ET).")
            return {"status": "market_closed"}

        # ── Posiciones + held (insumo del scanner) ────────
        positions_list = executor.get_positions()
        held = {p["symbol"] for p in positions_list}
        logger.info(f"Posiciones abiertas: {held or 'ninguna'} | "
                    f"Trades hoy: {self.trades_today} | PnL: ${daily_pnl:+.2f}")
        plan_symbol = plan.get("symbol") if (plan and plan.get("activo")) else None
        # Proteccion doble: aunque el scanner lo evalúe, nunca lo comprará
        if plan_symbol:
            held.add(plan_symbol)

        # ── SEÑAL (cerebro compartido, read-only) ─────────
        signals = self.signal_engine.analyze(
            memory=memory, held=held, plan_symbol=plan_symbol,
            prev_regime=self.current_regime, alert=self._alert,
        )
        self.current_regime = signals.regime

        # ── EJECUCIÓN (cara interna: auto-trade en paper) ──
        ctx = _CycleCtx(
            trades_today=self.trades_today, wins_today=self.wins_today,
            losses_today=self.losses_today, held=held, positions_list=positions_list,
            plan=self.plan, plan_strategy=self.plan_strategy, plan_symbol=plan_symbol,
            safe_capital=safe_capital, portfolio_value=portfolio_value,
        )
        self.auto_executor.execute(signals, ctx)
        self.trades_today = ctx.trades_today
        self.wins_today   = ctx.wins_today
        self.losses_today = ctx.losses_today
        self.plan         = ctx.plan

        # Guardar estado del dia (sobrevive crash/reinicio)
        memory.update_daily_state(
            self.trades_today, self.wins_today, self.losses_today, day_start_equity
        )

        # Guardar performance parcial del dia en cada ciclo
        # para que reportes/dashboard siempre incluyan el dia actual
        if day_start_equity is not None:
            memory.record_day_end(
                equity=portfolio_value,
                pnl=daily_pnl,
                trades=self.trades_today,
                wins=self.wins_today,
                losses=self.losses_today,
            )

        return {
            "status": "ok",
            "trades_today": self.trades_today,
            "wins_today": self.wins_today,
            "losses_today": self.losses_today,
            "regime": signals.regime,
        }


__all__ = [
    "BotEngine", "AutoExecutor", "is_market_open", "wait_next_bar",
    "_safety_get_conn", "SLEEP_MAP", "LOOKBACK_DAYS",
]
