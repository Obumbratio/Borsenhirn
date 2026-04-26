"""Tests de borsenhirn.safety.killswitch."""

import pytest

from borsenhirn.safety.killswitch import (
    InMemoryStateStore,
    KillReason,
    KillSnapshot,
    KillSwitch,
    KillSwitchConfig,
)


# ── InMemoryStateStore ────────────────────────────────────────


def test_store_get_missing_returns_none():
    s = InMemoryStateStore()
    assert s.get("missing") is None


def test_store_set_and_get():
    s = InMemoryStateStore()
    s.set("k1", True, "because", {"x": 1})
    row = s.get("k1")
    assert row is not None
    assert row["triggered"] is True
    assert row["reason"] == "because"
    assert row["data"]["x"] == 1


def test_store_list_active_only():
    s = InMemoryStateStore()
    s.set("active", True, "r1", {})
    s.set("inactive", False, "r2", {})
    active = s.list_active()
    keys = {r["key"] for r in active}
    assert keys == {"active"}


def test_store_clear_writes_note():
    s = InMemoryStateStore()
    s.set("k1", True, "r", {})
    s.clear("k1", note="resolved manually")
    row = s.get("k1")
    assert row["triggered"] is False
    assert row["data"]["clear_note"] == "resolved manually"


# ── KillSwitch: construcción ──────────────────────────────────


def test_killswitch_config_accepts_valid_ranges():
    cfg = KillSwitchConfig(
        max_daily_loss_pct=0.10,
        max_drawdown_7d_pct=0.20,
        max_consecutive_failures=3,
    )
    assert cfg.max_daily_loss_pct == 0.10
    assert cfg.max_drawdown_7d_pct == 0.20
    assert cfg.max_consecutive_failures == 3


# ── Check: max_daily_loss ─────────────────────────────────────


def test_daily_loss_triggers_when_pnl_exceeds_limit(in_memory_killswitch):
    ks = in_memory_killswitch
    snap = KillSnapshot(
        equity_now=95_000, equity_day_start=100_000,
        daily_pnl=-5_500,
    )
    triggered = ks.check_all(snap)
    assert len(triggered) == 1
    assert triggered[0].key == KillReason.MAX_DAILY_LOSS
    assert ks.is_halted()


def test_daily_loss_does_not_trigger_below_limit(in_memory_killswitch):
    ks = in_memory_killswitch
    snap = KillSnapshot(
        equity_now=97_000, equity_day_start=100_000,
        daily_pnl=-3_000,   # -3% < 5%
    )
    triggered = ks.check_all(snap)
    assert triggered == []
    assert not ks.is_halted()


def test_daily_loss_needs_equity_day_start(in_memory_killswitch):
    ks = in_memory_killswitch
    snap = KillSnapshot(
        equity_now=95_000, equity_day_start=None, daily_pnl=-5_000,
    )
    triggered = ks.check_all(snap)
    assert triggered == []


# ── Check: max_drawdown_7d ────────────────────────────────────


def test_drawdown_7d_triggers(in_memory_killswitch):
    ks = in_memory_killswitch
    # Peak 100k, ahora en 80k → -20% > -15%
    snap = KillSnapshot(
        equity_now=80_000, equity_day_start=85_000, daily_pnl=-5_000,
        equity_history_7d=[100_000, 95_000, 90_000, 85_000, 80_000],
    )
    triggered = ks.check_all(snap)
    keys = [t.key for t in triggered]
    assert KillReason.MAX_DRAWDOWN_7D in keys


def test_drawdown_7d_ignored_if_history_too_short(in_memory_killswitch):
    ks = in_memory_killswitch
    snap = KillSnapshot(
        equity_now=80_000, equity_day_start=100_000, daily_pnl=-2_000,
        equity_history_7d=[100_000],   # solo 1 → ignora DD
    )
    triggered = ks.check_all(snap)
    keys = [t.key for t in triggered]
    assert KillReason.MAX_DRAWDOWN_7D not in keys


# ── Check: consecutive_failures ───────────────────────────────


def test_consecutive_failures_triggers_at_limit(in_memory_killswitch):
    ks = in_memory_killswitch
    snap = KillSnapshot(
        equity_now=100_000, equity_day_start=100_000, daily_pnl=0,
        consecutive_order_failures=5,
    )
    triggered = ks.check_all(snap)
    keys = [t.key for t in triggered]
    assert KillReason.CONSECUTIVE_FAILURES in keys


def test_consecutive_failures_below_limit_does_not_trigger(in_memory_killswitch):
    ks = in_memory_killswitch
    snap = KillSnapshot(
        equity_now=100_000, equity_day_start=100_000, daily_pnl=0,
        consecutive_order_failures=4,
    )
    triggered = ks.check_all(snap)
    assert triggered == []


# ── Manual halt + clear ───────────────────────────────────────


def test_manual_halt_then_clear(in_memory_killswitch):
    ks = in_memory_killswitch
    ks.manual_halt("testing")
    assert ks.is_halted()
    active = [r["key"] for r in ks.active_reasons()]
    assert "manual_halt" in active

    ks.clear(KillReason.MANUAL, note="test done")
    assert not ks.is_halted()


def test_clear_all_clears_multiple(in_memory_killswitch):
    ks = in_memory_killswitch
    ks.manual_halt("a")
    snap = KillSnapshot(
        equity_now=90_000, equity_day_start=100_000, daily_pnl=-5_500,
    )
    ks.check_all(snap)
    assert len(ks.active_reasons()) >= 2
    ks.clear_all(note="reset")
    assert not ks.is_halted()


# ── Idempotencia ──────────────────────────────────────────────


def test_trigger_idempotent_no_duplicate_alerts(in_memory_killswitch,
                                                  alert_mgr_capture):
    ks = in_memory_killswitch
    snap = KillSnapshot(
        equity_now=90_000, equity_day_start=100_000, daily_pnl=-6_000,
    )
    ks.check_all(snap)
    alerts_first = len(alert_mgr_capture._capturing.calls)
    # Ejecutar de nuevo con el mismo estado
    ks.check_all(snap)
    alerts_second = len(alert_mgr_capture._capturing.calls)
    # No deberían haberse emitido nuevas alertas (ya estaba triggered)
    assert alerts_second == alerts_first
