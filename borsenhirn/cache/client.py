"""
RedisCache — wrapper sobre redis-py con inyección de cliente.

Diseño:
    - El cliente Redis se INYECTA (no se construye dentro). Eso permite
      tests con fakeredis sin tocar I/O real.
    - Métricas de hit/miss/error en CacheStats — útil para observability.
    - Serialization JSON automática para dict/list, raw bytes/str para
      tipos primitivos.
    - Namespace prefix por instancia para evitar colisiones cross-feature.
    - Si Redis cae, get devuelve None (no lanza). set devuelve False.
      Filosofía: el cache nunca debe romper el flujo principal.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

logger = logging.getLogger(__name__)


class CacheUnavailable(Exception):
    """Solo se lanza si el código pide explícitamente strict mode."""


@dataclass
class CacheStats:
    """Contador thread-safe de operaciones del cache."""
    hits: int = 0
    misses: int = 0
    sets: int = 0
    deletes: int = 0
    errors: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def hit(self) -> None:
        with self._lock:
            self.hits += 1

    def miss(self) -> None:
        with self._lock:
            self.misses += 1

    def set_(self) -> None:
        with self._lock:
            self.sets += 1

    def delete(self) -> None:
        with self._lock:
            self.deletes += 1

    def error(self) -> None:
        with self._lock:
            self.errors += 1

    def hit_ratio(self) -> float:
        with self._lock:
            total = self.hits + self.misses
            return self.hits / total if total else 0.0

    def snapshot(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            return {
                "hits": self.hits, "misses": self.misses,
                "sets": self.sets, "deletes": self.deletes,
                "errors": self.errors,
                "hit_ratio": (self.hits / total) if total else 0.0,
                "total_lookups": total,
            }


class RedisCache:
    """
    Cliente cache de alto nivel. NO crea conexiones — recibe un cliente
    Redis (o fake) por inyección.

    Args:
        client: redis.Redis (o fakeredis.FakeStrictRedis) o cualquier
                objeto con la API de redis-py.
        namespace: prefix para todas las keys ("borsenhirn" por default).
        default_ttl: si set() no recibe ttl, usa este valor (None = sin TTL).
    """

    def __init__(
        self,
        client: Any,
        namespace: str = "bh",
        default_ttl: Optional[int] = 3600,
    ):
        self.client = client
        self.namespace = namespace
        self.default_ttl = default_ttl
        self.stats = CacheStats()

    # ── Key helpers ─────────────────────────────────────

    def _ns_key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    # ── ping / health ───────────────────────────────────

    def is_available(self) -> bool:
        if self.client is None:
            return False
        try:
            self.client.ping()
            return True
        except Exception as exc:
            logger.debug("Redis ping failed: %s", exc)
            return False

    # ── get / set / delete ──────────────────────────────

    def get(self, key: str, default: Any = None) -> Any:
        """Devuelve el valor o default si missing/error. NUNCA lanza."""
        if self.client is None:
            self.stats.miss()
            return default
        try:
            raw = self.client.get(self._ns_key(key))
        except Exception as exc:
            logger.warning("cache.get error: %s", exc)
            self.stats.error()
            return default
        if raw is None:
            self.stats.miss()
            return default
        self.stats.hit()
        return self._deserialize(raw)

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        if self.client is None:
            return False
        if ttl is None:
            ttl = self.default_ttl
        try:
            payload = self._serialize(value)
            if ttl is not None and ttl > 0:
                self.client.setex(self._ns_key(key), ttl, payload)
            else:
                self.client.set(self._ns_key(key), payload)
            self.stats.set_()
            return True
        except Exception as exc:
            logger.warning("cache.set error: %s", exc)
            self.stats.error()
            return False

    def delete(self, *keys: str) -> int:
        if self.client is None or not keys:
            return 0
        try:
            ns_keys = [self._ns_key(k) for k in keys]
            n = self.client.delete(*ns_keys)
            for _ in range(n or 0):
                self.stats.delete()
            return int(n or 0)
        except Exception as exc:
            logger.warning("cache.delete error: %s", exc)
            self.stats.error()
            return 0

    def exists(self, key: str) -> bool:
        if self.client is None:
            return False
        try:
            return bool(self.client.exists(self._ns_key(key)))
        except Exception as exc:
            logger.warning("cache.exists error: %s", exc)
            self.stats.error()
            return False

    def expire(self, key: str, ttl: int) -> bool:
        """Setea o renueva el TTL de una key existente."""
        if self.client is None:
            return False
        try:
            return bool(self.client.expire(self._ns_key(key), ttl))
        except Exception as exc:
            self.stats.error()
            return False

    def ttl(self, key: str) -> int:
        """Segundos restantes (>0), -1 si no tiene TTL, -2 si no existe."""
        if self.client is None:
            return -2
        try:
            return int(self.client.ttl(self._ns_key(key)))
        except Exception:
            return -2

    # ── Cache-aside pattern ─────────────────────────────

    def get_or_set(
        self,
        key: str,
        loader: Callable[[], Any],
        ttl: Optional[int] = None,
    ) -> Any:
        """
        Si key existe: devuelve cached.
        Si no: ejecuta loader(), cachea, devuelve.

        Si Redis está caído, ejecuta loader() y devuelve sin cachear
        (degradación graceful).
        """
        cached_val = self.get(key)
        if cached_val is not None:
            return cached_val
        value = loader()
        if value is not None:
            self.set(key, value, ttl=ttl)
        return value

    # ── Counters (atómicos) ─────────────────────────────

    def incr(self, key: str, amount: int = 1) -> Optional[int]:
        if self.client is None:
            return None
        try:
            return int(self.client.incrby(self._ns_key(key), amount))
        except Exception as exc:
            self.stats.error()
            return None

    # ── Bulk invalidation ───────────────────────────────

    def invalidate_namespace(self, sub_namespace: str) -> int:
        """
        Borra todas las keys que empiezan con `<namespace>:<sub_namespace>:`.
        Usa SCAN (no KEYS) para no bloquear Redis. Devuelve la cuenta de
        keys borradas.
        """
        if self.client is None:
            return 0
        pattern = f"{self.namespace}:{sub_namespace}:*"
        deleted = 0
        try:
            for key in self.client.scan_iter(match=pattern, count=200):
                self.client.delete(key)
                deleted += 1
                self.stats.delete()
        except Exception as exc:
            logger.warning("invalidate_namespace error: %s", exc)
            self.stats.error()
        return deleted

    # ── Serialization ───────────────────────────────────

    @staticmethod
    def _serialize(value: Any) -> str:
        if isinstance(value, (dict, list, tuple)):
            return "json:" + json.dumps(value, default=str)
        if isinstance(value, bool):
            return "bool:" + ("1" if value else "0")
        if isinstance(value, int):
            return "int:" + str(value)
        if isinstance(value, float):
            return "float:" + repr(value)
        if isinstance(value, str):
            return "str:" + value
        if isinstance(value, bytes):
            # Solo soportamos bytes ASCII por simplicidad de la deserialization
            return "bytes:" + value.decode("utf-8", errors="replace")
        # Fallback JSON
        return "json:" + json.dumps(value, default=str)

    @staticmethod
    def _deserialize(raw: Union[str, bytes]) -> Any:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        if not raw:
            return raw
        if raw.startswith("json:"):
            try:
                return json.loads(raw[5:])
            except (ValueError, json.JSONDecodeError):
                return raw[5:]
        if raw.startswith("int:"):
            try:
                return int(raw[4:])
            except ValueError:
                return raw[4:]
        if raw.startswith("float:"):
            try:
                return float(raw[6:])
            except ValueError:
                return raw[6:]
        if raw.startswith("bool:"):
            return raw[5:] == "1"
        if raw.startswith("str:"):
            return raw[4:]
        if raw.startswith("bytes:"):
            return raw[6:]
        # Sin prefix conocido — devolver raw
        return raw


# ── Factory de conveniencia ─────────────────────────────


def create_default_cache(
    host: Optional[str] = None,
    port: Optional[int] = None,
    db: Optional[int] = None,
    namespace: str = "bh",
    default_ttl: int = 3600,
) -> RedisCache:
    """
    Crea un RedisCache con cliente conectado (real o fake) leyendo
    REDIS_HOST / REDIS_PORT / REDIS_DB de env. Si Redis no está
    disponible, devuelve un RedisCache con client=None que hace no-op.

    Para tests: NO usar esta factory, instanciar `RedisCache(client=fake)`
    directamente.
    """
    try:
        import redis
    except ImportError:
        logger.warning("redis-py no instalado, cache deshabilitado.")
        return RedisCache(client=None, namespace=namespace,
                            default_ttl=default_ttl)

    h = host or os.getenv("REDIS_HOST", "localhost")
    p = port or int(os.getenv("REDIS_PORT", "6379"))
    d = db if db is not None else int(os.getenv("REDIS_DB", "0"))

    try:
        client = redis.Redis(
            host=h, port=p, db=d,
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
        client.ping()
        logger.info("[CACHE] conectado a Redis %s:%s db=%s", h, p, d)
        return RedisCache(client=client, namespace=namespace,
                            default_ttl=default_ttl)
    except Exception as exc:
        logger.warning("[CACHE] Redis no disponible (%s) — modo no-op", exc)
        return RedisCache(client=None, namespace=namespace,
                            default_ttl=default_ttl)
