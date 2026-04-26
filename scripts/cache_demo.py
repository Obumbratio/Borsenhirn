"""
Smoke test end-to-end de borsenhirn.cache contra Redis real.

Cubre:
    1. Conectar a Redis (o detectar que no está corriendo).
    2. Round-trip set/get con TTLs.
    3. @cached decorator midiendo latencia (cache vs sin cache).
    4. RateLimiter con tier FREE: bloqueo después del límite.
    5. invalidate_namespace.
    6. Stats de hit/miss.
    7. Cleanup.

Uso:
    python scripts/cache_demo.py
"""

from __future__ import annotations

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from borsenhirn.cache import (  # noqa: E402
    RateLimitConfig,
    RateLimiter,
    Tier,
    cached,
    create_default_cache,
)

SEP = "=" * 64


def section(title: str) -> None:
    print(f"\n{SEP}\n  {title}\n{SEP}")


def main():
    print(f"\n{SEP}\n  CACHE + RATE-LIMITER DEMO\n{SEP}")

    cache = create_default_cache(namespace="demo")
    if not cache.is_available():
        print("FAIL: Redis no responde. Verificá REDIS_HOST/REDIS_PORT y que")
        print("      el servicio Redis esté corriendo.")
        sys.exit(1)
    print("[1] Redis conectado")

    # ── 2. Set / get básico ───────────────────────────
    section("[2] Round-trip set/get")
    cache.set("hello", "world", ttl=30)
    assert cache.get("hello") == "world"
    print("  OK string")

    cache.set("dict_test", {"symbol": "SPY", "price": 450.5}, ttl=30)
    assert cache.get("dict_test")["symbol"] == "SPY"
    print("  OK dict")

    cache.set("list_test", [1, 2, 3], ttl=30)
    assert cache.get("list_test") == [1, 2, 3]
    print("  OK list")

    # ── 3. @cached decorator ──────────────────────────
    section("[3] @cached decorator (latencia)")
    calls = {"n": 0}

    @cached(cache, ttl=30, namespace="demo_fn")
    def slow_lookup(symbol):
        calls["n"] += 1
        time.sleep(0.05)   # simula 50ms de I/O
        return {"symbol": symbol, "price": 100.0}

    t0 = time.time()
    slow_lookup("AAPL")
    t1 = time.time()
    slow_lookup("AAPL")     # cache hit
    t2 = time.time()
    miss_ms = (t1 - t0) * 1000
    hit_ms = (t2 - t1) * 1000
    print(f"  miss: {miss_ms:.1f}ms")
    print(f"  hit:  {hit_ms:.1f}ms ({(miss_ms / hit_ms):.0f}x más rápido)")
    print(f"  función ejecutada {calls['n']} veces (esperado 1)")
    assert calls["n"] == 1

    # invalidate
    slow_lookup.invalidate("AAPL")
    slow_lookup("AAPL")
    assert calls["n"] == 2
    print("  OK invalidate")

    # ── 4. Rate limiter ───────────────────────────────
    section("[4] RateLimiter — Tier FREE limit=5/60s")
    rl = RateLimiter(cache, limits={
        Tier.FREE: RateLimitConfig(max_requests=5, window_seconds=60),
        Tier.PRO: RateLimitConfig(max_requests=50, window_seconds=60),
        Tier.ENTERPRISE: RateLimitConfig(max_requests=500, window_seconds=60),
    })
    rl.reset("demo_user", "test", Tier.FREE)   # limpia residuos de runs previos

    for i in range(7):
        r = rl.check("demo_user", "test", Tier.FREE)
        status = "ALLOW" if r.allowed else "BLOCK"
        print(f"  req {i+1}: {status}  remaining={r.remaining} "
              f"retry_after={r.retry_after_seconds}s")

    # Subject diferente debe estar limpio
    r_other = rl.check("other_user", "test", Tier.FREE)
    assert r_other.allowed
    print(f"  OK other_user no afectado (allowed={r_other.allowed})")

    rl.reset("demo_user", "test", Tier.FREE)
    rl.reset("other_user", "test", Tier.FREE)

    # ── 5. invalidate_namespace ───────────────────────
    section("[5] invalidate_namespace")
    for sym in ["AAPL", "TSLA", "SPY", "QQQ"]:
        cache.set(f"bars:{sym}", {"price": 100}, ttl=60)
    deleted = cache.invalidate_namespace("bars")
    print(f"  borradas {deleted} keys del namespace 'bars'")

    # ── 6. Stats ──────────────────────────────────────
    section("[6] Stats finales")
    snap = cache.stats.snapshot()
    for k, v in snap.items():
        print(f"  {k:>15}: {v}")

    # ── 7. Cleanup ────────────────────────────────────
    section("[7] Cleanup")
    n = cache.invalidate_namespace("")   # borra todo el namespace 'demo'
    # Algunos clientes Redis no soportan match='demo:*' con prefix vacío,
    # entonces forzamos uno por uno:
    cache.delete("hello", "dict_test", "list_test")
    cache.invalidate_namespace("demo_fn")
    print("  OK cleanup")

    print(f"\n{SEP}\n  DEMO COMPLETO ✓\n{SEP}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback
        traceback.print_exc()
        sys.exit(2)
