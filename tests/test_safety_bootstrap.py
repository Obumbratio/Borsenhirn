"""Tests de borsenhirn.safety.bootstrap (SafetyStack)."""

from __future__ import annotations

import time
from collections import deque

import pytest

from borsenhirn.safety.alerts import AlertLevel, AlertManager
from borsenhirn.safety.bootstrap import (
    SafetyStack,
    extract_equity_history_7d,
    make_recent_trades_buffer,
)
from borsenhirn.safety.killswitch import (
    InMemoryStateStore,
    KillReason,
    KillSwitch,
    KillSwitchConfig,
)
from borsenhirn.safety.sanity import SanityChecker, SanityConfig


# ── Fixtures locales ─────────────────────────────────────────


class _CapturingChannel:
    name = "capture"

    def __init__(self):
        self.calls = []

    def send(self, level, subject, body, meta=None):
        self.calls.append({"level": level, "subject": subject})
        return True


@pytest.fixture
def stack():
    ch = _CapturingChannel()
    am = AlertManager([ch], dedupe_window_sec=1)
    am._capture = ch
    store = InMemoryStateStore()
    ks = KillSwitch(
        store=store,
        alert_send=lambda subject, body, **m: am.critical(subject, body, **m),
        config=KillSwitchConfig(max_daily_loss_pct=0.05),
    )
    sc = SanityChecker(SanityConfig(max_position_pct=0.5))
    return SafetyStack(
        alert_mgr=am, killswitch=ks, sanity=sc,
        watchlist=["AAPL", "TSLA", "SPY"],
    )


# ── make_recent_trades_buffer ────────────────────────────────


def test_recent_trades_buffer_caps_at_maxlen():
    buf = make_recent_trades_buffer(maxlen=3)
    for i in range(10):
        buf.append({"i": i})
    assert len(buf) == 3
    assert buf[-1] == {"i": 9}


# ── alert_from_logger ────────────────────────────────────────


def test_alert_from_logger_routes_correct_level(stack):
    stack.alert_from_logger("INFO", "msg info")
    stack.alert_from_logger("WARN", "msg warn")
    stack.alert_from_logger("CRITICAL", "msg crit")
    levels = [c["level"] for c in stack.alert_mgr._capture.calls]
    assert AlertLevel.INFO in levels
    assert AlertLevel.WARN in levels
    assert AlertLevel.CRITICAL in levels


def test_alert_from_logger_unknown_level_falls_back_to_info(stack):
    stack.alert_from_logger("ZZZ_INVENTED", "msg")
    levels = [c["level"] for c in stack.alert_mgr._capture.calls]
    assert AlertLevel.INFO in levels


def test_alert_from_logger_does_not_crash_on_exception(stack):
    """Si el alert_mgr explota internamente, alert_from_logger no propaga."""
    def bad_send(*a, **kw):
        raise RuntimeError("boom")
    stack.alert_mgr.send = bad_send  # type: ignore
    # No debe lanzar
    stack.alert_from_logger("INFO", "x")


# ── build_snapshot + check_and_halt ──────────────────────────


def test_build_snapshot_includes_failures_counter(stack):
    stack.consecutive_order_failures = 3
    snap = stack.build_snapshot(
        equity_now=100_000, equity_day_start=100_000, daily_pnl=0,
    )
    assert snap.consecutive_order_failures == 3


def test_check_and_halt_returns_false_when_healthy(stack):
    snap = stack.build_snapshot(
        equity_now=100_000, equity_day_start=100_000, daily_pnl=0,
    )
    assert stack.check_and_halt(snap) is False
    assert not stack.is_halted()


def test_check_and_halt_returns_true_on_extreme_loss(stack):
    snap = stack.build_snapshot(
        equity_now=90_000, equity_day_start=100_000, daily_pnl=-7_000,
    )
    assert stack.check_and_halt(snap) is True
    assert stack.is_halted()


# ── safe_submit_buy ──────────────────────────────────────────


class _Executor:
    def __init__(self, accept=True):
        self.accept = accept
        self.calls = []

    def submit_order(self, sym, qty, side):
        self.calls.append((sym, qty, side))
        return f"oid-{sym}" if self.accept else None


def test_safe_submit_buy_passes_when_valid(stack):
    exe = _Executor()
    buf = make_recent_trades_buffer(50)
    oid = stack.safe_submit_buy(
        exe, "AAPL", 10, 150.0,
        positions_list=[], recent_trades=buf,
        portfolio_value=100_000, reason="test",
    )
    assert oid == "oid-AAPL"
    assert stack.consecutive_order_failures == 0
    assert len(buf) == 1
    assert buf[-1]["symbol"] == "AAPL"


def test_safe_submit_buy_blocks_outside_watchlist(stack):
    exe = _Executor()
    buf = make_recent_trades_buffer(50)
    oid = stack.safe_submit_buy(
        exe, "ZZZZ", 10, 100.0,
        positions_list=[], recent_trades=buf,
        portfolio_value=100_000,
    )
    assert oid is None
    assert exe.calls == []  # nunca se llamó al broker


def test_safe_submit_buy_increments_failures_when_broker_rejects(stack):
    exe = _Executor(accept=False)
    buf = make_recent_trades_buffer(50)
    stack.safe_submit_buy(
        exe, "AAPL", 10, 150.0,
        positions_list=[], recent_trades=buf,
        portfolio_value=100_000,
    )
    assert stack.consecutive_order_failures == 1


def test_safe_submit_buy_blocks_duplicate_position(stack):
    exe = _Executor()
    buf = make_recent_trades_buffer(50)
    oid = stack.safe_submit_buy(
        exe, "AAPL", 10, 150.0,
        positions_list=[{"symbol": "AAPL", "qty": "5"}],
        recent_trades=buf,
        portfolio_value=100_000,
    )
    assert oid is None
    assert exe.calls == []


# ── register_sell + register_sell_success ─────────────────────


def test_register_sell_increments_on_failure(stack):
    stack.register_sell("AAPL", oid=None)
    assert stack.consecutive_order_failures == 1


def test_register_sell_resets_on_success(stack):
    stack.consecutive_order_failures = 4
    stack.register_sell("AAPL", oid="oid-1")
    assert stack.consecutive_order_failures == 0


def test_register_sell_success_appends_to_buffer(stack):
    buf = make_recent_trades_buffer(50)
    stack.register_sell_success("AAPL", buf)
    assert len(buf) == 1
    assert buf[-1]["action"] == "sell"
    assert stack.consecutive_order_failures == 0


# ── extract_equity_history_7d ────────────────────────────────


def test_extract_equity_history_with_dict_rows():
    class FakeMem:
        def get_performance_history(self, days=7):
            return [{"equity": 100}, {"equity": 110}, {"portfolio_value": 105}]
    out = extract_equity_history_7d(FakeMem())
    assert out == [100.0, 110.0, 105.0]


def test_extract_equity_history_falls_back_to_empty():
    class FakeMem:
        pass
    out = extract_equity_history_7d(FakeMem())
    assert out == []


def test_extract_equity_history_handles_exceptions():
    class FakeMem:
        def get_performance_history(self, days=7):
            raise RuntimeError("db down")
    out = extract_equity_history_7d(FakeMem())
    assert out == []


def test_extract_equity_history_skips_non_numeric():
    class FakeMem:
        def get_performance_history(self, days=7):
            return [{"equity": "garbage"}, {"equity": 100}, {"equity": None}]
    out = extract_equity_history_7d(FakeMem())
    assert out == [100.0]
