"""Tests de risk_manager.RiskManager."""

import pytest

import config
from risk_manager import RiskManager


@pytest.fixture
def risk():
    r = RiskManager()
    r.update(portfolio_value=100_000, daily_pnl=0.0, trades_today=0)
    return r


# ── check_daily_loss ──────────────────────────────────────


def test_daily_loss_not_hit_below_limit(risk):
    # MAX_DAILY_LOSS_PCT default suele ser 0.05 = 5000 en $100k
    limit_usd = 100_000 * config.MAX_DAILY_LOSS_PCT
    risk.update(100_000, -limit_usd * 0.5, 0)
    assert risk.check_daily_loss() is False


def test_daily_loss_triggered_over_limit(risk):
    limit_usd = 100_000 * config.MAX_DAILY_LOSS_PCT
    risk.update(100_000, -limit_usd * 1.1, 0)
    assert risk.check_daily_loss() is True


def test_daily_loss_only_negative_counts(risk):
    risk.update(100_000, +5_000, 0)   # ganancia grande
    assert risk.check_daily_loss() is False


# ── check_max_trades ──────────────────────────────────────


def test_max_trades_not_hit(risk):
    risk.update(100_000, 0, config.MAX_TRADES_PER_DAY - 1)
    assert risk.check_max_trades() is False


def test_max_trades_hit(risk):
    risk.update(100_000, 0, config.MAX_TRADES_PER_DAY)
    assert risk.check_max_trades() is True


def test_max_trades_exceeded(risk):
    risk.update(100_000, 0, config.MAX_TRADES_PER_DAY + 5)
    assert risk.check_max_trades() is True


# ── reset_daily ───────────────────────────────────────────


def test_reset_daily_clears_counters(risk):
    risk.update(100_000, -1_000, 10)
    risk.reset_daily()
    assert risk.daily_pnl == 0.0
    assert risk.trades_today == 0


# ── validate_order ────────────────────────────────────────


def test_hold_returns_false(risk):
    ok, msg = risk.validate_order({"action": "hold"}, 100.0)
    assert not ok


def test_buy_returns_true_with_capital(risk):
    ok, msg = risk.validate_order({"action": "buy"}, 50.0)
    assert ok
    assert "BUY aprobado" in msg


def test_buy_blocked_when_daily_loss_hit(risk):
    risk.update(100_000, -6_000, 0)   # -6% > 5%
    ok, _ = risk.validate_order({"action": "buy"}, 100.0)
    assert not ok


def test_buy_blocked_when_max_trades_hit(risk):
    risk.update(100_000, 0, config.MAX_TRADES_PER_DAY)
    ok, _ = risk.validate_order({"action": "buy"}, 100.0)
    assert not ok


def test_buy_blocked_when_price_zero(risk):
    ok, _ = risk.validate_order({"action": "buy"}, 0)
    assert not ok


def test_sell_without_position_rejected(risk):
    ok, _ = risk.validate_order({"action": "sell"}, 100.0, position_qty=0)
    assert not ok


def test_sell_with_position_accepted(risk):
    ok, msg = risk.validate_order({"action": "sell"}, 100.0, position_qty=10)
    assert ok
    assert "SELL aprobado" in msg


def test_unknown_action(risk):
    ok, _ = risk.validate_order({"action": "teleport"}, 100.0)
    assert not ok


# ── calc_order_qty ────────────────────────────────────────


def test_calc_order_qty_scales_with_portfolio(risk):
    risk.update(100_000, 0, 0)
    q100 = risk.calc_order_qty(100)
    risk.update(200_000, 0, 0)
    q200 = risk.calc_order_qty(100)
    assert q200 > q100


def test_calc_order_qty_zero_price_safe(risk):
    assert risk.calc_order_qty(0) == 0
    assert risk.calc_order_qty(-5) == 0


def test_calc_order_qty_min_one(risk):
    # Con precio muy alto debería dar al menos 1
    risk.update(100_000, 0, 0)
    q = risk.calc_order_qty(1_000_000)
    assert q >= 1
