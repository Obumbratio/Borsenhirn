"""
Decorator @cached para envolver funciones puras.

Uso típico:

    cache = create_default_cache()

    @cached(cache, key_fn=lambda symbol, tf: f"bars:{symbol}:{tf}",
            ttl=300, namespace="alpaca")
    def get_historical(symbol, tf):
        # ... call expensive Alpaca API
        return df

    df = get_historical("SPY", "1Hour")  # primer call → API + cache
    df = get_historical("SPY", "1Hour")  # segundo call → desde cache

Reglas:
    - Si key_fn es None, la key se genera de los args (str + repr).
    - Si la función devuelve None o {} vacío, NO se cachea (probably error).
    - skip_cache=True como kwarg opcional bypassa el cache (force refresh).
    - El decorator preserva __name__ y __doc__ via functools.wraps.
"""

from __future__ import annotations

import functools
import hashlib
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _default_key_fn(*args, **kwargs) -> str:
    """Genera key determinística desde args/kwargs."""
    parts = [repr(a) for a in args]
    parts += [f"{k}={v!r}" for k, v in sorted(kwargs.items())]
    s = "|".join(parts)
    if len(s) > 200:
        # Si la key es larga, hashearla
        return hashlib.sha1(s.encode("utf-8")).hexdigest()
    return s


def cached(
    cache,
    key_fn: Optional[Callable[..., str]] = None,
    ttl: int = 300,
    namespace: str = "fn",
    skip_kwarg: str = "skip_cache",
):
    """
    Decorator que cachea el resultado de la función envuelta.

    Args:
        cache:      instancia de RedisCache.
        key_fn:     callable(*args, **kwargs) -> str para generar la key.
                    Default: hash de repr(args).
        ttl:        TTL en segundos. Default 5min.
        namespace:  prefix dentro del namespace de la cache.
        skip_kwarg: nombre del kwarg para forzar miss (default 'skip_cache').
    """
    def decorator(fn: Callable) -> Callable:

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            skip = kwargs.pop(skip_kwarg, False)

            # Generar key
            if key_fn is not None:
                try:
                    raw_key = key_fn(*args, **kwargs)
                except Exception as exc:
                    logger.warning("key_fn de %s falló: %s", fn.__name__, exc)
                    raw_key = _default_key_fn(*args, **kwargs)
            else:
                raw_key = _default_key_fn(*args, **kwargs)
            full_key = f"{namespace}:{fn.__name__}:{raw_key}"

            if not skip:
                cached_val = cache.get(full_key)
                if cached_val is not None:
                    return cached_val

            # Ejecutar función real
            value = fn(*args, **kwargs)

            # Guardar solo si el resultado es no-trivial
            if value is not None and not (
                isinstance(value, (dict, list)) and len(value) == 0
            ):
                cache.set(full_key, value, ttl=ttl)

            return value

        # Helpers para invalidar manualmente
        def invalidate(*args, **kwargs):
            if key_fn is not None:
                raw_key = key_fn(*args, **kwargs)
            else:
                raw_key = _default_key_fn(*args, **kwargs)
            full_key = f"{namespace}:{fn.__name__}:{raw_key}"
            return cache.delete(full_key)

        def invalidate_all():
            return cache.invalidate_namespace(f"{namespace}:{fn.__name__}")

        wrapper.invalidate = invalidate           # type: ignore
        wrapper.invalidate_all = invalidate_all   # type: ignore
        return wrapper

    return decorator
