"""Tests del RateLimiter sliding-window."""

from __future__ import annotations

import time

import pytest

from borsenhirn.cache.client import RedisCache
from borsenhirn.cache.rate_limiter import (
    DEFAULT_LIMITS,
    RateLimitConfig,
    RateLimitExceeded,
    RateLimiter,
    Tier,
)


@pytest.fixture
def cache():
    fakeredis = pytest.importorskip("fakeredis")
    return RedisCache(client=fakeredis.FakeStrictRedis(decode_responses=True),
                       namespace="rl_test")


@pytest.fixture
def limiter(cache):
    custom = {
        Tier.FREE: RateLimitConfig(max_requests=5, window_seconds=60),
        Tier.PRO: RateLimitConfig(max_requests=50, window_seconds=60),
        Tier.ENTERPRISE: RateLimitConfig(max_requests=500, window_seconds=60),
    }
    return RateLimiter(cache, limits=custom)


# ── Allowed dentro del límite ───────────────────────────────


def test_allows_below_limit(limiter):
    for i in range(5):
        r = limiter.check("user1", "test", Tier.FREE)
        assert r.allowed, f"request {i} debería pasar"


def test_remaining_decreases(limiter):
    r1 = limiter.check("user1", "test", Tier.FREE)
    r2 = limiter.check("user1", "test", Tier.FREE)
    r3 = limiter.check("user1", "test", Tier.FREE)
    assert r1.remaining > r2.remaining > r3.remaining


def test_blocks_at_limit(limiter):
    for _ in range(5):
        limiter.check("u", "x", Tier.FREE)
    r = limiter.check("u", "x", Tier.FREE)
    assert not r.allowed
    assert r.retry_after_seconds > 0
    assert r.remaining == 0


# ── Tier separation ─────────────────────────────────────────


def test_tier_pro_higher_limit(limiter):
    # Free: 5 req. Pro: 50 req.
    for _ in range(5):
        limiter.check("u_pro", "x", Tier.PRO)
    r = limiter.check("u_pro", "x", Tier.PRO)
    assert r.allowed   # PRO permite 50, no se llegó al cap


def test_different_tiers_different_buckets(limiter):
    # User mismo subject pero distinto tier → distintos buckets
    for _ in range(5):
        limiter.check("u", "x", Tier.FREE)
    # FREE quedó al tope; PRO sigue limpio
    free_r = limiter.check("u", "x", Tier.FREE)
    pro_r = limiter.check("u", "x", Tier.PRO)
    assert not free_r.allowed
    assert pro_r.allowed


# ── Subject separation ──────────────────────────────────────


def test_different_subjects_independent_buckets(limiter):
    for _ in range(5):
        limiter.check("user_a", "x", Tier.FREE)
    # user_a al tope; user_b sigue limpio
    r_a = limiter.check("user_a", "x", Tier.FREE)
    r_b = limiter.check("user_b", "x", Tier.FREE)
    assert not r_a.allowed
    assert r_b.allowed


# ── Action separation ───────────────────────────────────────


def test_different_actions_independent(limiter):
    for _ in range(5):
        limiter.check("u", "claude", Tier.FREE)
    r_claude = limiter.check("u", "claude", Tier.FREE)
    r_alpaca = limiter.check("u", "alpaca", Tier.FREE)
    assert not r_claude.allowed
    assert r_alpaca.allowed


# ── Weight ─────────────────────────────────────────────────


def test_weight_consumes_more(limiter):
    # Hacer un weight=3 y luego 2 weight=1 deberían consumir 5 (límite free=5)
    limiter.check("u", "x", Tier.FREE, weight=3)
    limiter.check("u", "x", Tier.FREE, weight=1)
    limiter.check("u", "x", Tier.FREE, weight=1)
    r = limiter.check("u", "x", Tier.FREE, weight=1)
    assert not r.allowed


def test_weight_exceeds_limit_immediately(limiter):
    """weight=10 cuando el límite es 5 → rechazo en el primer call."""
    r = limiter.check("u", "x", Tier.FREE, weight=10)
    assert not r.allowed


# ── check_or_raise ─────────────────────────────────────────


def test_check_or_raise_passes_when_allowed(limiter):
    r = limiter.check_or_raise("u", "x", Tier.FREE)
    assert r.allowed


def test_check_or_raise_raises_when_blocked(limiter):
    for _ in range(5):
        limiter.check("u", "x", Tier.FREE)
    with pytest.raises(RateLimitExceeded) as exc_info:
        limiter.check_or_raise("u", "x", Tier.FREE)
    assert exc_info.value.result.allowed is False


# ── Headers ────────────────────────────────────────────────


def test_to_headers_when_allowed(limiter):
    r = limiter.check("u", "x", Tier.FREE)
    h = r.to_headers()
    assert h["X-RateLimit-Limit"] == "5"
    assert int(h["X-RateLimit-Remaining"]) >= 0
    assert int(h["X-RateLimit-Reset"]) > int(time.time())
    assert h["X-RateLimit-Tier"] == "free"
    assert h["Retry-After"] == "0"


def test_to_headers_when_blocked(limiter):
    for _ in range(5):
        limiter.check("u", "x", Tier.FREE)
    r = limiter.check("u", "x", Tier.FREE)
    h = r.to_headers()
    assert h["X-RateLimit-Remaining"] == "0"
    assert int(h["Retry-After"]) > 0


# ── Reset / current_usage ──────────────────────────────────


def test_reset_clears_bucket(limiter):
    for _ in range(5):
        limiter.check("u", "x", Tier.FREE)
    assert limiter.current_usage("u", "x", Tier.FREE) == 5
    limiter.reset("u", "x", Tier.FREE)
    assert limiter.current_usage("u", "x", Tier.FREE) == 0
    # ahora debería volver a permitir
    r = limiter.check("u", "x", Tier.FREE)
    assert r.allowed


def test_current_usage_reflects_state(limiter):
    assert limiter.current_usage("u", "x", Tier.FREE) == 0
    limiter.check("u", "x", Tier.FREE)
    limiter.check("u", "x", Tier.FREE)
    assert limiter.current_usage("u", "x", Tier.FREE) == 2


# ── Burst multiplier ───────────────────────────────────────


def test_burst_multiplier_increases_effective_limit():
    cfg = RateLimitConfig(max_requests=10, window_seconds=60,
                            burst_multiplier=1.5)
    assert cfg.effective_limit == 15


# ── Fail-open cuando client=None ───────────────────────────


def test_fail_open_when_cache_unavailable():
    cache = RedisCache(client=None, namespace="test")
    rl = RateLimiter(cache)
    r = rl.check("u", "x", Tier.FREE)
    assert r.allowed   # decisión deliberada: fail-open
    assert r.remaining > 0


# ── Validation ─────────────────────────────────────────────


def test_unknown_tier_raises(limiter):
    with pytest.raises(ValueError):
        limiter.check("u", "x", tier="enterprise_extra")  # type: ignore


# ── Defaults sanity ────────────────────────────────────────


def test_default_limits_have_sensible_values():
    assert DEFAULT_LIMITS[Tier.FREE].max_requests >= 30
    assert DEFAULT_LIMITS[Tier.PRO].max_requests > DEFAULT_LIMITS[Tier.FREE].max_requests
    assert DEFAULT_LIMITS[Tier.ENTERPRISE].max_requests > DEFAULT_LIMITS[Tier.PRO].max_requests
