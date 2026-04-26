"""
borsenhirn.cache — Redis cache + rate limiting con cliente inyectable.

Componentes:
    client:       RedisCache (wrapper sobre redis-py, testeable con fakeredis).
    decorators:   @cached para envolver funciones puras.
    rate_limiter: RateLimiter sliding-window con tiers (free/pro/enterprise).
    api_cache:    helpers para cachear llamadas a APIs externas.

Convivencia con borsenhirn/core/cache.py:
    Ese módulo sigue funcionando como API legacy (set_value/get_value).
    Este nuevo módulo es la API recomendada para código nuevo — testeable,
    typed, con métricas de hit/miss.
"""

from borsenhirn.cache.client import (
    RedisCache,
    CacheStats,
    CacheUnavailable,
    create_default_cache,
)
from borsenhirn.cache.decorators import cached
from borsenhirn.cache.rate_limiter import (
    RateLimiter,
    RateLimitExceeded,
    RateLimitConfig,
    RateLimitResult,
    Tier,
)

__all__ = [
    "RedisCache",
    "CacheStats",
    "CacheUnavailable",
    "create_default_cache",
    "cached",
    "RateLimiter",
    "RateLimitExceeded",
    "RateLimitConfig",
    "RateLimitResult",
    "Tier",
]
