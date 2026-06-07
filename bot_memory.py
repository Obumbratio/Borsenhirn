"""
bot_memory.py — Memoria persistente del bot de trading.

Guarda y recupera entre sesiones (incluso si el bot crashea):
- Estado diario: trades_today, wins/losses, day_start_equity, precio entrada SPY
- Historial de performance por dia: P&L, win rate, equity acumulada
- Resultados de cada trade cerrado (para aprendizaje)
- Fecha del ultimo entrenamiento ML (retrain semanal automatico)

Archivo: reports/bot_memory.json
"""
import os, json, logging
from datetime import date

MEMORY_FILE = "reports/bot_memory.json"
logger = logging.getLogger(__name__)

_DEFAULTS = {
    "daily_state": {
        "date":             None,
        "trades_today":     0,
        "wins_today":       0,
        "losses_today":     0,
        "day_start_equity": None,
        "entry_prices":     {},   # {symbol: precio_entrada} para todas las posiciones abiertas
    },
    "last_trained":       None,   # fecha ISO del ultimo retrain ML
    "performance_history": [],    # resumen por dia, hasta 365 entradas
    "trade_outcomes":      [],    # trades cerrados con P&L real, hasta 500

    # ── Bloque 1: condiciones al momento de entrada ────────────────
    # {symbol: {rsi, regime, vix, ma_trend, ml_prob, entry_price, entry_date}}
    "trade_entry_ctx":    {},

    # ── Bloque 3: score acumulado por simbolo ─────────────────────
    # {symbol: {score, wins, losses, total_pnl, last_updated}}
    # score: 0.0 (pesimo) a 1.0 (excelente), empieza en 0.5 (neutral)
    "symbol_scores":      {},

    # ── Bloque 3: rendimiento por regimen ─────────────────────────
    # {regime: {wins, losses, total_pnl}}  e.g. "BULL": {...}
    "regime_stats":       {},
}


