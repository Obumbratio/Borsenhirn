import os, sys, time, argparse, logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import config
import logger as _logger_mod  # para register_external_alerter
from logger import setup_logging, log_trade, send_alert
from data_fetcher import DataFetcher
from indicators import add_all_indicators
from ml_model import TradingModel
from risk_manager import RiskManager
from execution import Executor
from my_plan import load_plan, save_plan, PlanStrategy
from market_context import get_full_context, format_context_summary
from bot_memory_pg import BotMemory
from scanner import MarketScanner
from regime_detector import detect_regime
from m3_risk import RiskEngine
from borsenhirn import db as bdb
from borsenhirn.tenancy import DEFAULT_TENANT_UUID

# ── Safety layer (kill switches + sanity + alertas) ───────────
from borsenhirn.safety.bootstrap import (
    SafetyStack, make_recent_trades_buffer, extract_equity_history_7d,
)

setup_logging()
logger = logging.getLogger(__name__)

SLEEP_MAP    = {"1Min":60,"5Min":300,"15Min":900,"1Hour":3600,"4Hour":14400,"1Day":86400}
LOOKBACK_DAYS = {"1Min":3,"5Min":7,"15Min":14,"1Hour":60,"4Hour":160,"1Day":400}

_ET = ZoneInfo("America/New_York")


def _safety_get_conn():
    """
    Devuelve conn fresca del app pool, compatible con el contrato
    `get_conn_fn` que espera SafetyStack (funcion plain, NO context
    manager — la conn se mantiene abierta hasta que el caller la
    descarte por GC).

    Reemplazo del `_get_conn` viejo de bot_memory_pg que fue
    eliminado en B1 5.4.a junto con el pool propio del modulo.

    Nota: el bot real usa pocas conns simultaneas para safety
    (1-2), asi que el pool de tamano 10 sobra. Si el flujo
    cambiara, refactorizar a context manager.
    """
    return bdb.get_app_pool().getconn()


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


def _handle_plan(plan, plan_strategy, fetcher, executor, risk, portfolio_value,
                 trades_today, wins_today, losses_today, memory,
                 safety=None, recent_trades_buffer=None, positions_list=None):
    """Ejecuta un ciclo completo de la estrategia del plan del usuario."""
    symbol = plan.get("symbol", "QQQ")
    plan_capital = portfolio_value * plan.get("capital_pct", 0.3)

    try:
        end_dt   = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=LOOKBACK_DAYS.get(config.TIMEFRAME, 60))
        df_raw   = fetcher.get_historical(symbol, start_dt, end_dt, config.TIMEFRAME)

        if df_raw.empty or len(df_raw) < 30:
            logger.warning(f"[MI PLAN] Sin datos para {symbol}.")
            return trades_today, wins_today, losses_today

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
            if qty > 0 and trades_today < config.MAX_TRADES_PER_DAY:
                if safety is not None:
                    oid = safety.safe_submit_buy(
                        executor, symbol, qty, price,
                        positions_list=positions_list or [],
                        recent_trades=recent_trades_buffer,
                        portfolio_value=portfolio_value,
                        reason=f"[MI PLAN] {signal['reason']}",
                    )
                else:
                    oid = executor.submit_order(symbol, qty, "buy")
                if oid:
                    trades_today += 1
                    plan["entry_price"]  = price
                    plan["shares_held"]  = qty
                    save_plan(plan)
                    log_trade("buy", symbol, price, qty, f"[MI PLAN] {signal['reason']}")
                    send_alert(f"MI PLAN BUY {qty}x{symbol} @ ${price:.2f} | {signal['reason']}")

        elif signal["action"] == "sell" and pos_qty > 0:
            oid = executor.submit_order(symbol, int(pos_qty), "sell")
            if oid:
                trades_today += 1
                entry = plan.get("entry_price") or price
                pnl   = memory.record_trade_outcome(
                    symbol, entry, price, int(pos_qty), f"[MI PLAN] {signal['reason']}"
                )
                if pnl > 0:
                    wins_today += 1
                else:
                    losses_today += 1
                plan["entry_price"] = None
                plan["shares_held"] = 0
                save_plan(plan)
                memory.clear_entry_price(symbol)  # por si el scanner tambien tenia entrada
                log_trade("sell", symbol, price, int(pos_qty),
                          f"[MI PLAN] {signal['reason']} | PnL=${pnl:+.2f}")
                send_alert(f"MI PLAN SELL {int(pos_qty)}x{symbol} @ ${price:.2f} | PnL=${pnl:+.2f}")

    except Exception as e:
        logger.error(f"[MI PLAN] Error: {e}", exc_info=True)

    return trades_today, wins_today, losses_today


