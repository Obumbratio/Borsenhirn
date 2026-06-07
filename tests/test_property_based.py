"""
Property-based tests con hypothesis.

Estos tests no validan ejemplos específicos — validan **invariantes**
sobre el comportamiento, generando cientos de inputs aleatorios y
buscando contraejemplos. Si pasan, hay garantía mucho más fuerte que
con tests por casos.

Mantenelos rápidos (cap de ejemplos / deadline) para no bloquear CI.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from borsenhirn.safety.alerts import AlertLevel, AlertManager
from borsenhirn.safety.killswitch import (
    InMemoryStateStore,
    KillReason,
    KillSnapshot,
    KillSwitch,
    KillSwitchConfig,
)
from borsenhirn.safety.sanity import (
    OrderContext,
    SanityChecker,
    SanityConfig,
)
from borsenhirn.ml.validation import PurgedKFold
from borsenhirn.ml.labeling import (
    TripleBarrierConfig,
    estimate_volatility,
    triple_barrier,
)


# Settings comunes: rápido y reproducible
HYPOTHESIS_FAST = settings(
    max_examples=50,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
    derandomize=True,
)


# ────────────────────────────────────────────────────────────────
# Property 1 — Sanity SIEMPRE rechaza qty <= 0 o price <= 0
# ────────────────────────────────────────────────────────────────


def _sanity_default():
    return SanityChecker(SanityConfig(
        max_position_pct=0.5,        # generosos para no esconder otros checks
        max_qty_per_order=1_000_000,
    ))


@given(
    qty=st.integers(min_value=-1000, max_value=0),
    price=st.floats(min_value=1, max_value=1000, allow_nan=False),
)
@HYPOTHESIS_FAST
def test_property_qty_non_positive_always_rejected(qty, price):
    sc = _sanity_default()
    ctx = OrderContext(
        symbol="AAPL", action="buy", qty=qty, price=price,
        portfolio_value=100_000, watchlist=["AAPL"],
        current_positions={},
    )
    res = sc.validate(ctx)
    assert not res.ok, f"qty={qty} debió rechazarse, fue ok={res.ok} {res.reason}"


@given(
    price=st.one_of(
        st.floats(max_value=0.0, allow_nan=False, allow_infinity=False),
        st.just(float("nan")),
    ),
)
@HYPOTHESIS_FAST
def test_property_bad_price_always_rejected(price):
    sc = _sanity_default()
    ctx = OrderContext(
        symbol="AAPL", action="buy", qty=10, price=price,
        portfolio_value=100_000, watchlist=["AAPL"],
        current_positions={},
    )
    res = sc.validate(ctx)
    assert not res.ok


# ────────────────────────────────────────────────────────────────
# Property 2 — KillSwitch siempre dispara con pérdida diaria extrema
# ────────────────────────────────────────────────────────────────


def _make_ks(daily_pct=0.05):
    store = InMemoryStateStore()
    ks = KillSwitch(
        store=store,
        alert_send=lambda subject, body, **m: None,
        config=KillSwitchConfig(
            max_daily_loss_pct=daily_pct,
            max_drawdown_7d_pct=0.99,
            max_consecutive_failures=999,
        ),
    )
    return ks


@given(
    equity_start=st.floats(min_value=10_000, max_value=10_000_000,
                            allow_nan=False),
    loss_multiplier=st.floats(min_value=1.05, max_value=5.0,
                                allow_nan=False),
)
@HYPOTHESIS_FAST
def test_property_extreme_daily_loss_always_triggers(equity_start,
                                                      loss_multiplier):
    """Si pérdida diaria > limit_pct * equity_start, kill switch dispara."""
    ks = _make_ks(daily_pct=0.05)
    limit = 0.05 * equity_start
    pnl = -limit * loss_multiplier   # excede el límite
    snap = KillSnapshot(
        equity_now=equity_start + pnl,
        equity_day_start=equity_start,
        daily_pnl=pnl,
    )
    triggered = ks.check_all(snap)
    keys = [t.key for t in triggered]
    assert KillReason.MAX_DAILY_LOSS in keys, (
        f"esperaba MAX_DAILY_LOSS, got {keys} | "
        f"equity={equity_start} pnl={pnl} limit={-limit}"
    )


@given(
    equity_start=st.floats(min_value=10_000, max_value=10_000_000,
                            allow_nan=False),
    pnl_ratio=st.floats(min_value=-0.04, max_value=0.10, allow_nan=False),
)
@HYPOTHESIS_FAST
def test_property_modest_pnl_never_triggers_daily_loss(equity_start, pnl_ratio):
    """Si pérdida < 4% nunca debería disparar (límite es 5%)."""
    ks = _make_ks(daily_pct=0.05)
    pnl = equity_start * pnl_ratio
    snap = KillSnapshot(
        equity_now=equity_start + pnl,
        equity_day_start=equity_start,
        daily_pnl=pnl,
    )
    triggered = ks.check_all(snap)
    keys = [t.key for t in triggered]
    assert KillReason.MAX_DAILY_LOSS not in keys


# ────────────────────────────────────────────────────────────────
# Property 3 — PurgedKFold nunca tiene overlap train/test
# ────────────────────────────────────────────────────────────────


@given(
    n_splits=st.integers(min_value=2, max_value=8),
    horizon=st.integers(min_value=0, max_value=20),
    embargo_pct=st.floats(min_value=0.0, max_value=0.05, allow_nan=False),
    n=st.integers(min_value=200, max_value=2000),
)
@HYPOTHESIS_FAST
def test_property_purged_kfold_no_overlap(n_splits, horizon, embargo_pct, n):
    assume(n >= n_splits * 2)
    X = np.zeros((n, 3))
    cv = PurgedKFold(n_splits=n_splits, label_horizon=horizon,
                      embargo_pct=embargo_pct)
    for tr, te in cv.split(X):
        overlap = set(tr.tolist()) & set(te.tolist())
        assert not overlap, \
            f"overlap encontrado n={n} splits={n_splits} h={horizon}"


@given(
    n_splits=st.integers(min_value=2, max_value=6),
    horizon=st.integers(min_value=1, max_value=15),
    n=st.integers(min_value=300, max_value=2000),
)
@HYPOTHESIS_FAST
def test_property_purged_kfold_purges_horizon_neighborhood(n_splits, horizon, n):
    """Las muestras inmediatamente antes del test (dentro del horizon)
    NUNCA deben aparecer en train."""
    assume(n >= n_splits * (horizon + 5))
    X = np.zeros((n, 2))
    cv = PurgedKFold(n_splits=n_splits, label_horizon=horizon, embargo_pct=0)
    for tr, te in cv.split(X):
        test_min = int(te.min())
        forbidden = set(range(max(0, test_min - horizon), test_min))
        assert not (forbidden & set(tr.tolist())), \
            f"train incluye índice purgado | test_min={test_min} h={horizon}"


# ────────────────────────────────────────────────────────────────
# Property 4 — triple_barrier: bin_meta consistente con signo de ret
# ────────────────────────────────────────────────────────────────


@given(
    seed=st.integers(min_value=0, max_value=10_000),
    pt=st.floats(min_value=0.5, max_value=3.0, allow_nan=False),
    sl=st.floats(min_value=0.5, max_value=3.0, allow_nan=False),
    holding=st.integers(min_value=5, max_value=50),
)
@HYPOTHESIS_FAST
def test_property_triple_barrier_bin_meta_matches_return_sign(seed, pt, sl,
                                                               holding):
    rng = np.random.default_rng(seed)
    n = 500
    close = pd.Series(100 + np.cumsum(rng.standard_normal(n) * 0.5))
    vol = estimate_volatility(close, span=20)
    events = np.array([50, 100, 200, 300, 400])
    out = triple_barrier(
        close, events, vol,
        TripleBarrierConfig(pt_mult=pt, sl_mult=sl, max_holding=holding),
    )
    if out.empty:
        return
    for _, row in out.iterrows():
        if row["ret"] > 0:
            assert row["bin_meta"] == 1
        else:
            assert row["bin_meta"] == 0


# ────────────────────────────────────────────────────────────────
# Property 5 — AlertManager dedupe nunca emite duplicados rápidos
# ────────────────────────────────────────────────────────────────


class _CountingChannel:
    name = "counter"
    def __init__(self):
        self.calls = 0
    def send(self, *args, **kwargs):
        self.calls += 1
        return True


@given(
    n_events=st.integers(min_value=2, max_value=50),
    subject=st.text(min_size=1, max_size=30),
)
@HYPOTHESIS_FAST
def test_property_dedupe_collapses_rapid_repetition(n_events, subject):
    """Con dedupe activo y sin tiempo entre eventos, n_events INFO con el
    mismo subject deberían dar exactamente 1 envío."""
    ch = _CountingChannel()
    mgr = AlertManager([ch], dedupe_window_sec=3600)
    for _ in range(n_events):
        mgr.send(AlertLevel.INFO, subject, "body")
    assert ch.calls == 1, f"esperaba 1 envío con dedupe, got {ch.calls}"


@given(
    n_events=st.integers(min_value=2, max_value=20),
    subject=st.text(min_size=1, max_size=30),
)
@HYPOTHESIS_FAST
def test_property_critical_never_dedupes(n_events, subject):
    ch = _CountingChannel()
    mgr = AlertManager([ch], dedupe_window_sec=3600)
    for _ in range(n_events):
        mgr.send(AlertLevel.CRITICAL, subject, "body")
    assert ch.calls == n_events, \
        f"CRITICAL no debe dedupearse, esperaba {n_events}, got {ch.calls}"
