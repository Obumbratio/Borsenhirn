"""Tests del decorator @cached."""

from __future__ import annotations

import pytest

from borsenhirn.cache.client import RedisCache
from borsenhirn.cache.decorators import cached


@pytest.fixture
def cache():
    fakeredis = pytest.importorskip("fakeredis")
    return RedisCache(client=fakeredis.FakeStrictRedis(decode_responses=True),
                       namespace="dec_test")


# ── Hit / miss básico ──────────────────────────────────────


def test_cached_caches_result(cache):
    calls = []

    @cached(cache, ttl=60)
    def expensive(x):
        calls.append(x)
        return x * 2

    assert expensive(5) == 10
    assert expensive(5) == 10
    assert expensive(5) == 10
    assert len(calls) == 1   # solo el primer call corrió la función


def test_cached_different_args_different_cache(cache):
    calls = []

    @cached(cache, ttl=60)
    def f(x):
        calls.append(x)
        return x + 1

    f(1); f(2); f(3); f(1); f(2)
    assert sorted(calls) == [1, 2, 3]


def test_cached_with_kwargs(cache):
    calls = []

    @cached(cache, ttl=60)
    def f(a, b=10):
        calls.append((a, b))
        return a + b

    assert f(1) == 11
    assert f(1) == 11   # cache hit
    assert f(1, b=20) == 21    # diferente kwargs, cache miss
    assert len(calls) == 2


# ── key_fn custom ──────────────────────────────────────────


def test_cached_custom_key_fn(cache):
    @cached(cache, key_fn=lambda x: f"prefix-{x}", ttl=60)
    def f(x):
        return x

    f("a")
    # Debe haber una entry con la key custom
    assert cache.exists("fn:f:prefix-a")


def test_cached_namespace_separates(cache):
    calls = []

    @cached(cache, namespace="ns_a", ttl=60)
    def f1(x):
        calls.append(("a", x))
        return x

    @cached(cache, namespace="ns_b", ttl=60)
    def f2(x):
        calls.append(("b", x))
        return x

    f1(1); f2(1)
    assert ("a", 1) in calls
    assert ("b", 1) in calls
    # 2 calls aunque el arg sea el mismo


# ── skip_cache (force refresh) ─────────────────────────────


def test_cached_skip_cache_kwarg_bypasses(cache):
    calls = []

    @cached(cache, ttl=60)
    def f(x):
        calls.append(x)
        return x * 10

    f(3)
    f(3, skip_cache=True)   # bypass
    f(3)                     # hit (cache se actualizó tras skip)
    assert len(calls) == 2


# ── invalidate ─────────────────────────────────────────────


def test_invalidate_specific_key(cache):
    calls = []

    @cached(cache, ttl=60)
    def f(x):
        calls.append(x)
        return x

    f(1); f(2); f(1); f(2)
    assert len(calls) == 2

    f.invalidate(1)
    f(1)   # ahora debe correr de nuevo
    assert len(calls) == 3
    f(2)   # 2 sigue cacheado
    assert len(calls) == 3


def test_invalidate_all_clears_namespace(cache):
    calls = []

    @cached(cache, namespace="bulk", ttl=60)
    def f(x):
        calls.append(x)
        return x

    for i in range(5):
        f(i)
    assert len(calls) == 5

    n_deleted = f.invalidate_all()
    assert n_deleted == 5

    for i in range(5):
        f(i)
    assert len(calls) == 10   # todos volvieron a correr


# ── No cachea None / vacío ─────────────────────────────────


def test_cached_does_not_cache_none(cache):
    calls = []

    @cached(cache, ttl=60)
    def f(x):
        calls.append(x)
        return None

    f(1); f(1); f(1)
    assert len(calls) == 3   # nunca cacheó


def test_cached_does_not_cache_empty_dict(cache):
    calls = []

    @cached(cache, ttl=60)
    def f(x):
        calls.append(x)
        return {}

    f(1); f(1)
    assert len(calls) == 2


def test_cached_does_cache_empty_string(cache):
    """Un string vacío SÍ se cachea (es una respuesta válida)."""
    calls = []

    @cached(cache, ttl=60)
    def f(x):
        calls.append(x)
        return ""

    f(1); f(1)
    # Nuestra heurística cachea no-None y no-vacío. "" no es vacío
    # como contenedor, pero como string sí podría serlo. La regla
    # actual cachea solo si no es None y no es contenedor vacío.
    # Comportamiento esperado: "" se cachea.
    assert len(calls) == 1


# ── Preserva metadata de la función ────────────────────────


def test_cached_preserves_dunder_name(cache):
    @cached(cache, ttl=60)
    def my_great_function(x):
        """docstring"""
        return x

    assert my_great_function.__name__ == "my_great_function"
    assert "docstring" in (my_great_function.__doc__ or "")
