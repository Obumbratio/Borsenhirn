"""Tests de borsenhirn.ml.labeling (triple-barrier method)."""

import numpy as np
import pandas as pd
import pytest

from borsenhirn.ml.labeling import (
    TripleBarrierConfig,
    estimate_volatility,
    triple_barrier,
)


@pytest.fixture
def rising_price_series():
    """Serie que sube monotónicamente — debería tocar PT casi siempre."""
    return pd.Series(100 + np.arange(500) * 0.5)


@pytest.fixture
def falling_price_series():
    """Serie que baja monotónicamente — debería tocar SL casi siempre."""
    return pd.Series(200 - np.arange(500) * 0.5)


@pytest.fixture
def flat_price_series():
    """Serie plana — debería expirar en vertical."""
    return pd.Series(np.full(500, 100.0))


# ── estimate_volatility ───────────────────────────────────


def test_estimate_volatility_returns_non_negative(rising_price_series):
    v = estimate_volatility(rising_price_series, span=20)
    assert (v >= 0).all()


def test_estimate_volatility_no_nans_after_fill(rising_price_series):
    v = estimate_volatility(rising_price_series, span=20)
    assert v.notna().all()


def test_estimate_volatility_rolling_method_works(rising_price_series):
    v = estimate_volatility(rising_price_series, span=20, method="rolling")
    assert len(v) == len(rising_price_series)


def test_estimate_volatility_rejects_invalid_method(rising_price_series):
    with pytest.raises(ValueError):
        estimate_volatility(rising_price_series, method="magic")


# ── triple_barrier: tocar PT ──────────────────────────────


def test_triple_barrier_rising_tends_to_hit_pt(rising_price_series):
    vol = pd.Series(0.01, index=rising_price_series.index)  # vol constante
    events = np.array([50, 100, 150, 200, 250, 300, 350])
    out = triple_barrier(
        rising_price_series, events, vol,
        TripleBarrierConfig(pt_mult=1.0, sl_mult=1.0, max_holding=20),
    )
    pt_rate = (out["barrier"] == "pt").mean()
    assert pt_rate > 0.8, f"esperaba >80% PT, got {pt_rate:.2%}"


# ── triple_barrier: tocar SL ──────────────────────────────


def test_triple_barrier_falling_tends_to_hit_sl(falling_price_series):
    vol = pd.Series(0.01, index=falling_price_series.index)
    events = np.array([50, 100, 150, 200, 250, 300, 350])
    out = triple_barrier(
        falling_price_series, events, vol,
        TripleBarrierConfig(pt_mult=1.0, sl_mult=1.0, max_holding=20),
    )
    sl_rate = (out["barrier"] == "sl").mean()
    assert sl_rate > 0.8


# ── triple_barrier: vertical ──────────────────────────────


def test_triple_barrier_flat_expires_vertical(flat_price_series):
    vol = pd.Series(0.1, index=flat_price_series.index)  # barrera ancha
    events = np.array([50, 100, 150, 200, 250])
    out = triple_barrier(
        flat_price_series, events, vol,
        TripleBarrierConfig(pt_mult=5.0, sl_mult=5.0, max_holding=10),
    )
    vert_rate = (out["barrier"] == "vertical").mean()
    assert vert_rate == 1.0


# ── triple_barrier: bin_meta consistency ──────────────────


def test_triple_barrier_bin_meta_matches_return_sign(rising_price_series):
    vol = pd.Series(0.01, index=rising_price_series.index)
    events = np.array([50, 100, 150, 200])
    out = triple_barrier(
        rising_price_series, events, vol,
        TripleBarrierConfig(pt_mult=1.0, sl_mult=1.0, max_holding=20),
    )
    # bin_meta = 1 sii ret > 0
    for _, row in out.iterrows():
        if row["ret"] > 0:
            assert row["bin_meta"] == 1
        else:
            assert row["bin_meta"] == 0


# ── triple_barrier: columnas esperadas ────────────────────


def test_triple_barrier_output_schema(rising_price_series):
    vol = pd.Series(0.01, index=rising_price_series.index)
    out = triple_barrier(
        rising_price_series, np.array([50, 100]), vol,
        TripleBarrierConfig(),
    )
    expected = {"t_in", "t_out", "close_in", "close_out", "ret",
                "barrier", "bin_meta", "bin_dir", "side", "holding_bars"}
    assert expected.issubset(set(out.columns))


# ── triple_barrier: side (long/short) ─────────────────────


def test_triple_barrier_short_side_inverts_barriers(falling_price_series):
    """Para short en mercado bajista, debería tocar PT (ganancia)."""
    vol = pd.Series(0.01, index=falling_price_series.index)
    side = pd.Series(-1, index=falling_price_series.index)
    events = np.array([50, 100, 150, 200, 250])
    out = triple_barrier(
        falling_price_series, events, vol,
        TripleBarrierConfig(pt_mult=1.0, sl_mult=1.0, max_holding=20),
        side=side,
    )
    pt_rate = (out["barrier"] == "pt").mean()
    assert pt_rate > 0.8


# ── Edge cases ────────────────────────────────────────────


def test_triple_barrier_empty_events_returns_empty_df():
    close = pd.Series(100 + np.arange(100) * 0.5)
    vol = pd.Series(0.01, index=close.index)
    out = triple_barrier(close, np.array([], dtype=int), vol,
                         TripleBarrierConfig())
    assert out.empty


def test_triple_barrier_event_near_end_skipped():
    close = pd.Series(100 + np.arange(100) * 0.5)
    vol = pd.Series(0.01, index=close.index)
    # El último índice no puede generar trade (no hay ventana)
    out = triple_barrier(close, np.array([98, 99]), vol,
                         TripleBarrierConfig(max_holding=20))
    # evento 99 es el último, no hay futuro; evento 98 solo tiene 1 barra
    assert len(out) <= 1
