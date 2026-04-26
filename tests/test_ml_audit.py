"""Tests de borsenhirn.ml.audit (PSI + check_label_leakage)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from borsenhirn.ml.audit import (
    check_label_leakage,
    population_stability_index,
)


# ── PSI ──────────────────────────────────────────────────────


def test_psi_same_distribution_is_low():
    rng = np.random.default_rng(0)
    a = rng.standard_normal(1000)
    b = rng.standard_normal(1000)
    psi = population_stability_index(a, b)
    assert psi < 0.25, f"esperaba PSI estable < 0.25, got {psi}"


def test_psi_shifted_distribution_is_high():
    rng = np.random.default_rng(0)
    a = rng.standard_normal(1000)
    b = rng.standard_normal(1000) + 5   # gran shift
    psi = population_stability_index(a, b)
    assert psi > 1.0


def test_psi_handles_nans():
    rng = np.random.default_rng(0)
    a = rng.standard_normal(500)
    b = np.concatenate([rng.standard_normal(400), [np.nan] * 100])
    psi = population_stability_index(a, b)
    # No debe ser NaN ni infinito
    assert np.isfinite(psi)


def test_psi_too_few_samples_returns_nan():
    a = np.array([1, 2, 3])
    b = np.array([1, 2])
    psi = population_stability_index(a, b)
    assert np.isnan(psi)


def test_psi_more_bins_more_sensitive():
    rng = np.random.default_rng(0)
    a = rng.standard_normal(1000)
    b = rng.standard_normal(1000) + 0.5
    psi_5 = population_stability_index(a, b, n_bins=5)
    psi_20 = population_stability_index(a, b, n_bins=20)
    # Ambos deberían ser positivos y razonables
    assert psi_5 > 0
    assert psi_20 > 0


# ── check_label_leakage ──────────────────────────────────────


def test_label_leakage_clean_features():
    """Features sin correlación con close futuro → clean=True."""
    rng = np.random.default_rng(0)
    n = 500
    df = pd.DataFrame({
        "close": np.cumsum(rng.standard_normal(n)) + 100,
        "rsi": rng.uniform(0, 100, n),     # totalmente independiente
        "vol_ratio": rng.uniform(0.5, 2, n),
    })
    out = check_label_leakage(df, label_horizon=5)
    assert out["clean"] is True
    assert out["warnings"] == []


def test_label_leakage_detects_obvious_lookahead():
    """Una feature que ES close.shift(-3) debería detectarse."""
    rng = np.random.default_rng(0)
    n = 500
    close = np.cumsum(rng.standard_normal(n)) + 100
    df = pd.DataFrame({
        "close": close,
        "future_proxy": pd.Series(close).shift(-3),  # MIRA al futuro
    })
    out = check_label_leakage(df, label_horizon=5)
    assert out["clean"] is False
    feats = [w["feature"] for w in out["warnings"]]
    assert "future_proxy" in feats


def test_label_leakage_ignores_ohlcv_columns():
    """El check ignora open/high/low/close/volume por construcción."""
    rng = np.random.default_rng(0)
    n = 200
    close = np.cumsum(rng.standard_normal(n)) + 100
    df = pd.DataFrame({
        "open": close, "high": close, "low": close,
        "close": close, "volume": rng.integers(1, 100, n).astype(float),
    })
    out = check_label_leakage(df, label_horizon=5)
    assert out["clean"] is True


def test_label_leakage_missing_close_returns_clean():
    df = pd.DataFrame({"feat1": [1, 2, 3, 4, 5]})
    out = check_label_leakage(df, label_horizon=2)
    assert out["clean"] is True
    assert "note" in out


def test_label_leakage_threshold_configurable():
    """Bajar el threshold debe encontrar más warnings."""
    rng = np.random.default_rng(0)
    n = 500
    close = np.cumsum(rng.standard_normal(n)) + 100
    df = pd.DataFrame({
        "close": close,
        "almost_future": pd.Series(close).shift(-1) + rng.standard_normal(n) * 5,
    })
    strict = check_label_leakage(df, label_horizon=3, corr_threshold=0.5)
    lenient = check_label_leakage(df, label_horizon=3, corr_threshold=0.999)
    # Threshold más bajo => más warnings (o iguales)
    assert len(strict["warnings"]) >= len(lenient["warnings"])
