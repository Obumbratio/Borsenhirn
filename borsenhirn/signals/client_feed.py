"""
Feed de señal IMPERSONAL para el cliente (Paso 2 — Opción C, sin store).

La señal del cliente es el "cerebro compartido": modelo ML global (.pkl) + scanner
con `memory=None` → `symbol_score` neutral (0.5) para todos. Resultado: idéntico para
cualquier usuario (impersonal por construcción), sin tocar el aprendizaje per-tenant
(eso queda en el auto-trader interno).

Caché: la señal se calcula una vez y se sirve por `SIGNALS_CACHE_TTL` (def. 1h),
para no pegarle a Alpaca + correr el scanner en cada request. `get_client_signals()`
recomputa solo si está vencida.

⚠️ Client-safe: este módulo importa SOLO `borsenhirn.signals` + data/scanner/model
globales. NO importa el auto-trader (`borsenhirn.engine`/`internal.autotrader`), así
que el API de cliente puede usarlo sin cruzar la línea roja (ver guardrail).
"""

from __future__ import annotations

import os
import time
import logging
import threading
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_TTL_SEC = int(os.getenv("SIGNALS_CACHE_TTL", "3600"))  # 1h por defecto

_lock = threading.Lock()
_engine = None                       # SignalEngine "de la casa" (singleton lazy)
_cache: dict = {"value": None, "ts": 0.0}


def _build_engine():
    """Construye el SignalEngine compartido: modelo global + fetcher/scanner de la casa."""
    from ml_model import TradingModel
    from data_fetcher import DataFetcher
    from scanner import MarketScanner
    from borsenhirn.signals import SignalEngine

    model = TradingModel()
    model.load_model()                       # modelo global (.pkl), igual para todos
    fetcher = DataFetcher()                   # datos de mercado de la casa (config), impersonales
    scanner = MarketScanner(model=model, fetcher=fetcher)
    return SignalEngine(model=model, fetcher=fetcher, scanner=scanner)


def _compute() -> dict:
    """Corre un análisis impersonal (sin cuenta, sin memoria) y arma el payload."""
    global _engine
    if _engine is None:
        _engine = _build_engine()
    signals = _engine.analyze(
        memory=None,            # → symbol_score neutral 0.5 (impersonal)
        held=set(),             # sin cuenta: no hay posiciones
        plan_symbol=None,       # sin plan de usuario
        prev_regime=None,
        alert=lambda *a, **k: None,   # la señal del cliente no alerta a nadie
    )
    buys = [
        {
            "symbol": e.get("symbol"),
            "price": e.get("price"),
            "reason": (e.get("signal") or {}).get("reason"),
        }
        for e in signals.scan.get("buys", [])
    ]
    return {
        "regime": signals.regime,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "impersonal": True,
        "ttl_sec": _TTL_SEC,
        "signals": buys,
    }


def get_client_signals(force: bool = False) -> dict:
    """
    Devuelve la señal impersonal cacheada (recomputa si venció o `force=True`).
    El payload NO depende del usuario que llama — es el cerebro compartido.
    """
    now = time.monotonic()
    with _lock:
        cached = _cache["value"]
        if not force and cached is not None and (now - _cache["ts"]) < _TTL_SEC:
            return cached
        value = _compute()
        _cache["value"] = value
        _cache["ts"] = now
        return value


def reset_cache() -> None:
    """Limpia la caché (tests / cambios de config)."""
    with _lock:
        _cache["value"] = None
        _cache["ts"] = 0.0


__all__ = ["get_client_signals", "reset_cache"]
