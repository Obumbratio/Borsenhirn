"""
bot_memory_pg.py — Memoria persistente del bot usando PostgreSQL.

Reemplaza bot_memory.py (JSON) con la misma interfaz exacta.
main.py no necesita ningún cambio — solo cambia el import:

    # Antes:
    from bot_memory import BotMemory

    # Después:
    from bot_memory_pg import BotMemory

Tablas usadas (ya creadas por database.py):
    - bot_daily_state      : estado del día actual
    - bot_performance      : historial diario de P&L
    - bot_trade_outcomes   : trades cerrados con P&L real
    - bot_entry_context    : condiciones al momento de compra
    - bot_symbol_scores    : score acumulado por símbolo
    - bot_regime_stats     : rendimiento por régimen de mercado
    - bot_ml_training      : fecha del último retrain ML
"""

import logging
from datetime import date, datetime, timezone
from typing import Optional
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
import psycopg2.pool
from psycopg2.extras import RealDictCursor

import config  # usa config.DATABASE_URL o variables individuales

logger = logging.getLogger(__name__)


# ── Connection Pool ────────────────────────────────────────────────────────────

_pool = None

def _get_pool():
    """Retorna el pool de conexiones (singleton, creado en primera llamada)."""
    global _pool
    if _pool is None or _pool.closed:
        _pool = psycopg2.pool.ThreadedConnectionPool(
            minconn=1,
            maxconn=5,
            host=getattr(config, "DB_HOST", "localhost"),
            port=getattr(config, "DB_PORT", 5432),
            dbname=getattr(config, "DB_NAME", "borsenhirn"),
            user=getattr(config, "DB_USER", "postgres"),
            password=getattr(config, "DB_PASSWORD", ""),
        )
    return _pool

@contextmanager
def _get_conn():
    """Context manager que toma una conexión del pool y la devuelve al salir."""
    pool = _get_pool()
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


# ── Crear tablas si no existen ────────────────────────────────────────────────

