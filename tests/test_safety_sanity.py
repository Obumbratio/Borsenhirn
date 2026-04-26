"""Tests de borsenhirn.safety.sanity."""

import time

import pytest

from borsenhirn.safety.sanity import (
    OrderContext,
    SanityChecker,
    SanityConfig,
)


def _ctx(**overrides):
    """Constructor de contextos con defaults razonables."""
    defaults = dict(
        symbol="AAPL", action="buy", qty=10, price=150.0,
        portfolio_value=100_000, watchlist=["AAPL", "TSLA", "SPY"],
        current_positions={},
        recent_trades=[],
    )
    defaults.update(overrides)
    return OrderContext(**defaults)


# ── Acción ──────────────────────────────────────────────────


def test_rejects_invalid_action(sanity_checker):
    r = sanity_checker.validate(_ctx(action="teleport"))
    assert not r.ok and r.check == "action"


# ── Precio ──────────────────────────────────────────────────


def test_rejects_zero_price(sanity_checker):
    r = sanity_checker.validate(_ctx(price=0))
    assert not r.ok and r.check == "price"


def test_rejects_negative_price(sanity_checker):
    r = sanity_checker.validate(_ctx(price=-1))
    assert not r.ok and r.check == "price"


def test_rejects_absurd_price(sanity_checker):
    r = sanity_checker.validate(_ctx(price=1_000_000))
    assert not r.ok and r.check == "price"


def test_rejects_nan_price(sanity_checker):
    r = sanity_checker.validate(_ctx(price=float("nan")))
    assert not r.ok and r.check == "price"


# ── Quantity ────────────────────────────────────────────────


def test_rejects_qty_zero(sanity_checker):
    r = sanity_checker.validate(_ctx(qty=0))
    assert not r.ok and r.check == "quantity"


def test_rejects_qty_over_hard_cap(sanity_checker):
    r = sanity_checker.validate(_ctx(qty=100_000, price=0.5))
    assert not r.ok and r.check == "quantity"


def test_rejects_position_exceeds_max_pct(sanity_checker):
    # notional = 1000 * 150 = 150_000 > 6% * 100_000 = 6_000
    r = sanity_checker.validate(_ctx(qty=1000, price=150.0))
    assert not r.ok and r.check == "position_size"


# ── Watchlist ───────────────────────────────────────────────


def test_rejects_symbol_outside_watchlist(sanity_checker):
    r = sanity_checker.validate(_ctx(symbol="ZZZZ"))
    assert not r.ok and r.check == "watchlist"


def test_accepts_when_watchlist_check_disabled():
    from borsenhirn.safety.sanity import SanityConfig, SanityChecker
    sc = SanityChecker(SanityConfig(
        watchlist_required=False, max_position_pct=0.5,
    ))
    r = sc.validate(_ctx(symbol="UNKNOWN"))
    assert r.ok, f"esperaba ok, got {r.reason}"


# ── Duplicate buy ───────────────────────────────────────────


def test_rejects_buy_when_already_holding(sanity_checker):
    r = sanity_checker.validate(_ctx(current_positions={"AAPL": 10}))
    assert not r.ok and r.check == "duplicate_buy"


def test_allows_buy_when_not_holding(sanity_checker):
    r = sanity_checker.validate(_ctx(current_positions={"TSLA": 5}))
    assert r.ok


# ── Sell sanity ─────────────────────────────────────────────


def test_rejects_sell_without_position(sanity_checker):
    r = sanity_checker.validate(_ctx(action="sell", current_positions={}))
    assert not r.ok and r.check == "sell_position"


def test_rejects_sell_qty_larger_than_held(sanity_checker):
    # qty*price bajo para no activar el check de position_size antes;
    # el fallo debe venir de sell_position (qty > held).
    r = sanity_checker.validate(_ctx(
        action="sell", qty=50, price=1.0,
        current_positions={"AAPL": 10},
    ))
    assert not r.ok and r.check == "sell_position"


def test_accepts_sell_with_matching_position(sanity_checker):
    r = sanity_checker.validate(_ctx(
        action="sell", qty=10, current_positions={"AAPL": 10},
    ))
    assert r.ok


# ── Wash trade ──────────────────────────────────────────────


def test_rejects_buy_right_after_sell(sanity_checker):
    recent = [{
        "symbol": "AAPL", "action": "sell",
        "timestamp": time.time() - 100,   # 100s atrás, < 300s
    }]
    r = sanity_checker.validate(_ctx(recent_trades=recent))
    assert not r.ok and r.check == "wash_trade"


def test_allows_buy_after_wash_window(sanity_checker):
    recent = [{
        "symbol": "AAPL", "action": "sell",
        "timestamp": time.time() - 600,   # 600s atrás > 300s
    }]
    r = sanity_checker.validate(_ctx(recent_trades=recent))
    assert r.ok


def test_wash_check_ignores_other_symbols(sanity_checker):
    recent = [{
        "symbol": "TSLA", "action": "sell",
        "timestamp": time.time() - 50,
    }]
    r = sanity_checker.validate(_ctx(recent_trades=recent))
    assert r.ok


# ── Happy path ──────────────────────────────────────────────


def test_valid_buy_passes_all(sanity_checker):
    r = sanity_checker.validate(_ctx())
    assert r.ok
    assert r.check == "all"


# ── Property: qty<=0 siempre rechazado ──────────────────────


@pytest.mark.parametrize("q", [-10, -1, 0])
def test_property_non_positive_qty_always_rejected(sanity_checker, q):
    r = sanity_checker.validate(_ctx(qty=q))
    assert not r.ok