def run(train=False, once=False, live=False):
    modo = "LIVE — CUENTA REAL" if live else "PAPER TRADING"
    logger.info("=" * 55)
    logger.info(f"  TRADING BOT INICIADO  [{modo}]")
    logger.info(f"  {config.SYMBOL} | {config.TIMEFRAME}")
    logger.info("=" * 55)

    memory = BotMemory(tenant_id=DEFAULT_TENANT_UUID)
    memory.log_summary()

    # ── Safety stack: AlertManager + KillSwitch + SanityChecker ──
    safety = SafetyStack.init_from_config(
        _safety_get_conn, tenant_id=DEFAULT_TENANT_UUID,
    )
    _logger_mod.register_external_alerter(safety.alert_from_logger)
    recent_trades_buffer = make_recent_trades_buffer(maxlen=200)
    if safety.is_halted():
        reasons = [r["key"] for r in safety.killswitch.active_reasons()]
        logger.warning(f"[SAFETY] Bot inicia con kill switch ACTIVO: {reasons}")
        safety.alert_mgr.critical(
            "Bot arrancó en HALT",
            f"Kill switches activos al arranque: {reasons}. "
            f"Limpia con `python scripts/ks_admin.py clear --key <key>` "
            f"para retomar trading.",
        )
    logger.info(f"[SAFETY] stack listo | canales: "
                f"{[c.name for c in safety.alert_mgr.channels]}")

    if live:
        if not config.LIVE_ALPACA_API_KEY or config.LIVE_ALPACA_API_KEY == "YOUR_LIVE_API_KEY_HERE":
            logger.error("LIVE_ALPACA_API_KEY no configurada en .env — abortando.")
            return
        fetcher  = DataFetcher(api_key=config.LIVE_ALPACA_API_KEY,
                               secret_key=config.LIVE_ALPACA_SECRET_KEY)
        executor = Executor(api_key=config.LIVE_ALPACA_API_KEY,
                            secret_key=config.LIVE_ALPACA_SECRET_KEY, paper=False)
    else:
        fetcher  = DataFetcher()
        executor = Executor()

    model = TradingModel()
    risk  = RiskManager()

    if train or not os.path.exists(config.MODEL_PATH):
        logger.info("Entrenando modelo ML...")
        end_dt   = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=730)
        df_h     = fetcher.get_historical(config.SYMBOL, start_dt, end_dt, config.TIMEFRAME)
        if not df_h.empty:
            m = model.train(add_all_indicators(df_h))
            memory.record_ml_metrics(
                accuracy=m.get("accuracy", 0),
                precision=m.get("precision", 0),
                recall=m.get("recall", 0),
                f1=m.get("f1", 0),
                n_samples=m.get("n_samples", 0),
            )
            send_alert(f"Modelo entrenado. Accuracy={m.get('accuracy',0):.4f}")
    else:
        model.load_model()

    # ── Cargar plan del usuario si existe ────────────────────
    plan          = load_plan()
    plan_strategy = None
    if plan and plan.get("activo"):
        plan_strategy = PlanStrategy(plan=plan, model=model)
        logger.info(f"MI PLAN activo: {plan.get('symbol')} | "
                    f"{plan.get('strategy_type')} | "
                    f"Capital plan={plan.get('capital_pct',0.3)*100:.0f}% | "
                    f"Capital seguro={plan.get('safe_capital_pct',0.7)*100:.0f}%")
        send_alert(f"MI PLAN activado: {plan.get('symbol')} "
                   f"({plan.get('capital_pct',0.3)*100:.0f}% capital)")
    else:
        logger.info("Sin plan de usuario activo. Modo normal (solo SPY).")

    scanner = MarketScanner(model=model, fetcher=fetcher)
    risk_engine = RiskEngine()
    acc     = executor.get_account()
    if acc:
        logger.info(f"Equity: ${acc.get('equity',0):.2f} | BP: ${acc.get('buying_power',0):.2f}")
        risk.update(acc.get("portfolio_value", config.CAPITAL), 0.0, 0)

    logger.info(f"Watchlist: {config.WATCHLIST} | Max posiciones: {config.MAX_OPEN_POSITIONS}")

    # ── Limpieza de posiciones al inicio ─────────────────────
    # Si hay más posiciones abiertas que MAX_OPEN_POSITIONS, cerrar las peores
    startup_positions = executor.get_positions()
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
            executor.close_position(sym)

    # Restaurar estado del dia desde memoria (sobrevive reinicios y crashes)
    saved = memory.get_daily_state()
    trades_today     = saved["trades_today"]
    wins_today       = saved["wins_today"]
    losses_today     = saved["losses_today"]
    day_start_equity = saved["day_start_equity"]
    if trades_today > 0:
        logger.info(f"[MEMORIA] Restaurado: trades_today={trades_today} "
                    f"wins={wins_today} losses={losses_today}")

    current_day     = datetime.now(timezone.utc).date()
    daily_pnl       = 0.0
    portfolio_value = config.CAPITAL
    current_regime  = None   # último régimen confirmado (para detectar cambios)
    send_alert(f"Bot iniciado | Watchlist={config.WATCHLIST} @ {config.TIMEFRAME}"
               + (f" + MI PLAN {plan.get('symbol')}" if plan_strategy else ""))

    try:
        while True:
            now = datetime.now(timezone.utc)
            if now.date() != current_day:
                # Guardar resumen del dia anterior antes de resetear
                if trades_today > 0 or day_start_equity is not None:
                    memory.record_day_end(
                        equity=portfolio_value,
                        pnl=daily_pnl,
                        trades=trades_today,
                        wins=wins_today,
                        losses=losses_today,
                    )
                    perf = memory.get_performance_summary(days=30)
                    if perf:
                        logger.info(
                            f"[MEMORIA] Cierre de dia | "
                            f"PnL hoy=${daily_pnl:+.2f} | "
                            f"Win rate (30d)={perf['win_rate']:.0%} | "
                            f"PnL acum (30d)=${perf['total_pnl']:+.2f}"
                        )

                current_day      = now.date()
                trades_today     = 0
                wins_today       = 0
                losses_today     = 0
                day_start_equity = None
                daily_pnl        = 0.0
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
                            send_alert(f"Modelo reentrenado. Accuracy={m.get('accuracy',0):.4f}")
                    except Exception as e:
                        logger.error(f"Retrain fallido: {e}")

                # Recargar plan en cada nuevo dia (puede haber sido modificado)
                plan = load_plan()
                if plan and plan.get("activo"):
                    plan_strategy = PlanStrategy(plan=plan, model=model)
                else:
                    plan_strategy = None

            # ── Cuenta y equity ───────────────────────────────
            acc = executor.get_account()
            if acc:
                if day_start_equity is None:
                    day_start_equity = acc.get("equity", config.CAPITAL)
                daily_pnl = acc.get("equity", day_start_equity) - day_start_equity
                portfolio_value = acc.get("portfolio_value", config.CAPITAL)
                risk.update(portfolio_value, daily_pnl, trades_today)

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
                wait_next_bar(config.TIMEFRAME)
                continue

            # ── Log de inicio de ciclo ───────────────────────
            pt_now = datetime.now(ZoneInfo("America/Los_Angeles"))
            logger.info(
                f"[CICLO] {pt_now.strftime('%I:%M %p')} PT | "
                f"Equity: ${portfolio_value:,.2f} | "
                f"Posiciones: {len(executor.get_positions())}/{config.MAX_OPEN_POSITIONS} | "
                f"Trades hoy: {trades_today}"
            )

            # ── Horario de mercado ────────────────────────────
            if not is_market_open():
                logger.info("Mercado cerrado — esperando apertura (9:30am–4:00pm ET).")
                wait_next_bar(config.TIMEFRAME)
                continue

            # ── Contexto de mercado externo (una sola vez por ciclo) ──
            market_ctx = get_full_context(config.SYMBOL)
            logger.info(format_context_summary(market_ctx))

            # ── Régimen de mercado ────────────────────────────────
            regime_info = detect_regime(fetcher, market_ctx)
            regime      = regime_info["regime"]
            if regime != current_regime:
                prev = current_regime or "—"
                logger.info(f"[REGIME] Cambio: {prev} → {regime} | "
                            f"conf={regime_info['confidence']:.0%} | "
                            f"VIX={regime_info['vix']:.1f} | "
                            f"ADX={regime_info['adx']:.1f} | "
                            f"breadth={regime_info['breadth_pct']:.1%}"
                            if regime_info["breadth_pct"] is not None else
                            f"[REGIME] Cambio: {prev} → {regime}")
                send_alert(f"[REGIME] {prev} → {regime} | "
                           f"VIX={regime_info['vix']:.1f} | "
                           f"SPY {regime_info['spy_trend']} | "
                           f"conf={regime_info['confidence']:.0%}")
                current_regime = regime

            # ── Scanner multi-simbolo ─────────────────────────
            positions_list = executor.get_positions()
            held = {p["symbol"] for p in positions_list}
            logger.info(f"Posiciones abiertas: {held or 'ninguna'} | "
                        f"Trades hoy: {trades_today} | PnL: ${daily_pnl:+.2f}")

            # Excluir el simbolo del plan del watchlist (evita conflictos de wash trade)
            plan_symbol = plan.get("symbol") if (plan and plan.get("activo")) else None
            watchlist   = [s for s in config.WATCHLIST if s != plan_symbol]
            # Proteccion doble: aunque el scanner lo evalúe, nunca lo comprará
            if plan_symbol:
                held.add(plan_symbol)
            scan = scanner.scan(
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

            # ── Ejecutar SELLS primero (liberar capital) ──────
            for entry in scan["sells"]:
                symbol = entry["symbol"]
                pos    = next((p for p in positions_list if p["symbol"] == symbol), None)
                if not pos:
                    continue
                qty   = int(float(pos["qty"]))
                price = entry["price"]
                oid   = executor.submit_order(symbol, qty, "sell")
                safety.register_sell(symbol, oid)
                if oid:
                    safety.register_sell_success(symbol, recent_trades_buffer)
                    trades_today += 1
                    entry_px = memory.get_entry_price(symbol)
                    if entry_px:
                        pnl = memory.record_trade_outcome(
                            symbol, entry_px, price, qty, entry["signal"]["reason"]
                        )
                        won = pnl > 0
                        wins_today   += (1 if won else 0)
                        losses_today += (1 if not won else 0)
                        # Bloque 3: actualizar score del simbolo y estadistica por regimen
                        memory.update_symbol_score(symbol, won, pnl)
                        entry_ctx = memory.get_entry_ctx(symbol)
                        entry_regime = entry_ctx["regime"] if entry_ctx else regime
                        memory.update_regime_stat(entry_regime, won, pnl)
                        memory.clear_entry_price(symbol)
                        memory.clear_entry_ctx(symbol)
                        log_trade("sell", symbol, price, qty,
                                  f"[SCANNER] {entry['signal']['reason']} | PnL=${pnl:+.2f}")
                        send_alert(f"SELL {qty}x{symbol} @ ${price:.2f} | PnL=${pnl:+.2f}")
                    else:
                        log_trade("sell", symbol, price, qty,
                                  f"[SCANNER] {entry['signal']['reason']}")
                        send_alert(f"SELL {qty}x{symbol} @ ${price:.2f}")
                    held.discard(symbol)

            # ── Take-profit / Trailing stop / Stop-loss desde precio de entrada ─
            for pos in positions_list:
                sym = pos["symbol"]
                if sym == plan_symbol or sym not in held:
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
                        trades_today += 1
                        pnl = memory.record_trade_outcome(
                            sym, entry_px, cur_price, qty,
                            f"Take-profit {pct_chg:.1%}"
                        )
                        wins_today += 1
                        memory.update_symbol_score(sym, True, pnl)
                        entry_ctx = memory.get_entry_ctx(sym)
                        memory.update_regime_stat(
                            entry_ctx["regime"] if entry_ctx else regime, True, pnl
                        )
                        memory.clear_entry_price(sym)
                        memory.clear_entry_ctx(sym)
                        log_trade("sell", sym, cur_price, qty,
                                  f"Take-profit {pct_chg:.1%} | PnL=${pnl:+.2f}")
                        send_alert(f"TAKE-PROFIT {qty}x{sym} @ ${cur_price:.2f} "
                                   f"| +{pct_chg:.1%} | PnL=${pnl:+.2f}")
                        held.discard(sym)

                elif trailing_triggered:
                    qty = int(float(pos["qty"]))
                    oid = executor.submit_order(sym, qty, "sell")
                    if oid:
                        trades_today += 1
                        pnl = memory.record_trade_outcome(
                            sym, entry_px, cur_price, qty,
                            f"Trailing stop {pct_from_high:.1%} desde max ${highest:.2f}"
                        )
                        won = pnl > 0
                        wins_today   += (1 if won else 0)
                        losses_today += (1 if not won else 0)
                        memory.update_symbol_score(sym, won, pnl)
                        entry_ctx = memory.get_entry_ctx(sym)
                        memory.update_regime_stat(
                            entry_ctx["regime"] if entry_ctx else regime, won, pnl
                        )
                        memory.clear_entry_price(sym)
                        memory.clear_entry_ctx(sym)
                        log_trade("sell", sym, cur_price, qty,
                                  f"Trailing stop | max=${highest:.2f} | {pct_chg:.1%} desde entrada | PnL=${pnl:+.2f}")
                        send_alert(f"TRAILING STOP {qty}x{sym} @ ${cur_price:.2f} "
                                   f"| max=${highest:.2f} | PnL=${pnl:+.2f}")
                        held.discard(sym)

                elif pct_chg <= -config.STOP_LOSS_FROM_ENTRY_PCT:
                    qty = int(float(pos["qty"]))
                    oid = executor.submit_order(sym, qty, "sell")
                    if oid:
                        trades_today += 1
                        pnl = memory.record_trade_outcome(
                            sym, entry_px, cur_price, qty,
                            f"Stop-loss entrada {pct_chg:.1%}"
                        )
                        losses_today += 1
                        memory.update_symbol_score(sym, False, pnl)
                        entry_ctx = memory.get_entry_ctx(sym)
                        memory.update_regime_stat(
                            entry_ctx["regime"] if entry_ctx else regime, False, pnl
                        )
                        memory.clear_entry_price(sym)
                        memory.clear_entry_ctx(sym)
                        log_trade("sell", sym, cur_price, qty,
                                  f"Stop-loss entrada {pct_chg:.1%} | PnL=${pnl:+.2f}")
                        send_alert(f"STOP-LOSS {qty}x{sym} @ ${cur_price:.2f} "
                                   f"| {pct_chg:.1%} | PnL=${pnl:+.2f}")
                        held.discard(sym)

            # ── Ejecutar BUYS (hasta MAX_OPEN_POSITIONS) ──────
            for entry in scan["buys"]:
                if len(held) >= config.MAX_OPEN_POSITIONS:
                    logger.info(f"[SCANNER] Max posiciones ({config.MAX_OPEN_POSITIONS}) alcanzado.")
                    break
                if trades_today >= config.MAX_TRADES_PER_DAY:
                    logger.info("[SCANNER] Max trades diarios alcanzado.")
                    break
                symbol = entry["symbol"]
                price  = entry["price"]
                if price <= 0:
                    continue
                qty = max(config.MIN_SHARES_PER_BUY, int(safe_capital * config.MAX_POSITION_PCT / price))
                ok, msg = risk.validate_order(entry["signal"], price, 0)
                if not ok:
                    logger.info(f"[SCANNER] {symbol} BUY bloqueado: {msg}")
                    continue
                m3 = risk_engine.evaluate(symbol)
                if m3["verdict"] == "HIGH":
                    logger.info(f"[M3] {symbol} bloqueado — score={m3['score']:.2f} {m3['verdict_es']}")
                    continue
                logger.info(f"[M3] {symbol} aprobado {m3['emoji']} score={m3['score']:.2f}")
                oid = safety.safe_submit_buy(
                    executor, symbol, qty, price,
                    positions_list=positions_list,
                    recent_trades=recent_trades_buffer,
                    portfolio_value=portfolio_value,
                    reason=entry["signal"]["reason"],
                )
                if oid:
                    trades_today += 1
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
                    log_trade("buy", symbol, price, qty,
                              f"[SCANNER] {entry['signal']['reason']}")
                    send_alert(f"BUY {qty}x{symbol} @ ${price:.2f} | "
                               f"{entry['signal']['reason'][:50]}")
                    held.add(symbol)

            # ── MI PLAN (activo del usuario, capital separado) ─
            if plan_strategy:
                plan = load_plan()
                trades_today, wins_today, losses_today = _handle_plan(
                    plan, plan_strategy, fetcher, executor,
                    risk, portfolio_value, trades_today,
                    wins_today, losses_today, memory,
                    safety=safety,
                    recent_trades_buffer=recent_trades_buffer,
                    positions_list=positions_list,
                )

            # Guardar estado del dia (sobrevive crash/reinicio)
            memory.update_daily_state(
                trades_today, wins_today, losses_today, day_start_equity
            )

            # Guardar performance parcial del dia en cada ciclo
            # para que reportes/dashboard siempre incluyan el dia actual
            if day_start_equity is not None:
                memory.record_day_end(
                    equity=portfolio_value,
                    pnl=daily_pnl,
                    trades=trades_today,
                    wins=wins_today,
                    losses=losses_today,
                )

            if once:
                logger.info("Modo --once completado.")
                break
            wait_next_bar(config.TIMEFRAME)

    except KeyboardInterrupt:
        logger.info("Bot detenido manualmente.")
        send_alert("Bot detenido.")
    except Exception as e:
        logger.error(f"Error fatal: {e}", exc_info=True)
        send_alert(f"Error: {e}")
    finally:
        logger.info("Bot cerrado.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--train", action="store_true")
    p.add_argument("--once",  action="store_true")
    p.add_argument("--live",  action="store_true", help="Operar con cuenta real (dinero real)")
    a = p.parse_args()
    run(train=a.train, once=a.once, live=a.live)