class BotMemory:
    def __init__(self):
        os.makedirs("reports", exist_ok=True)
        self.data = self._load()

    def _load(self):
        if os.path.exists(MEMORY_FILE):
            try:
                with open(MEMORY_FILE, encoding="utf-8") as f:
                    d = json.load(f)
                # compatibilidad con versiones anteriores sin estas keys
                for k, v in _DEFAULTS.items():
                    if k not in d:
                        d[k] = (v.copy() if isinstance(v, dict)
                                else list(v) if isinstance(v, list) else v)
                # migracion: spy_entry_price → entry_prices dict
                ds = d.get("daily_state", {})
                if "spy_entry_price" in ds:
                    old_price = ds.pop("spy_entry_price")
                    if "entry_prices" not in ds:
                        ds["entry_prices"] = {}
                    if old_price:
                        ds["entry_prices"]["SPY"] = old_price
                if "entry_prices" not in ds:
                    ds["entry_prices"] = {}
                return d
            except Exception as e:
                logger.error(f"BotMemory.load: {e}")
        return {k: (v.copy() if isinstance(v, dict)
                    else list(v) if isinstance(v, list) else v)
                for k, v in _DEFAULTS.items()}

    def save(self):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            logger.error(f"BotMemory.save: {e}")

    # ── Estado diario ─────────────────────────────────────────────

    def get_daily_state(self) -> dict:
        """
        Retorna el estado persistido si es del mismo dia.
        Si es un dia nuevo, resetea contadores pero conserva
        entry_prices (puede haber posiciones abiertas de dias anteriores).
        """
        ds    = self.data["daily_state"]
        today = date.today().isoformat()
        if ds.get("date") == today:
            return {
                "trades_today":     ds.get("trades_today", 0),
                "wins_today":       ds.get("wins_today", 0),
                "losses_today":     ds.get("losses_today", 0),
                "day_start_equity": ds.get("day_start_equity"),
                "entry_prices":     ds.get("entry_prices", {}),
            }
        # dia nuevo — contadores a cero, pero posiciones pueden seguir abiertas
        return {
            "trades_today":     0,
            "wins_today":       0,
            "losses_today":     0,
            "day_start_equity": None,
            "entry_prices":     ds.get("entry_prices", {}),
        }

    def update_daily_state(self, trades_today, wins_today, losses_today,
                           day_start_equity):
        self.data["daily_state"].update({
            "date":             date.today().isoformat(),
            "trades_today":     trades_today,
            "wins_today":       wins_today,
            "losses_today":     losses_today,
            "day_start_equity": day_start_equity,
            # entry_prices se actualiza directamente via set/clear_entry_price
        })
        self.save()

    def set_entry_price(self, symbol: str, price: float):
        self.data["daily_state"].setdefault("entry_prices", {})[symbol] = price
        self.save()

    def get_entry_price(self, symbol: str) -> float | None:
        return self.data["daily_state"].get("entry_prices", {}).get(symbol)

    def clear_entry_price(self, symbol: str):
        self.data["daily_state"].get("entry_prices", {}).pop(symbol, None)
        self.save()

    # ── Historial de performance ──────────────────────────────────

    def record_day_end(self, equity: float, pnl: float,
                       trades: int, wins: int, losses: int):
        """Llamar al inicio de cada nuevo dia (antes de resetear contadores)."""
        today = date.today().isoformat()
        # evitar duplicados del mismo dia
        self.data["performance_history"] = [
            r for r in self.data["performance_history"] if r.get("date") != today
        ]
        self.data["performance_history"].append({
            "date":     today,
            "equity":   round(equity, 2),
            "pnl":      round(pnl, 2),
            "trades":   trades,
            "wins":     wins,
            "losses":   losses,
            "win_rate": round(wins / trades, 3) if trades > 0 else None,
        })
        # mantener solo el ultimo año
        self.data["performance_history"] = self.data["performance_history"][-365:]
        self.save()

    def get_performance_summary(self, days: int = 30) -> dict | None:
        hist = self.data["performance_history"][-days:]
        if not hist:
            return None
        total_pnl    = sum(r["pnl"] for r in hist)
        total_trades = sum(r["trades"] for r in hist)
        total_wins   = sum(r["wins"] for r in hist)
        return {
            "days":          len(hist),
            "total_pnl":     round(total_pnl, 2),
            "total_trades":  total_trades,
            "win_rate":      round(total_wins / total_trades, 3) if total_trades > 0 else 0,
            "avg_daily_pnl": round(total_pnl / len(hist), 2),
            "best_day":      round(max(r["pnl"] for r in hist), 2),
            "worst_day":     round(min(r["pnl"] for r in hist), 2),
        }

    def get_performance_history(self, days: int = 30) -> list:
        """Devuelve filas crudas del historial de performance (para graficas)."""
        return self.data["performance_history"][-days:]

    # ── Trade outcomes ────────────────────────────────────────────

    def record_trade_outcome(self, symbol: str, buy_price: float,
                             sell_price: float, qty: int,
                             reason_sell: str) -> float:
        """Registra el resultado de un trade cerrado. Retorna el P&L."""
        pnl = round((sell_price - buy_price) * qty, 2)
        self.data["trade_outcomes"].append({
            "date":        date.today().isoformat(),
            "symbol":      symbol,
            "buy_price":   round(buy_price, 4),
            "sell_price":  round(sell_price, 4),
            "qty":         qty,
            "pnl":         pnl,
            "win":         pnl > 0,
            "reason_sell": reason_sell,
        })
        self.data["trade_outcomes"] = self.data["trade_outcomes"][-500:]
        self.save()
        return pnl

    def get_win_stats(self, symbol: str = None, last_n: int = 50) -> dict | None:
        outcomes = self.data["trade_outcomes"]
        if symbol:
            outcomes = [t for t in outcomes if t["symbol"] == symbol]
        outcomes = outcomes[-last_n:]
        if not outcomes:
            return None
        wins   = [t for t in outcomes if t["win"]]
        losses = [t for t in outcomes if not t["win"]]
        return {
            "total":     len(outcomes),
            "wins":      len(wins),
            "losses":    len(losses),
            "win_rate":  round(len(wins) / len(outcomes), 3),
            "avg_win":   round(sum(t["pnl"] for t in wins)   / len(wins),   2) if wins   else 0.0,
            "avg_loss":  round(sum(t["pnl"] for t in losses) / len(losses), 2) if losses else 0.0,
            "total_pnl": round(sum(t["pnl"] for t in outcomes), 2),
        }

    # ── ML retraining ─────────────────────────────────────────────

    def should_retrain(self, interval_days: int = 7) -> bool:
        last = self.data.get("last_trained")
        if not last:
            # primera vez: marcar hoy para que retraine en interval_days dias
            self.mark_trained()
            return False
        return (date.today() - date.fromisoformat(last)).days >= interval_days

    def mark_trained(self):
        self.data["last_trained"] = date.today().isoformat()
        self.save()

    # ── Bloque 1: contexto de entrada ────────────────────────────

    def save_entry_ctx(self, symbol: str, rsi: float, regime: str,
                       vix: float, ma_trend: str, ml_prob: float,
                       entry_price: float):
        """Guarda las condiciones del mercado al momento de comprar."""
        self.data["trade_entry_ctx"][symbol] = {
            "rsi":           round(rsi, 2),
            "regime":        regime,
            "vix":           round(vix, 2),
            "ma_trend":      ma_trend,
            "ml_prob":       round(ml_prob, 4),
            "entry_price":   round(entry_price, 4),
            "highest_price": round(entry_price, 4),  # se actualiza cada ciclo para trailing stop
            "entry_date":    date.today().isoformat(),
        }
        self.save()

    def update_highest_price(self, symbol: str, current_price: float) -> float:
        """
        Actualiza el precio maximo alcanzado desde la compra.
        Retorna el maximo actualizado (para calcular trailing stop afuera).
        """
        ctx = self.data["trade_entry_ctx"].get(symbol)
        if not ctx:
            return current_price
        if current_price > ctx.get("highest_price", 0):
            ctx["highest_price"] = round(current_price, 4)
            self.save()
        return ctx["highest_price"]

    def get_highest_price(self, symbol: str) -> float | None:
        ctx = self.data["trade_entry_ctx"].get(symbol)
        return ctx.get("highest_price") if ctx else None

    def get_entry_ctx(self, symbol: str) -> dict | None:
        return self.data["trade_entry_ctx"].get(symbol)

    def clear_entry_ctx(self, symbol: str):
        self.data["trade_entry_ctx"].pop(symbol, None)
        self.save()

    # ── Bloque 3: symbol score ────────────────────────────────────

    def update_symbol_score(self, symbol: str, won: bool, pnl: float):
        """
        Actualiza el score del simbolo despues de cerrar un trade.
        Score sube si ganamos, baja si perdemos.
        Rango: 0.0 (pesimo) a 1.0 (excelente), neutro en 0.5.
        """
        scores = self.data["symbol_scores"]
        if symbol not in scores:
            scores[symbol] = {"score": 0.5, "wins": 0, "losses": 0,
                              "total_pnl": 0.0, "last_updated": None}
        s = scores[symbol]
        s["wins"]       += 1 if won else 0
        s["losses"]     += 0 if won else 1
        s["total_pnl"]   = round(s["total_pnl"] + pnl, 2)
        s["last_updated"] = date.today().isoformat()

        # Score: promedio movil exponencial simple
        # Win sube hacia 1.0, Loss baja hacia 0.0, paso 0.1
        step = 0.1
        s["score"] = round(
            s["score"] + step * (1.0 - s["score"]) if won
            else s["score"] - step * s["score"],
            4
        )
        self.save()

    def get_symbol_score(self, symbol: str) -> float:
        """Retorna score del simbolo (0.5 si no hay historial)."""
        return self.data["symbol_scores"].get(symbol, {}).get("score", 0.5)

    def get_top_symbols(self, n: int = 10) -> list[dict]:
        """Retorna los N mejores simbolos por score."""
        scores = self.data["symbol_scores"]
        ranked = sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True)
        return [{"symbol": sym, **data} for sym, data in ranked[:n]]

    def get_bottom_symbols(self, n: int = 5) -> list[dict]:
        """Retorna los N peores simbolos por score."""
        scores = self.data["symbol_scores"]
        ranked = sorted(scores.items(), key=lambda x: x[1]["score"])
        return [{"symbol": sym, **data} for sym, data in ranked[:n]]

    # ── Bloque 3: regime stats ────────────────────────────────────

    def update_regime_stat(self, regime: str, won: bool, pnl: float):
        """Registra resultado de un trade segun el regimen al momento de entrada."""
        rs = self.data["regime_stats"]
        if regime not in rs:
            rs[regime] = {"wins": 0, "losses": 0, "total_pnl": 0.0}
        rs[regime]["wins"]      += 1 if won else 0
        rs[regime]["losses"]    += 0 if won else 1
        rs[regime]["total_pnl"]  = round(rs[regime]["total_pnl"] + pnl, 2)
        self.save()

    def get_regime_win_rate(self, regime: str) -> float | None:
        """Retorna el win rate historico en un regimen dado. None si no hay datos."""
        rs = self.data["regime_stats"].get(regime)
        if not rs:
            return None
        total = rs["wins"] + rs["losses"]
        return round(rs["wins"] / total, 3) if total > 0 else None

    # ── Resumen en log ────────────────────────────────────────────

    def log_summary(self):
        """Imprime resumen de memoria al arrancar el bot."""
        perf = self.get_performance_summary(days=30)
        if perf:
            logger.info(
                f"[MEMORIA] {perf['days']} dias | "
                f"PnL acum=${perf['total_pnl']:+.2f} | "
                f"Win rate={perf['win_rate']:.0%} | "
                f"Trades={perf['total_trades']} | "
                f"Mejor dia=${perf['best_day']:+.2f} | "
                f"Peor dia=${perf['worst_day']:+.2f}"
            )
        stats = self.get_win_stats(last_n=20)
        if stats and stats["total"] >= 3:
            logger.info(
                f"[MEMORIA] Ultimos {stats['total']} trades | "
                f"Wins={stats['wins']} Losses={stats['losses']} | "
                f"Avg win=${stats['avg_win']:+.2f} | "
                f"Avg loss=${stats['avg_loss']:+.2f} | "
                f"PnL total=${stats['total_pnl']:+.2f}"
            )
        last_trained = self.data.get("last_trained")
        if last_trained:
            days_ago = (date.today() - date.fromisoformat(last_trained)).days
            logger.info(f"[MEMORIA] Modelo ML entrenado hace {days_ago} dias "
                        f"(retrain cada 7 dias)")

        # Symbol scores acumulados
        scores = self.data.get("symbol_scores", {})
        if scores:
            top = self.get_top_symbols(3)
            bot = self.get_bottom_symbols(3)
            top_str = ", ".join(f"{s['symbol']}={s['score']:.2f}" for s in top)
            bot_str = ", ".join(f"{s['symbol']}={s['score']:.2f}" for s in bot)
            logger.info(f"[MEMORIA] Scores ({len(scores)} simbolos) | "
                        f"Top: {top_str} | Bottom: {bot_str}")

        # Estadisticas por regimen
        rs = self.data.get("regime_stats", {})
        if rs:
            parts = []
            for regime, data in rs.items():
                total = data["wins"] + data["losses"]
                if total > 0:
                    wr = data["wins"] / total
                    parts.append(f"{regime}: {wr:.0%} ({total} trades, ${data['total_pnl']:+.0f})")
            if parts:
                logger.info(f"[MEMORIA] Por regimen | " + " | ".join(parts))
