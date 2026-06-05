"""
Fixtures comunes para todos los tests.

Evita duplicar código de setup (DataFrames sintéticos, mocks de executor,
stores in-memory) en cada archivo test_*.py.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ────────────────────────────────────────────────────────────────
# DataFrames sintéticos
# ────────────────────────────────────────────────────────────────

@pytest.fixture
def rng():
    """Generador reproducible (seed=42)."""
    return np.random.default_rng(42)


@pytest.fixture
def synthetic_ohlc_df(rng):
    """
    DataFrame OHLCV minimalista (150 filas) con índice datetime.
    Suficiente para la mayoría de tests que necesiten un df realista.
    """
    n = 150
    dates = pd.date_range("2024-01-01 09:30", periods=n, freq="1h")
    close = 100 + np.cumsum(rng.standard_normal(n) * 0.3)
    df = pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.003,
        "low": close * 0.997,
        "close": close,
        "volume": rng.integers(1000, 10000, n).astype(float),
    }, index=dates)
    return df


@pytest.fixture
def synthetic_df_with_indicators(synthetic_ohlc_df, rng):
    """DataFrame OHLCV + indicadores técnicos pre-calculados."""
    import config
    df = synthetic_ohlc_df.copy()
    n = len(df)
    df[f"sma_{config.MA_SHORT_WINDOW}"] = df["close"].rolling(
        config.MA_SHORT_WINDOW).mean()
    df[f"sma_{config.MA_LONG_WINDOW}"] = df["close"].rolling(
        config.MA_LONG_WINDOW).mean()
    df["rsi"] = 30 + rng.random(n) * 40   # entre 30-70
    df["atr"] = np.abs(rng.standard_normal(n) * 0.5) + 0.5
    df["MACD_12_26_9"] = rng.standard_normal(n) * 0.5
    df["MACDs_12_26_9"] = rng.standard_normal(n) * 0.5
    df["MACDh_12_26_9"] = df["MACD_12_26_9"] - df["MACDs_12_26_9"]
    bb_mid = df["close"].rolling(config.BB_WINDOW).mean()
    bb_std = df["close"].rolling(config.BB_WINDOW).std()
    df[f"BBL_{config.BB_WINDOW}_{float(config.BB_STD)}"] = bb_mid - 2 * bb_std
    df[f"BBM_{config.BB_WINDOW}_{float(config.BB_STD)}"] = bb_mid
    df[f"BBU_{config.BB_WINDOW}_{float(config.BB_STD)}"] = bb_mid + 2 * bb_std
    return df


# ────────────────────────────────────────────────────────────────
# Mocks de dominio
# ────────────────────────────────────────────────────────────────

class FakeExecutor:
    """
    Executor fake para tests. Registra todas las órdenes recibidas.
    """

    def __init__(self, accept: bool = True):
        self.accept = accept
        self.calls: List[Dict[str, Any]] = []
        self.closed: List[str] = []

    def submit_order(self, symbol, qty, side, order_type="market"):
        self.calls.append({
            "symbol": symbol, "qty": qty, "side": side,
            "order_type": order_type,
        })
        if not self.accept:
            return None
        return f"oid-{len(self.calls)}-{symbol}-{side}"

    def close_position(self, symbol):
        self.closed.append(symbol)
        return True

    def get_account(self):
        return {"equity": 100_000.0, "buying_power": 100_000.0,
                "cash": 100_000.0, "portfolio_value": 100_000.0}

    def get_positions(self):
        return []


@pytest.fixture
def fake_executor():
    return FakeExecutor()


@pytest.fixture
def failing_executor():
    return FakeExecutor(accept=False)


# ────────────────────────────────────────────────────────────────
# Alert manager de pruebas (captura llamadas)
# ────────────────────────────────────────────────────────────────

class _CapturingChannel:
    """Canal que no envía nada, solo registra calls para assertions."""
    name = "capture"

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    def send(self, level, subject, body, meta=None):
        self.calls.append({
            "level": level, "subject": subject,
            "body": body, "meta": meta,
        })
        return True


@pytest.fixture
def capturing_channel():
    return _CapturingChannel()


@pytest.fixture
def alert_mgr_capture(capturing_channel):
    """AlertManager con un único canal que captura todas las alertas."""
    from borsenhirn.safety.alerts import AlertLevel, AlertManager
    mgr = AlertManager([capturing_channel], dedupe_window_sec=1,
                       min_level=AlertLevel.INFO)
    mgr._capturing = capturing_channel   # atajo para inspeccionar en tests
    return mgr


# ────────────────────────────────────────────────────────────────
# KillSwitch con store in-memory
# ────────────────────────────────────────────────────────────────

@pytest.fixture
def in_memory_killswitch(alert_mgr_capture):
    """KillSwitch con InMemoryStateStore. Se resetea entre tests."""
    from borsenhirn.safety.killswitch import (
        InMemoryStateStore, KillSwitch, KillSwitchConfig,
    )
    store = InMemoryStateStore()
    ks = KillSwitch(
        store=store,
        alert_send=lambda subject, body, **meta:
            alert_mgr_capture.critical(subject, body, **meta),
        config=KillSwitchConfig(
            max_daily_loss_pct=0.05,
            max_drawdown_7d_pct=0.15,
            max_consecutive_failures=5,
        ),
    )
    return ks


# ────────────────────────────────────────────────────────────────
# Sanity checker con defaults de producción
# ────────────────────────────────────────────────────────────────

@pytest.fixture
def sanity_checker():
    from borsenhirn.safety.sanity import SanityChecker, SanityConfig
    return SanityChecker(SanityConfig(
        max_position_pct=0.06,
        max_qty_per_order=10_000,
        min_price=0.5,
        max_price=100_000,
        wash_trade_min_gap_sec=300,
        watchlist_required=True,
    ))


# ────────────────────────────────────────────────────────────────
# Gate de tests de integración con DB real (B1 5.6)
# ────────────────────────────────────────────────────────────────
# Los tests marcados `@pytest.mark.integration` tocan Postgres real y NO
# corren en la suite normal. Se saltan salvo que se setee RUN_DB_INTEGRATION.
# Esto mantiene la baseline verde y, sobre todo, evita golpear cualquier DB
# por accidente en CI o en un run distraído.
def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_DB_INTEGRATION"):
        return
    skip_db = pytest.mark.skip(
        reason="integración con DB real: setear RUN_DB_INTEGRATION=1 "
               "(y `source .env.dev`) para correr"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_db)
