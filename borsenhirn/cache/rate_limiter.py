"""
Sliding-window rate limiter usando Redis sorted sets.

Algoritmo
---------
Para cada (subject, action) mantenemos un sorted set en Redis donde:
    score = epoch_ms del request
    member = id único del request (timestamp + nonce)

En cada hit:
    1. ZREMRANGEBYSCORE para limpiar requests fuera de la ventana.
    2. ZCARD para contar requests dentro de la ventana.
    3. Si count < límite: ZADD + EXPIRE → permitido.
       Si count >= límite: rechazo.

Ventajas vs token bucket:
    - Sin estado de "último timestamp" — todo en Redis atómico.
    - Tolera bursts naturales (hasta N en cualquier ventana de T).
    - Limpieza pasiva — los entries viejos se podan al próximo request.

Tier-aware:
    El RateLimiter recibe un dict {tier: RateLimitConfig}. Cada subject
    declara su tier (free/pro/enterprise) al chequear. Esto permite
    monetización directa: free=60req/min, pro=600req/min, etc.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class Tier(str, Enum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuración de un límite por tier."""
    max_requests: int          # ej. 60
    window_seconds: int        # ej. 60 → 60 req/min
    burst_multiplier: float = 1.0   # 1.0 = exacto; 1.5 = permite 50% extra rápido

    @property
    def effective_limit(self) -> int:
        return max(1, int(self.max_requests * self.burst_multiplier))


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int
    reset_at_epoch: int
    tier: str

    def to_headers(self) -> Dict[str, str]:
        """X-RateLimit-* headers estilo GitHub/Stripe."""
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_at_epoch),
            "X-RateLimit-Tier": self.tier,
            "Retry-After": str(self.retry_after_seconds) if not self.allowed else "0",
        }


class RateLimitExceeded(Exception):
    """Excepción que el caller puede atrapar para devolver 429."""

    def __init__(self, result: RateLimitResult, message: str = ""):
        self.result = result
        super().__init__(message or f"Rate limit exceeded for {result.tier}")


# ── Defaults razonables ─────────────────────────────────────


DEFAULT_LIMITS: Dict[Tier, RateLimitConfig] = {
    Tier.FREE: RateLimitConfig(max_requests=60, window_seconds=60),
    Tier.PRO: RateLimitConfig(max_requests=600, window_seconds=60),
    Tier.ENTERPRISE: RateLimitConfig(max_requests=6000, window_seconds=60),
}