_DDL = """
CREATE TABLE IF NOT EXISTS bot_daily_state (
    id               SERIAL PRIMARY KEY,
    state_date       DATE    NOT NULL UNIQUE,
    trades_today     INTEGER NOT NULL DEFAULT 0,
    wins_today       INTEGER NOT NULL DEFAULT 0,
    losses_today     INTEGER NOT NULL DEFAULT 0,
    day_start_equity NUMERIC(18,4),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_entry_prices (
    symbol      VARCHAR(16) NOT NULL,
    state_date  DATE        NOT NULL,
    entry_price NUMERIC(18,4) NOT NULL,
    PRIMARY KEY (symbol, state_date)
);

CREATE TABLE IF NOT EXISTS bot_performance (
    perf_date  DATE        NOT NULL PRIMARY KEY,
    equity     NUMERIC(18,4) NOT NULL,
    pnl        NUMERIC(18,4) NOT NULL,
    trades     INTEGER     NOT NULL DEFAULT 0,
    wins       INTEGER     NOT NULL DEFAULT 0,
    losses     INTEGER     NOT NULL DEFAULT 0,
    win_rate   NUMERIC(6,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_trade_outcomes (
    id          SERIAL PRIMARY KEY,
    trade_date  DATE          NOT NULL,
    symbol      VARCHAR(16)   NOT NULL,
    buy_price   NUMERIC(18,4) NOT NULL,
    sell_price  NUMERIC(18,4) NOT NULL,
    qty         INTEGER       NOT NULL,
    pnl         NUMERIC(18,4) NOT NULL,
    win         BOOLEAN       NOT NULL,
    reason_sell TEXT,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_entry_context (
    symbol        VARCHAR(16)   NOT NULL PRIMARY KEY,
    rsi           NUMERIC(8,2),
    regime        VARCHAR(16),
    vix           NUMERIC(8,2),
    ma_trend      VARCHAR(16),
    ml_prob       NUMERIC(8,4),
    entry_price   NUMERIC(18,4),
    highest_price NUMERIC(18,4),
    entry_date    DATE,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_symbol_scores (
    symbol       VARCHAR(16)   NOT NULL PRIMARY KEY,
    score        NUMERIC(8,4)  NOT NULL DEFAULT 0.5,
    wins         INTEGER       NOT NULL DEFAULT 0,
    losses       INTEGER       NOT NULL DEFAULT 0,
    total_pnl    NUMERIC(18,4) NOT NULL DEFAULT 0,
    last_updated DATE,
    updated_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_regime_stats (
    regime     VARCHAR(16)   NOT NULL PRIMARY KEY,
    wins       INTEGER       NOT NULL DEFAULT 0,
    losses     INTEGER       NOT NULL DEFAULT 0,
    total_pnl  NUMERIC(18,4) NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_ml_training (
    id           SERIAL PRIMARY KEY,
    trained_date DATE        NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bot_ml_metrics (
    id              SERIAL PRIMARY KEY,
    trained_date    DATE NOT NULL,
    accuracy        NUMERIC(8,4),
    precision_score NUMERIC(8,4),
    recall_score    NUMERIC(8,4),
    f1_score        NUMERIC(8,4),
    n_samples       INTEGER,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


def _ensure_tables(conn):
    """Crea las tablas si no existen. Idempotente."""
    with conn.cursor() as cur:
        cur.execute(_DDL)
    conn.commit()


# ── BotMemory ─────────────────────────────────────────────────────────────────

class BotMemory:
    """
    Memoria persistente del bot usando PostgreSQL con connection pooling.
    Interfaz 100% idéntica a bot_memory.BotMemory (versión JSON).
    """

    def __init__(self):
        try:
            with _get_conn() as conn:
                _ensure_tables(conn)
            logger.info("[MEMORIA-PG] Conectado a PostgreSQL (pool).")
        except Exception as e:
            logger.error(f"[MEMORIA-PG] Error conectando a Postgres: {e}")
            raise

    @contextmanager
    def _db(self):
        """Context manager: obtiene conexión del pool con cursor RealDictCursor."""
        with _get_conn() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                yield conn, cur

    # ── Estado diario ─────────────────────────────────────────────

    def get_daily_state(self) -> dict:
        today = date.today()
        entry_prices = self._get_entry_prices(today)

        with self._db() as (conn, cur):
            cur.execute(
                "SELECT * FROM bot_daily_state WHERE state_date = %s",
                (today,)
            )
            row = cur.fetchone()

        if row:
            return {
                "trades_today":     row["trades_today"],
                "wins_today":       row["wins_today"],
                "losses_today":     row["losses_today"],
                "day_start_equity": float(row["day_start_equity"]) if row["day_start_equity"] else None,
                "entry_prices":     entry_prices,
            }
        return {
            "trades_today":     0,
            "wins_today":       0,
            "losses_today":     0,
            "day_start_equity": None,
            "entry_prices":     entry_prices,
        }

    def update_daily_state(self, trades_today: int, wins_today: int,
                           losses_today: int, day_start_equity: float):
        today = date.today()
        with self._db() as (conn, cur):
            cur.execute("""
                INSERT INTO bot_daily_state
                    (state_date, trades_today, wins_today, losses_today, day_start_equity, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (state_date) DO UPDATE SET
                    trades_today     = EXCLUDED.trades_today,
                    wins_today       = EXCLUDED.wins_today,
                    losses_today     = EXCLUDED.losses_today,
                    day_start_equity = EXCLUDED.day_start_equity,
                    updated_at       = NOW()
            """, (today, trades_today, wins_today, losses_today, day_start_equity))
            conn.commit()

    def _get_entry_prices(self, state_date=None) -> dict:
        if state_date is None:
            state_date = date.today()
        with self._db() as (conn, cur):
            cur.execute(
                "SELECT symbol, entry_price FROM bot_entry_prices WHERE state_date <= %s",
                (state_date,)
            )
            rows = cur.fetchall()
        return {r["symbol"]: float(r["entry_price"]) for r in rows}

    def set_entry_price(self, symbol: str, price: float):
        today = date.today()
        with self._db() as (conn, cur):
            cur.execute("""
                INSERT INTO bot_entry_prices (symbol, state_date, entry_price)
                VALUES (%s, %s, %s)
                ON CONFLICT (symbol, state_date) DO UPDATE SET
                    entry_price = EXCLUDED.entry_price
            """, (symbol, today, price))
            conn.commit()

    def get_entry_price(self, symbol: str) -> Optional[float]:
        with self._db() as (conn, cur):
            cur.execute(
                "SELECT entry_price FROM bot_entry_prices WHERE symbol = %s ORDER BY state_date DESC LIMIT 1",
                (symbol,)
            )
            row = cur.fetchone()
        return float(row["entry_price"]) if row else None

    def clear_entry_price(self, symbol: str):
        with self._db() as (conn, cur):
            cur.execute("DELETE FROM bot_entry_prices WHERE symbol = %s", (symbol,))
            conn.commit()

    # ── Historial de performance ──────────────────────────────────

    def record_day_end(self, equity: float, pnl: float,
                       trades: int, wins: int, losses: int):
        today    = date.today()
        win_rate = round(wins / trades, 3) if trades > 0 else None
        with self._db() as (conn, cur):
            cur.execute("""
                INSERT INTO bot_performance
                    (perf_date, equity, pnl, trades, wins, losses, win_rate)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (perf_date) DO UPDATE SET
                    equity   = EXCLUDED.equity,
                    pnl      = EXCLUDED.pnl,
                    trades   = EXCLUDED.trades,
                    wins     = EXCLUDED.wins,
                    losses   = EXCLUDED.losses,
                    win_rate = EXCLUDED.win_rate
            """, (today, equity, pnl, trades, wins, losses, win_rate))
            conn.commit()

    def get_performance_summary(self, days: int = 30) -> Optional[dict]:
        with self._db() as (conn, cur):
            cur.execute("""
                SELECT * FROM bot_performance
                ORDER BY perf_date DESC
                LIMIT %s
            """, (days,))
            rows = cur.fetchall()

        if not rows:
            return None

        total_pnl    = sum(float(r["pnl"])    for r in rows)
        total_trades = sum(int(r["trades"])   for r in rows)
        total_wins   = sum(int(r["wins"])     for r in rows)
        pnls         = [float(r["pnl"])       for r in rows]

        return {
            "days":          len(rows),
            "total_pnl":     round(total_pnl, 2),
            "total_trades":  total_trades,
            "win_rate":      round(total_wins / total_trades, 3) if total_trades > 0 else 0,
            "avg_daily_pnl": round(total_pnl / len(rows), 2),
            "best_day":      round(max(pnls), 2),
            "worst_day":     round(min(pnls), 2),
        }

    def get_performance_history(self, days: int = 30) -> list:
        """Devuelve filas crudas del historial de performance (para graficas).
        Incluye el dia actual si ya fue registrado por record_day_end."""
        with self._db() as (conn, cur):
            cur.execute("""
                SELECT perf_date, equity, pnl, trades, wins, losses, win_rate
                FROM bot_performance
                ORDER BY perf_date DESC
                LIMIT %s
            """, (days,))
            rows = cur.fetchall()

        return [
            {
                "date":     r["perf_date"].isoformat(),
                "equity":   round(float(r["equity"]), 2),
                "pnl":      round(float(r["pnl"]), 2),
                "trades":   int(r["trades"]),
                "wins":     int(r["wins"]),
                "losses":   int(r["losses"]),
                "win_rate": float(r["win_rate"]) if r["win_rate"] is not None else None,
            }
            for r in reversed(rows)  # cronologico: mas antiguo primero
        ]

    # ── Trade outcomes ────────────────────────────────────────────

    def record_trade_outcome(self, symbol: str, buy_price: float,
                             sell_price: float, qty: int,
                             reason_sell: str) -> float:
        pnl = round((sell_price - buy_price) * qty, 2)
        win = pnl > 0
        with self._db() as (conn, cur):
            cur.execute("""
                INSERT INTO bot_trade_outcomes
                    (trade_date, symbol, buy_price, sell_price, qty, pnl, win, reason_sell)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (date.today(), symbol, buy_price, sell_price, qty, pnl, win, reason_sell))
            conn.commit()
        logger.info(f"[MEMORIA-PG] Trade cerrado: {symbol} PnL=${pnl:+.2f} ({'WIN' if win else 'LOSS'})")
        return pnl

    def get_win_stats(self, last_n: int = 20) -> Optional[dict]:
        with self._db() as (conn, cur):
            cur.execute("""
                SELECT pnl, win FROM bot_trade_outcomes
                ORDER BY created_at DESC
                LIMIT %s
            """, (last_n,))
            rows = cur.fetchall()

        if not rows:
            return None

        wins   = [r for r in rows if r["win"]]
        losses = [r for r in rows if not r["win"]]
        return {
            "total":     len(rows),
            "wins":      len(wins),
            "losses":    len(losses),
            "win_rate":  round(len(wins) / len(rows), 3),
            "avg_win":   round(sum(float(r["pnl"]) for r in wins)   / len(wins),   2) if wins   else 0.0,
            "avg_loss":  round(sum(float(r["pnl"]) for r in losses) / len(losses), 2) if losses else 0.0,
            "total_pnl": round(sum(float(r["pnl"]) for r in rows), 2),
        }

    # ── ML retraining ─────────────────────────────────────────────

    def should_retrain(self, interval_days: int = 7) -> bool:
        with self._db() as (conn, cur):
            cur.execute(
                "SELECT trained_date FROM bot_ml_training ORDER BY trained_date DESC LIMIT 1"
            )
            row = cur.fetchone()

        if not row:
            self.mark_trained()
            return False
        return (date.today() - row["trained_date"]).days >= interval_days

    def mark_trained(self):
        with self._db() as (conn, cur):
            cur.execute(
                "INSERT INTO bot_ml_training (trained_date) VALUES (%s)",
                (date.today(),)
            )
            conn.commit()

    # ── ML metrics ────────────────────────────────────────────────

    def record_ml_metrics(self, accuracy: float, precision: float,
                          recall: float, f1: float, n_samples: int):
        """Registra métricas del último retrain del modelo ML."""
        with self._db() as (conn, cur):
            cur.execute("""
                INSERT INTO bot_ml_metrics
                    (trained_date, accuracy, precision_score, recall_score, f1_score, n_samples)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (date.today(), round(accuracy, 4), round(precision, 4),
                  round(recall, 4), round(f1, 4), n_samples))
            conn.commit()
        logger.info(f"[MEMORIA-PG] ML metrics guardadas: acc={accuracy:.4f} "
                    f"prec={precision:.4f} rec={recall:.4f} f1={f1:.4f} n={n_samples}")

    def get_ml_metrics_history(self, n: int = 10) -> list:
        """Retorna las últimas n métricas de retrain del modelo ML."""
        with self._db() as (conn, cur):
            cur.execute("""
                SELECT trained_date, accuracy, precision_score, recall_score,
                       f1_score, n_samples, created_at
                FROM bot_ml_metrics
                ORDER BY created_at DESC
                LIMIT %s
            """, (n,))
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ── Contexto de entrada ───────────────────────────────────────

    def save_entry_ctx(self, symbol: str, rsi: float, regime: str,
                       vix: float, ma_trend: str, ml_prob: float,
                       entry_price: float):
        with self._db() as (conn, cur):
            cur.execute("""
                INSERT INTO bot_entry_context
                    (symbol, rsi, regime, vix, ma_trend, ml_prob,
                     entry_price, highest_price, entry_date, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE SET
                    rsi           = EXCLUDED.rsi,
                    regime        = EXCLUDED.regime,
                    vix           = EXCLUDED.vix,
                    ma_trend      = EXCLUDED.ma_trend,
                    ml_prob       = EXCLUDED.ml_prob,
                    entry_price   = EXCLUDED.entry_price,
                    highest_price = EXCLUDED.highest_price,
                    entry_date    = EXCLUDED.entry_date,
                    updated_at    = NOW()
            """, (symbol, round(rsi, 2), regime, round(vix, 2), ma_trend,
                  round(ml_prob, 4), round(entry_price, 4),
                  round(entry_price, 4), date.today()))
            conn.commit()

    def update_highest_price(self, symbol: str, current_price: float) -> float:
        with self._db() as (conn, cur):
            cur.execute(
                "SELECT highest_price FROM bot_entry_context WHERE symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()

            if not row:
                return current_price

            highest = float(row["highest_price"])
            if current_price > highest:
                cur.execute("""
                    UPDATE bot_entry_context
                    SET highest_price = %s, updated_at = NOW()
                    WHERE symbol = %s
                """, (round(current_price, 4), symbol))
                conn.commit()
                return round(current_price, 4)
            return highest

    def get_highest_price(self, symbol: str) -> Optional[float]:
        with self._db() as (conn, cur):
            cur.execute(
                "SELECT highest_price FROM bot_entry_context WHERE symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
        return float(row["highest_price"]) if row else None

    def get_entry_ctx(self, symbol: str) -> Optional[dict]:
        with self._db() as (conn, cur):
            cur.execute(
                "SELECT * FROM bot_entry_context WHERE symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
        if not row:
            return None
        return {
            "rsi":           float(row["rsi"]) if row["rsi"] else None,
            "regime":        row["regime"],
            "vix":           float(row["vix"]) if row["vix"] else None,
            "ma_trend":      row["ma_trend"],
            "ml_prob":       float(row["ml_prob"]) if row["ml_prob"] else None,
            "entry_price":   float(row["entry_price"]) if row["entry_price"] else None,
            "highest_price": float(row["highest_price"]) if row["highest_price"] else None,
            "entry_date":    row["entry_date"].isoformat() if row["entry_date"] else None,
        }

    def clear_entry_ctx(self, symbol: str):
        with self._db() as (conn, cur):
            cur.execute("DELETE FROM bot_entry_context WHERE symbol = %s", (symbol,))
            conn.commit()

    # ── Symbol scores ─────────────────────────────────────────────

    def update_symbol_score(self, symbol: str, won: bool, pnl: float):
        with self._db() as (conn, cur):
            cur.execute(
                "SELECT score, wins, losses, total_pnl FROM bot_symbol_scores WHERE symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()

            if row:
                score     = float(row["score"])
                wins      = int(row["wins"])
                losses    = int(row["losses"])
                total_pnl = float(row["total_pnl"])
            else:
                score, wins, losses, total_pnl = 0.5, 0, 0, 0.0

            if won:
                wins  += 1
                score  = round(score + 0.1 * (1.0 - score), 4)
            else:
                losses += 1
                score   = round(score - 0.1 * score, 4)
            total_pnl = round(total_pnl + pnl, 2)

            cur.execute("""
                INSERT INTO bot_symbol_scores
                    (symbol, score, wins, losses, total_pnl, last_updated, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (symbol) DO UPDATE SET
                    score        = EXCLUDED.score,
                    wins         = EXCLUDED.wins,
                    losses       = EXCLUDED.losses,
                    total_pnl    = EXCLUDED.total_pnl,
                    last_updated = EXCLUDED.last_updated,
                    updated_at   = NOW()
            """, (symbol, score, wins, losses, total_pnl, date.today()))
            conn.commit()

    def get_symbol_score(self, symbol: str) -> float:
        with self._db() as (conn, cur):
            cur.execute(
                "SELECT score FROM bot_symbol_scores WHERE symbol = %s",
                (symbol,)
            )
            row = cur.fetchone()
        return float(row["score"]) if row else 0.5

    def get_top_symbols(self, n: int = 10) -> list:
        with self._db() as (conn, cur):
            cur.execute("""
                SELECT symbol, score, wins, losses, total_pnl, last_updated
                FROM bot_symbol_scores
                ORDER BY score DESC
                LIMIT %s
            """, (n,))
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_bottom_symbols(self, n: int = 5) -> list:
        with self._db() as (conn, cur):
            cur.execute("""
                SELECT symbol, score, wins, losses, total_pnl, last_updated
                FROM bot_symbol_scores
                ORDER BY score ASC
                LIMIT %s
            """, (n,))
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ── Regime stats ──────────────────────────────────────────────

    def update_regime_stat(self, regime: str, won: bool, pnl: float):
        with self._db() as (conn, cur):
            cur.execute("""
                INSERT INTO bot_regime_stats (regime, wins, losses, total_pnl)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (regime) DO UPDATE SET
                    wins      = bot_regime_stats.wins      + EXCLUDED.wins,
                    losses    = bot_regime_stats.losses    + EXCLUDED.losses,
                    total_pnl = bot_regime_stats.total_pnl + EXCLUDED.total_pnl,
                    updated_at = NOW()
            """, (regime, 1 if won else 0, 0 if won else 1, round(pnl, 2)))
            conn.commit()

    def get_regime_win_rate(self, regime: str) -> Optional[float]:
        with self._db() as (conn, cur):
            cur.execute(
                "SELECT wins, losses FROM bot_regime_stats WHERE regime = %s",
                (regime,)
            )
            row = cur.fetchone()
        if not row:
            return None
        total = int(row["wins"]) + int(row["losses"])
        return round(int(row["wins"]) / total, 3) if total > 0 else None

    # ── Resumen en log ────────────────────────────────────────────

    def log_summary(self):
        perf = self.get_performance_summary(days=30)
        if perf:
            logger.info(
                f"[MEMORIA-PG] {perf['days']} dias | "
                f"PnL acum=${perf['total_pnl']:+.2f} | "
                f"Win rate={perf['win_rate']:.0%} | "
                f"Trades={perf['total_trades']} | "
                f"Mejor dia=${perf['best_day']:+.2f} | "
                f"Peor dia=${perf['worst_day']:+.2f}"
            )

        stats = self.get_win_stats(last_n=20)
        if stats and stats["total"] >= 3:
            logger.info(
                f"[MEMORIA-PG] Ultimos {stats['total']} trades | "
                f"Wins={stats['wins']} Losses={stats['losses']} | "
                f"Avg win=${stats['avg_win']:+.2f} | "
                f"Avg loss=${stats['avg_loss']:+.2f} | "
                f"PnL total=${stats['total_pnl']:+.2f}"
            )

        with self._db() as (conn, cur):
            cur.execute(
                "SELECT trained_date FROM bot_ml_training ORDER BY trained_date DESC LIMIT 1"
            )
            row = cur.fetchone()
        if row:
            days_ago = (date.today() - row["trained_date"]).days
            logger.info(f"[MEMORIA-PG] Modelo ML entrenado hace {days_ago} dias "
                        f"(retrain cada 7 dias)")

        top = self.get_top_symbols(3)
        bot = self.get_bottom_symbols(3)
        if top:
            top_str = ", ".join(f"{s['symbol']}={float(s['score']):.2f}" for s in top)
            bot_str = ", ".join(f"{s['symbol']}={float(s['score']):.2f}" for s in bot)
            logger.info(f"[MEMORIA-PG] Scores | Top: {top_str} | Bottom: {bot_str}")

        with self._db() as (conn, cur):
            cur.execute("SELECT * FROM bot_regime_stats")
            rows = cur.fetchall()
        if rows:
            parts = []
            for r in rows:
                total = int(r["wins"]) + int(r["losses"])
                if total > 0:
                    wr = int(r["wins"]) / total
                    parts.append(
                        f"{r['regime']}: {wr:.0%} ({total} trades, ${float(r['total_pnl']):+.0f})"
                    )
            if parts:
                logger.info(f"[MEMORIA-PG] Por regimen | " + " | ".join(parts))

    # ── Migración desde JSON ──────────────────────────────────────

    def migrate_from_json(self, json_path: str = "reports/bot_memory.json"):
        import json, os
        if not os.path.exists(json_path):
            logger.info(f"[MIGRATE] No existe {json_path} — nada que migrar.")
            return

        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)

        migrated = 0

        for r in data.get("performance_history", []):
            try:
                win_rate = round(r["wins"] / r["trades"], 3) if r.get("trades", 0) > 0 else None
                with self._db() as (conn, cur):
                    cur.execute("""
                        INSERT INTO bot_performance
                            (perf_date, equity, pnl, trades, wins, losses, win_rate)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (perf_date) DO NOTHING
                    """, (r["date"], r["equity"], r["pnl"],
                          r["trades"], r["wins"], r["losses"], win_rate))
                    conn.commit()
                migrated += 1
            except Exception as e:
                logger.warning(f"[MIGRATE] performance row: {e}")

        for t in data.get("trade_outcomes", []):
            try:
                with self._db() as (conn, cur):
                    cur.execute("""
                        INSERT INTO bot_trade_outcomes
                            (trade_date, symbol, buy_price, sell_price, qty, pnl, win, reason_sell)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (t["date"], t["symbol"], t["buy_price"], t["sell_price"],
                          t["qty"], t["pnl"], t["win"], t.get("reason_sell", "")))
                    conn.commit()
                migrated += 1
            except Exception as e:
                logger.warning(f"[MIGRATE] trade_outcome row: {e}")

        for symbol, s in data.get("symbol_scores", {}).items():
            try:
                with self._db() as (conn, cur):
                    cur.execute("""
                        INSERT INTO bot_symbol_scores
                            (symbol, score, wins, losses, total_pnl, last_updated)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (symbol) DO NOTHING
                    """, (symbol, s["score"], s["wins"], s["losses"],
                          s["total_pnl"], s.get("last_updated")))
                    conn.commit()
                migrated += 1
            except Exception as e:
                logger.warning(f"[MIGRATE] symbol_score {symbol}: {e}")

        for regime, rs in data.get("regime_stats", {}).items():
            try:
                with self._db() as (conn, cur):
                    cur.execute("""
                        INSERT INTO bot_regime_stats (regime, wins, losses, total_pnl)
                        VALUES (%s, %s, %s, %s)
                        ON CONFLICT (regime) DO NOTHING
                    """, (regime, rs["wins"], rs["losses"], rs["total_pnl"]))
                    conn.commit()
                migrated += 1
            except Exception as e:
                logger.warning(f"[MIGRATE] regime_stat {regime}: {e}")

        last_trained = data.get("last_trained")
        if last_trained:
            try:
                with self._db() as (conn, cur):
                    cur.execute(
                        "INSERT INTO bot_ml_training (trained_date) VALUES (%s) ON CONFLICT DO NOTHING",
                        (last_trained,)
                    )
                    conn.commit()
                migrated += 1
            except Exception as e:
                logger.warning(f"[MIGRATE] last_trained: {e}")

        logger.info(f"[MIGRATE] Migración completada. {migrated} registros importados desde {json_path}")
