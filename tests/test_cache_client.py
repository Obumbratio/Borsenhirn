"""Tests de borsenhirn.cache.client (RedisCache) usando fakeredis."""

from __future__ import annotations

import time

import pytest

from borsenhirn.cache.client import RedisCache, CacheStats


@pytest.fixture
def fake_client():
    """Cliente fakeredis. Si no está instalado, skip toda la suite."""
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.FakeStrictRedis(decode_responses=True)


@pytest.fixture
def cache(fake_client):
    return RedisCache(client=fake_client, namespace="test", default_ttl=60)


# ── set / get round-trip ────────────────────────────────────


def test_set_get_string(cache):
    assert cache.set("key1", "hello")
    assert cache.get("key1") == "hello"


def test_set_get_int(cache):
    cache.set("k", 42)
    assert cache.get("k") == 42


def test_set_get_float(cache):
    cache.set("k", 3.14159)
    assert cache.get("k") == 3.14159


def test_set_get_bool(cache):
    cache.set("k_true", True)
    cache.set("k_false", False)
    assert cache.get("k_true") is True
    assert cache.get("k_false") is False


def test_set_get_dict(cache):
    cache.set("k", {"symbol": "AAPL", "price": 150.5, "n": 100})
    val = cache.get("k")
    assert val == {"symbol": "AAPL", "price": 150.5, "n": 100}


def test_set_get_list(cache):
    cache.set("k", [1, 2, 3, "four"])
    assert cache.get("k") == [1, 2, 3, "four"]


def test_get_missing_returns_default(cache):
    assert cache.get("missing") is None
    assert cache.get("missing", default=42) == 42


# ── TTL ─────────────────────────────────────────────────────


def test_ttl_set_correctly(cache):
    cache.set("k", "v", ttl=30)
    ttl = cache.ttl("k")
    assert 25 <= ttl <= 30


def test_ttl_default_used_when_omitted(cache):
    cache.set("k", "v")
    ttl = cache.ttl("k")
    # default_ttl=60 (fixture)
    assert 55 <= ttl <= 60


def test_ttl_returns_minus_2_for_missing(cache):
    assert cache.ttl("nope") == -2


def test_expire_renews_ttl(cache):
    cache.set("k", "v", ttl=10)
    cache.expire("k", 100)
    assert cache.ttl("k") > 50


# ── delete ──────────────────────────────────────────────────


def test_delete_existing_returns_count(cache):
    cache.set("k1", "v")
    cache.set("k2", "v")
    assert cache.delete("k1", "k2") == 2


def test_delete_missing_returns_zero(cache):
    assert cache.delete("nope") == 0


def test_delete_actually_removes(cache):
    cache.set("k", "v")
    cache.delete("k")
    assert cache.get("k") is None


# ── exists ──────────────────────────────────────────────────


def test_exists_true(cache):
    cache.set("k", "v")
    assert cache.exists("k") is True


def test_exists_false_for_missing(cache):
    assert cache.exists("nope") is False


# ── get_or_set ──────────────────────────────────────────────


def test_get_or_set_misses_then_caches(cache):
    calls = []
    def loader():
        calls.append(1)
        return {"data": "expensive"}

    val1 = cache.get_or_set("k", loader, ttl=60)
    val2 = cache.get_or_set("k", loader, ttl=60)
    assert val1 == val2 == {"data": "expensive"}
    assert len(calls) == 1   # loader corrió solo 1 vez


def test_get_or_set_loader_returns_none_does_not_cache(cache):
    def loader_none():
        return None

    val = cache.get_or_set("k", loader_none, ttl=60)
    assert val is None
    # Si loader devuelve None, no cacheamos — próximo call también ejecuta
    assert cache.get("k") is None


# ── incr ────────────────────────────────────────────────────


def test_incr_starts_at_amount(cache):
    assert cache.incr("counter") == 1
    assert cache.incr("counter") == 2
    assert cache.incr("counter", amount=10) == 12


# ── invalidate_namespace ────────────────────────────────────


def test_invalidate_namespace_deletes_matching(cache):
    cache.set("alpaca:bars:SPY", "v1")
    cache.set("alpaca:bars:AAPL", "v2")
    cache.set("alpaca:price:SPY", "v3")
    cache.set("fred:UNRATE", "v4")

    n = cache.invalidate_namespace("alpaca:bars")
    assert n == 2
    assert cache.get("alpaca:bars:SPY") is None
    assert cache.get("alpaca:bars:AAPL") is None
    # otros namespaces no afectados
    assert cache.get("alpaca:price:SPY") == "v3"
    assert cache.get("fred:UNRATE") == "v4"


# ── Stats ───────────────────────────────────────────────────


def test_stats_track_hits_and_misses(cache):
    cache.set("k", "v")
    cache.get("k")        # hit
    cache.get("k")        # hit
    cache.get("missing")  # miss
    snap = cache.stats.snapshot()
    assert snap["hits"] == 2
    assert snap["misses"] == 1
    assert snap["hit_ratio"] == pytest.approx(2 / 3, rel=0.01)


def test_stats_track_sets_and_deletes(cache):
    cache.set("k1", "v")
    cache.set("k2", "v")
    cache.delete("k1")
    snap = cache.stats.snapshot()
    assert snap["sets"] == 2
    assert snap["deletes"] == 1


# ── Fail-soft cuando client=None ────────────────────────────


def test_no_client_get_returns_default():
    c = RedisCache(client=None)
    assert c.get("k") is None
    assert c.get("k", default=42) == 42


def test_no_client_set_returns_false():
    c = RedisCache(client=None)
    assert c.set("k", "v") is False


def test_no_client_is_available_false():
    c = RedisCache(client=None)
    assert c.is_available() is False


# ── Namespace isolation ─────────────────────────────────────


def test_different_namespaces_dont_collide(fake_client):
    a = RedisCache(client=fake_client, namespace="ns_a")
    b = RedisCache(client=fake_client, namespace="ns_b")
    a.set("k", "value-A")
    b.set("k", "value-B")
    assert a.get("k") == "value-A"
    assert b.get("k") == "value-B"


# ── Serialization edge cases ───────────────────────────────


def test_serialize_nested_dict(cache):
    val = {"nested": {"list": [1, 2, {"inner": "x"}]}}
    cache.set("k", val)
    assert cache.get("k") == val


def test_serialize_empty_string(cache):
    cache.set("k", "")
    # Nota: nuestro deserializer devuelve "" para "str:" sin contenido
    assert cache.get("k") == ""


def test_is_available_with_fake_client(cache):
    assert cache.is_available() is True