class RateLimiter:
    """
    Rate limiter sliding-window.

    Args:
        cache: instancia de RedisCache (su .client se usa para los ZSET).
        limits: dict tier -> RateLimitConfig. Si no se pasa, usa DEFAULT_LIMITS.
        namespace: prefix para las keys, default 'rl'.
    """

    def __init__(
        self,
        cache,
        limits: Optional[Dict[Tier, RateLimitConfig]] = None,
        namespace: str = "rl",
    ):
        self.cache = cache
        self.limits = dict(limits) if limits else dict(DEFAULT_LIMITS)
        self.namespace = namespace

    # ── API principal ────────────────────────────────────

    def check(
        self,
        subject: str,
        action: str = "default",
        tier: Tier = Tier.FREE,
        weight: int = 1,
    ) -> RateLimitResult:
        """
        Decisión: ¿este request entra dentro del límite?
        Args:
            subject:   identificador único del cliente (user_id, ip, etc.).
            action:    bucket lógico (p.ej. "claude_api", "alpaca_orders").
                       Permite tener límites distintos por endpoint.
            tier:      determina qué config aplica.
            weight:    cuánto cuesta este request (default 1; usar >1 para
                       requests pesados como Claude completions con muchos tokens).
        """
        cfg = self.limits.get(tier)
        if cfg is None:
            raise ValueError(f"tier desconocido: {tier!r}")

        client = self.cache.client
        if client is None:
            # Cache caído → permitir (fail-open). Decisión deliberada:
            # rate limiter no debe ser SPOF. Si querés fail-closed,
            # cambia este return a RateLimitResult(allowed=False, ...).
            return RateLimitResult(
                allowed=True, limit=cfg.effective_limit,
                remaining=cfg.effective_limit,
                retry_after_seconds=0,
                reset_at_epoch=int(time.time()) + cfg.window_seconds,
                tier=tier.value,
            )

        key = f"{self.cache.namespace}:{self.namespace}:{tier.value}:{subject}:{action}"
        now_ms = int(time.time() * 1000)
        window_ms = cfg.window_seconds * 1000
        cutoff = now_ms - window_ms

        try:
            pipe = client.pipeline()
            pipe.zremrangebyscore(key, 0, cutoff)   # limpia viejos
            pipe.zcard(key)                          # cuenta actuales
            results = pipe.execute()
            current = int(results[1])

            limit = cfg.effective_limit
            if current + weight > limit:
                # Rechazo. Calcular retry_after viendo el más viejo en el set.
                try:
                    oldest = client.zrange(key, 0, 0, withscores=True)
                    if oldest:
                        oldest_ts = int(oldest[0][1])
                        retry_ms = max(1, oldest_ts + window_ms - now_ms)
                    else:
                        retry_ms = window_ms
                except Exception:
                    retry_ms = window_ms
                return RateLimitResult(
                    allowed=False,
                    limit=limit,
                    remaining=0,
                    retry_after_seconds=max(1, retry_ms // 1000),
                    reset_at_epoch=int((now_ms + retry_ms) / 1000),
                    tier=tier.value,
                )

            # Permitido — registrar
            pipe = client.pipeline()
            for i in range(weight):
                # member único — usamos uuid4 para evitar colisiones
                # cuando hay weight>1 o requests al mismo ms.
                pipe.zadd(key, {f"{now_ms}-{uuid.uuid4().hex[:8]}-{i}": now_ms})
            pipe.expire(key, cfg.window_seconds + 1)
            pipe.execute()

            new_count = current + weight
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=max(0, limit - new_count),
                retry_after_seconds=0,
                reset_at_epoch=int((now_ms + window_ms) / 1000),
                tier=tier.value,
            )
        except Exception as exc:
            logger.warning("RateLimiter.check error: %s — fail-open", exc)
            return RateLimitResult(
                allowed=True, limit=cfg.effective_limit,
                remaining=cfg.effective_limit,
                retry_after_seconds=0,
                reset_at_epoch=int(time.time()) + cfg.window_seconds,
                tier=tier.value,
            )

    def check_or_raise(
        self,
        subject: str,
        action: str = "default",
        tier: Tier = Tier.FREE,
        weight: int = 1,
    ) -> RateLimitResult:
        """Como check() pero lanza RateLimitExceeded si no allowed."""
        result = self.check(subject, action, tier, weight)
        if not result.allowed:
            raise RateLimitExceeded(result)
        return result

    # ── Admin / observabilidad ──────────────────────────

    def reset(self, subject: str, action: str = "default",
                tier: Tier = Tier.FREE) -> bool:
        """Borra el bucket completo (admin reset)."""
        client = self.cache.client
        if client is None:
            return False
        key = f"{self.cache.namespace}:{self.namespace}:{tier.value}:{subject}:{action}"
        try:
            client.delete(key)
            return True
        except Exception:
            return False

    def current_usage(
        self,
        subject: str,
        action: str = "default",
        tier: Tier = Tier.FREE,
    ) -> int:
        """Cuántos requests hay registrados en la ventana actual."""
        client = self.cache.client
        if client is None:
            return 0
        cfg = self.limits.get(tier)
        if cfg is None:
            return 0
        key = f"{self.cache.namespace}:{self.namespace}:{tier.value}:{subject}:{action}"
        now_ms = int(time.time() * 1000)
        cutoff = now_ms - cfg.window_seconds * 1000
        try:
            client.zremrangebyscore(key, 0, cutoff)
            return int(client.zcard(key))
        except Exception:
            return 0
