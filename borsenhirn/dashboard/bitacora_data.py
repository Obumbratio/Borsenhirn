"""
bitacora_data.py — Capa unificada de datos para el dashboard "Bitácora Nocturna".

PROBLEMA QUE RESUELVE
─────────────────────
El dashboard original llamaba a varios endpoints de bot_api.py de forma directa
y, cuando alguno fallaba (típicamente /status.account si el SDK de Alpaca tiene
hiccups), las métricas mostraban $0 / 0% / "—" mientras que /portfolio (que
hace la misma llamada por su cuenta) seguía funcionando. Resultado:
incoherencia visual (Vermögen $0.00 con +3.76% delta).

ESTE MÓDULO
───────────
1. Llama a /status, /portfolio y /trades/list y MERGEA las respuestas para que
   cada métrica tenga al menos una fuente viva.
2. Cuando el backend no expone una métrica que el dashboard necesita
   (CPI, Fed Funds Rate), llama directamente al módulo M2.MacroFetcher
   (read-only · solo .fetch(), no modifica nada) o cae a yFinance para VIX.
3. Para cada métrica devuelve un MetricSnap con .value, .source ("live"/
   "cache"/"fallback"/"missing") y .stale (bool). Permite al render mostrar un
   indicador discreto cuando el valor no es fresh.
4. Cachea en disco (~/.borsenhirn/bitacora_market_cache.json) con TTLs para
   sobrevivir reinicios y degradación de APIs externas. Compatible con la
   eventual migración a Redis (TODO documentado).

REGLA DURA RESPETADA
────────────────────
- NO toca bot_api.py, data_fetcher.py, ni borsenhirn/api/main.py.
- Solo importa M2.MacroFetcher como caller read-only.
- Si M2 o sus deps no están disponibles, falla limpio y muestra "missing".
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from .bitacora_state import STATE_DIR

__all__ = [
    "MetricSnap",
    "DataPayload",
    "build_payload",
    "MARKET_CACHE_PATH",
    "DATA_SOURCE_MAP",
]

API_URL = os.environ.get("BORSENHIRN_API_URL", "http://localhost:8000")
MARKET_CACHE_PATH = STATE_DIR / "bitacora_market_cache.json"

# TTLs por tipo de dato · seg.
TTL_ACCOUNT_S = 30        # equity, cash · cambia minuto a minuto
TTL_REGIME_S = 600        # 10 min · regime no cambia tan rápido
TTL_VIX_S = 300           # 5 min
TTL_MACRO_S = 6 * 3600    # 6 hs · CPI/Fed cambian mensualmente
TTL_TRADES_S = 30


# Mapping declarativo · usado por la doc autogenerada y por los tests
DATA_SOURCE_MAP = {
    "equity":         {"primary": "/portfolio.account.equity",
                       "fallback": "/status.account.equity"},
    "cash":           {"primary": "/portfolio.account.cash",
                       "fallback": "/status.account.cash"},
    "buying_power":   {"primary": "/portfolio.account.buying_power",
                       "fallback": "/status.account.buying_power"},
    "day_pl":         {"primary": "/portfolio.account.day_pl",
                       "fallback": "/status.account.day_pl"},
    "day_pl_pct":     {"primary": "/portfolio.account.day_pl_pct",
                       "fallback": "/status.account.day_pl_pct"},
    "positions":      {"primary": "/portfolio.positions",
                       "fallback": "[]"},
    "regime":         {"primary": "/status.regime.regime",
                       "fallback": "cache · ~/.borsenhirn/bitacora_market_cache.json"},
    "confidence":     {"primary": "/status.regime.confidence",
                       "fallback": "cache"},
    "vix":            {"primary": "/status.regime.vix",
                       "fallback": "yfinance:^VIX → cache"},
    "cpi":            {"primary": "m2_analyst.MacroFetcher · FRED:CPIAUCSL",
                       "fallback": "cache"},
    "cpi_change":     {"primary": "m2_analyst.MacroFetcher · FRED:CPIAUCSL.change",
                       "fallback": "cache"},
    "fed_rate":       {"primary": "m2_analyst.MacroFetcher · FRED:FEDFUNDS",
                       "fallback": "cache"},
    "fed_rate_trend": {"primary": "m2_analyst.MacroFetcher · FRED:FEDFUNDS.trend",
                       "fallback": "cache"},
    "win_rate":       {"primary": "computed from /trades/list[pnl>0] / total_closed",
                       "fallback": "memory.wins_today / memory.trades_today"},
    "trades_today":   {"primary": "/status.memory.trades_today",
                       "fallback": "0"},
    "trades_closed":  {"primary": "len([t for t in /trades/list if t.pnl is not None])",
                       "fallback": "0"},
}


# ─── Tipos ───────────────────────────────────────────────────────────────────

@dataclass
class MetricSnap:
    value: Any
    source: str = "live"        # 'live' | 'cache' | 'fallback' | 'missing'
    stale: bool = False
    fetched_at: Optional[str] = None
    error: Optional[str] = None

    @property
    def is_fresh(self) -> bool:
        return self.source == "live" and not self.stale


@dataclass
class DataPayload:
    # Cuenta · todo del mismo snapshot Alpaca para garantizar coherencia
    equity: MetricSnap = field(default_factory=lambda: MetricSnap(0.0, "missing", True))
    cash: MetricSnap = field(default_factory=lambda: MetricSnap(0.0, "missing", True))
    buying_power: MetricSnap = field(default_factory=lambda: MetricSnap(0.0, "missing", True))
    day_pl: MetricSnap = field(default_factory=lambda: MetricSnap(0.0, "missing", True))
    day_pl_pct: MetricSnap = field(default_factory=lambda: MetricSnap(0.0, "missing", True))
    cumulative_pnl: MetricSnap = field(default_factory=lambda: MetricSnap(0.0, "missing", True))

    # Regime + macro
    regime: MetricSnap = field(default_factory=lambda: MetricSnap("—", "missing", True))
    confidence: MetricSnap = field(default_factory=lambda: MetricSnap(0.0, "missing", True))
    vix: MetricSnap = field(default_factory=lambda: MetricSnap(0.0, "missing", True))
    cpi: MetricSnap = field(default_factory=lambda: MetricSnap(None, "missing", True))
    cpi_change: MetricSnap = field(default_factory=lambda: MetricSnap(None, "missing", True))
    fed_rate: MetricSnap = field(default_factory=lambda: MetricSnap(None, "missing", True))
    fed_rate_trend: MetricSnap = field(default_factory=lambda: MetricSnap("flat", "missing", True))

    # Trades / memoria
    trades_today: MetricSnap = field(default_factory=lambda: MetricSnap(0, "missing", True))
    wins_today: MetricSnap = field(default_factory=lambda: MetricSnap(0, "missing", True))
    losses_today: MetricSnap = field(default_factory=lambda: MetricSnap(0, "missing", True))
    win_rate: MetricSnap = field(default_factory=lambda: MetricSnap(0.0, "missing", True))
    trades_closed: MetricSnap = field(default_factory=lambda: MetricSnap(0, "missing", True))

    # Listas crudas · para gráficas e iteración
    positions: List[dict] = field(default_factory=list)
    trades: List[dict] = field(default_factory=list)
    equity_history: List[dict] = field(default_factory=list)
    perf_history: List[dict] = field(default_factory=list)

    # Bot-level
    bot_mode: str = "PAPER"
    bot_last_cycle: Optional[str] = None
    bot_watchlist_size: int = 44
    api_online: bool = False
    alpaca_ok: bool = False

    def metrics_with_indicator(self) -> List[str]:
        """Returns nombres de métricas que NO están live · para diagnóstico."""
        out = []
        for name in ("equity","cash","buying_power","day_pl","day_pl_pct",
                     "cumulative_pnl","regime","confidence","vix","cpi",
                     "cpi_change","fed_rate","fed_rate_trend","win_rate"):
            snap = getattr(self, name, None)
            if isinstance(snap, MetricSnap) and snap.source != "live":
                out.append(f"{name}:{snap.source}")
        return out


# ─── Cache helpers ───────────────────────────────────────────────────────────

def _read_cache() -> Dict[str, dict]:
    if not MARKET_CACHE_PATH.exists():
        return {}
    try:
        with MARKET_CACHE_PATH.open("r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def _write_cache(cache: Dict[str, dict]) -> None:
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = MARKET_CACHE_PATH.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
        os.replace(tmp, MARKET_CACHE_PATH)
    except Exception:
        pass  # cache es best-effort


def _cache_get(cache: dict, key: str, ttl: int) -> Tuple[Any, bool]:
    """
    Devuelve (value, stale).
    stale=True si: existe pero excedió TTL · seguimos sirviéndolo de todos modos.
    Devuelve (None, True) si no existe.
    """
    entry = cache.get(key)
    if not entry:
        return None, True
    try:
        ts = datetime.fromisoformat(entry["ts"])
        age = (datetime.now() - ts).total_seconds()
        return entry.get("value"), age > ttl
    except Exception:
        return entry.get("value"), True


def _cache_set(cache: dict, key: str, value: Any) -> None:
    cache[key] = {"value": value, "ts": datetime.now().isoformat(timespec="seconds")}


# ─── Fetchers ────────────────────────────────────────────────────────────────

def _http_get(path: str, timeout: int = 5) -> Optional[dict]:
    try:
        r = requests.get(f"{API_URL}{path}", timeout=timeout)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _fetch_status() -> dict:
    return _http_get("/status", timeout=5) or {}


def _fetch_portfolio(period: str = "1D") -> dict:
    return _http_get(f"/portfolio?period={period}", timeout=8) or {}


def _fetch_trades(limit: int = 200) -> List[dict]:
    data = _http_get(f"/trades/list?limit={limit}", timeout=5)
    return data if isinstance(data, list) else []


def _fetch_perf_history(days: int = 30) -> List[dict]:
    data = _http_get(f"/performance/history?days={days}", timeout=5)
    if isinstance(data, dict):
        return data.get("history", []) or []
    return []


def _api_online() -> bool:
    return _http_get("/health", timeout=3) is not None


def _fetch_macro_via_m2() -> Tuple[Optional[dict], Optional[str]]:
    """
    Llama a m2_analyst.MacroFetcher directamente. Read-only.
    Devuelve (data, error). data = {fed_rate:{value,change,trend}, cpi:{...}, ...}
    """
    try:
        from m2_analyst import MacroFetcher  # type: ignore
        fetcher = MacroFetcher()
        data = fetcher.fetch()
        if data:
            return data, None
        return None, "fred_no_data"
    except ImportError as e:
        return None, f"import:{e}"
    except Exception as e:
        return None, f"{type(e).__name__}:{e}"


def _fetch_vix_yfinance() -> Tuple[Optional[float], Optional[str]]:
    """Fallback para VIX cuando /status.regime.vix está vacío."""
    try:
        import yfinance as yf  # type: ignore
        t = yf.Ticker("^VIX")
        hist = t.history(period="2d", interval="1d")
        if hist is not None and not hist.empty:
            return float(hist["Close"].iloc[-1]), None
        return None, "yf_empty"
    except ImportError as e:
        return None, f"import:{e}"
    except Exception as e:
        return None, f"{type(e).__name__}:{e}"


# ─── Mergers ─────────────────────────────────────────────────────────────────

def _pick_account_field(field: str,
                         portfolio: dict,
                         status: dict) -> Optional[float]:
    """
    Lee un campo de cuenta priorizando /portfolio (fuente directa Alpaca) y
    cayendo a /status.account si la primera no tiene valor.
    """
    pa = (portfolio or {}).get("account", {}) or {}
    sa = (status or {}).get("account", {}) or {}
    v = pa.get(field)
    if v not in (None, 0, 0.0):
        return v
    v = sa.get(field)
    if v not in (None, 0, 0.0):
        return v
    # Si ambos son 0 o None, devolvemos 0 (puede ser legítimamente $0).
    return pa.get(field) if pa else sa.get(field)


def _make_snap(value: Any, source: str, *,
                cache: dict = None,
                cache_key: str = None,
                stale: bool = False,
                error: str = None) -> MetricSnap:
    """
    Factory. Si value no es válido y existe cache, sirve el cacheado con
    stale=True. Si tampoco hay cache, devuelve missing.
    """
    if value not in (None, "—") and value != 0 or source == "live":
        if cache is not None and cache_key and value is not None:
            _cache_set(cache, cache_key, value)
        return MetricSnap(
            value=value, source=source, stale=stale,
            fetched_at=datetime.now().isoformat(timespec="seconds"),
            error=error,
        )
    if cache is not None and cache_key:
        cached_val, _ = _cache_get(cache, cache_key, ttl=10**9)  # cualquier edad sirve
        if cached_val is not None:
            return MetricSnap(
                value=cached_val, source="cache", stale=True,
                fetched_at=cache.get(cache_key, {}).get("ts"),
                error=error,
            )
    return MetricSnap(value=value, source="missing" if value is None else source,
                      stale=True, error=error)


# ─── Entrypoint público ──────────────────────────────────────────────────────

def build_payload() -> DataPayload:
    """
    Recoge todos los datos necesarios para renderizar el dashboard, mergea
    fuentes, aplica fallbacks y devuelve un DataPayload coherente.

    Es el único punto de entrada que el dashboard.py debe usar.
    """
    payload = DataPayload()
    cache = _read_cache()

    # ── 1. Health check ──
    payload.api_online = _api_online()
    if not payload.api_online:
        # Sin backend: devolvemos lo que haya cacheado, todo stale.
        for fname in ("equity","cash","buying_power","day_pl","day_pl_pct",
                      "vix","cpi","fed_rate","cumulative_pnl","win_rate"):
            cached_val, _ = _cache_get(cache, fname, ttl=10**9)
            if cached_val is not None:
                setattr(payload, fname,
                        MetricSnap(cached_val, "cache", True))
        return payload

    # ── 2. Bot status (incluye account + regime + memory) ──
    status = _fetch_status()
    portfolio = _fetch_portfolio("1D")
    trades = _fetch_trades(limit=200)
    perf_history = _fetch_perf_history(days=30)
    payload.trades = trades
    payload.perf_history = perf_history

    bot = (status or {}).get("bot", {}) or {}
    payload.bot_mode = "LIVE" if bot.get("live_mode") else "PAPER"
    payload.bot_last_cycle = bot.get("last_cycle")
    payload.bot_watchlist_size = int(bot.get("watchlist_size", 44) or 44)

    # ── 3. Account · merge portfolio + status ──
    for f in ("equity","cash","buying_power","day_pl","day_pl_pct"):
        val = _pick_account_field(f, portfolio, status)
        if val is None:
            val = 0.0
        try:
            val = float(val)
        except Exception:
            val = 0.0
        snap = _make_snap(val, "live" if val else "missing",
                          cache=cache, cache_key=f"account.{f}")
        setattr(payload, f, snap)

    payload.alpaca_ok = bool(payload.equity.value)
    payload.equity_history = (portfolio or {}).get("equity_history", []) or []
    payload.positions = (portfolio or {}).get("positions", []) or []

    # ── 4. P&L acumulado · derived from trades cerrados ──
    sells = [t for t in trades if t.get("pnl") is not None]
    cumulative = sum((t.get("pnl") or 0) for t in sells)
    payload.cumulative_pnl = _make_snap(
        float(cumulative), "live" if sells else "missing",
        cache=cache, cache_key="cumulative_pnl",
    )
    payload.trades_closed = _make_snap(
        len(sells), "live", cache=cache, cache_key="trades_closed",
    )

    # ── 5. Win rate · computed from sells ──
    if sells:
        wins = sum(1 for t in sells if (t.get("pnl") or 0) > 0)
        wr = (wins / len(sells)) * 100
        payload.win_rate = _make_snap(round(wr, 1), "live",
                                       cache=cache, cache_key="win_rate")
    else:
        # Fallback: usar memory.wins_today/trades_today si existe
        memory = (status or {}).get("memory", {}) or {}
        tt = int(memory.get("trades_today", 0) or 0)
        wt = int(memory.get("wins_today", 0) or 0)
        if tt > 0:
            payload.win_rate = _make_snap(round(wt/tt*100, 1), "live",
                                           cache=cache, cache_key="win_rate")
        else:
            payload.win_rate = _make_snap(0.0, "missing",
                                           cache=cache, cache_key="win_rate")

    # ── 6. Memory ──
    memory = (status or {}).get("memory", {}) or {}
    payload.trades_today = MetricSnap(int(memory.get("trades_today", 0) or 0), "live")
    payload.wins_today = MetricSnap(int(memory.get("wins_today", 0) or 0), "live")
    payload.losses_today = MetricSnap(int(memory.get("losses_today", 0) or 0), "live")

    # ── 7. Regime + confidence + VIX ──
    regime_dict = (status or {}).get("regime", {}) or {}
    rg = regime_dict.get("regime") or "—"
    conf = float(regime_dict.get("confidence", 0) or 0)
    vix = float(regime_dict.get("vix", 0) or 0)

    if rg and rg != "—":
        payload.regime = _make_snap(rg, "live",
                                     cache=cache, cache_key="regime")
    else:
        cached_val, _ = _cache_get(cache, "regime", ttl=10**9)
        payload.regime = MetricSnap(
            cached_val or "—",
            "cache" if cached_val else "missing",
            True,
        )

    if conf > 0:
        payload.confidence = _make_snap(conf, "live",
                                         cache=cache, cache_key="confidence")
    else:
        cached_val, _ = _cache_get(cache, "confidence", ttl=10**9)
        payload.confidence = MetricSnap(
            cached_val or 0.0,
            "cache" if cached_val else "missing",
            True,
        )

    # VIX · prioriza /status.regime.vix; fallback yfinance
    if vix > 0:
        payload.vix = _make_snap(vix, "live", cache=cache, cache_key="vix")
    else:
        v_yf, err = _fetch_vix_yfinance()
        if v_yf is not None:
            payload.vix = _make_snap(v_yf, "fallback",
                                      cache=cache, cache_key="vix")
        else:
            cached_val, _ = _cache_get(cache, "vix", ttl=10**9)
            if cached_val:
                payload.vix = MetricSnap(cached_val, "cache", True, error=err)
            else:
                payload.vix = MetricSnap(0.0, "missing", True, error=err)

    # ── 8. CPI + Fed Rate via M2.MacroFetcher (FRED) ──
    macro, err = _fetch_macro_via_m2()
    if macro:
        cpi_val = (macro.get("cpi") or {}).get("value")
        cpi_chg = (macro.get("cpi") or {}).get("change")
        fed_val = (macro.get("fed_rate") or {}).get("value")
        fed_trend = (macro.get("fed_rate") or {}).get("trend", "flat")
        if cpi_val is not None:
            payload.cpi = _make_snap(cpi_val, "live", cache=cache, cache_key="cpi")
            payload.cpi_change = _make_snap(cpi_chg, "live",
                                             cache=cache, cache_key="cpi_change")
        if fed_val is not None:
            payload.fed_rate = _make_snap(fed_val, "live",
                                           cache=cache, cache_key="fed_rate")
            payload.fed_rate_trend = _make_snap(fed_trend, "live",
                                                 cache=cache, cache_key="fed_rate_trend")
    if payload.cpi.source == "missing":
        cached_val, _ = _cache_get(cache, "cpi", ttl=10**9)
        if cached_val is not None:
            payload.cpi = MetricSnap(cached_val, "cache", True, error=err)
            cc, _ = _cache_get(cache, "cpi_change", ttl=10**9)
            if cc is not None:
                payload.cpi_change = MetricSnap(cc, "cache", True)
    if payload.fed_rate.source == "missing":
        cached_val, _ = _cache_get(cache, "fed_rate", ttl=10**9)
        if cached_val is not None:
            payload.fed_rate = MetricSnap(cached_val, "cache", True, error=err)
            ft, _ = _cache_get(cache, "fed_rate_trend", ttl=10**9)
            if ft is not None:
                payload.fed_rate_trend = MetricSnap(ft, "cache", True)

    _write_cache(cache)
    return payload
