"""Tests de circuit_breaker.CircuitBreaker (state machine)."""

import time

import pytest

from circuit_breaker import CircuitBreaker


@pytest.fixture
def cb():
    return CircuitBreaker("test", max_failures=3, cooldown=1)


def test_starts_closed(cb):
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.can_call()


def test_failures_below_threshold_stays_closed(cb):
    cb.record_failure()
    cb.record_failure()
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.can_call()


def test_failures_reach_threshold_opens(cb):
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
    assert cb.total_trips == 1
    assert not cb.can_call()


def test_open_circuit_blocks_calls(cb):
    for _ in range(3):
        cb.record_failure()
    assert not cb.can_call()


def test_cooldown_transitions_to_half_open(cb):
    for _ in range(3):
        cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN

    # Esperar cooldown
    time.sleep(1.1)
    # Primera can_call() tras cooldown debe pasar a HALF_OPEN
    assert cb.can_call()
    assert cb.state == CircuitBreaker.HALF_OPEN


def test_half_open_success_recovers(cb):
    for _ in range(3):
        cb.record_failure()
    time.sleep(1.1)
    cb.can_call()   # pasa a HALF_OPEN
    cb.record_success()
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failures == 0


def test_half_open_failure_reopens(cb):
    """Reabrir desde HALF_OPEN NO cuenta como nuevo trip (diseño actual)."""
    for _ in range(3):
        cb.record_failure()
    assert cb.total_trips == 1
    time.sleep(1.1)
    cb.can_call()   # HALF_OPEN
    cb.record_failure()
    assert cb.state == CircuitBreaker.OPEN
    # total_trips solo se incrementa cuando el circuito se abre por primera
    # vez desde CLOSED; los re-opens desde HALF_OPEN no se cuentan.
    assert cb.total_trips == 1


def test_record_success_closed_resets_failure_count(cb):
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    assert cb.failures == 0
    assert cb.state == CircuitBreaker.CLOSED


def test_get_status_contains_expected_keys(cb):
    s = cb.get_status()
    for key in ("name", "state", "failures", "total_trips", "cooldown"):
        assert key in s
    assert s["name"] == "test"


def test_multiple_independent_trips_counted(cb):
    """Trips independientes (recovery completo + nueva caída) sí cuentan."""
    # Trip 1: cae
    for _ in range(3):
        cb.record_failure()
    assert cb.total_trips == 1

    # Recovery completo: HALF_OPEN + success → CLOSED
    time.sleep(1.1)
    cb.can_call()
    cb.record_success()
    assert cb.state == CircuitBreaker.CLOSED

    # Trip 2: nueva secuencia de fallos
    for _ in range(3):
        cb.record_failure()
    assert cb.total_trips == 2


# ── Instancias globales presentes ───────────────────────────


def test_global_instances_exist():
    from circuit_breaker import (
        alpaca_cb, claude_cb, finnhub_cb, fred_cb,
        newsapi_cb, polygon_cb, yfinance_cb, alphavantage_cb,
    )
    for inst in [alpaca_cb, claude_cb, finnhub_cb, fred_cb,
                 newsapi_cb, polygon_cb, yfinance_cb, alphavantage_cb]:
        assert inst.state == CircuitBreaker.CLOSED


def test_get_all_status_returns_list():
    from circuit_breaker import get_all_status
    statuses = get_all_status()
    assert isinstance(statuses, list)
    assert all("name" in s and "state" in s for s in statuses)
