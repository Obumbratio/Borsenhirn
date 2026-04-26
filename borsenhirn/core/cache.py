"""
cache.py — Conexión central de Börsenhirn a Redis.
Memoria de corto plazo: precios, señales del día, estado en tiempo real.
"""

import os
import json
import logging
from datetime import timedelta
import redis
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))

try:
    _client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
        decode_responses=True, socket_connect_timeout=3
    )
    _client.ping()
    logger.info("[CACHE] Conexión a Redis OK.")
except Exception as e:
    logger.warning(f"[CACHE] Redis no disponible: {e}")
    _client = None


def set_value(key: str, value, ttl_seconds: int = 3600) -> bool:
    if not _client:
        return False
    try:
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        _client.setex(key, timedelta(seconds=ttl_seconds), str(value))
        return True
    except Exception as e:
        logger.error(f"[CACHE] set_value: {e}")
        return False


def get_value(key: str, default=None):
    if not _client:
        return default
    try:
        val = _client.get(key)
        if val is None:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    except Exception as e:
        logger.error(f"[CACHE] get_value: {e}")
        return default


def delete_key(key: str) -> bool:
    if not _client:
        return False
    try:
        _client.delete(key)
        return True
    except Exception as e:
        logger.error(f"[CACHE] delete_key: {e}")
        return False


def cache_price(symbol: str, price: float, ttl: int = 60):
    set_value(f"price:{symbol}", price, ttl_seconds=ttl)


def get_cached_price(symbol: str):
    val = get_value(f"price:{symbol}")
    return float(val) if val is not None else None


def cache_signal(symbol: str, source: str, signal: dict, ttl: int = 3600):
    set_value(f"signal:{source}:{symbol}", signal, ttl_seconds=ttl)


def get_cached_signal(symbol: str, source: str):
    return get_value(f"signal:{source}:{symbol}")


def set_bot_status(status: dict, ttl: int = 300):
    set_value("bot:status", status, ttl_seconds=ttl)


def get_bot_status() -> dict:
    return get_value("bot:status", default={})


def is_available() -> bool:
    if not _client:
        return False
    try:
        _client.ping()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if is_available():
        set_value("test:ok", {"borsenhirn": "online"}, ttl_seconds=60)
        print(f"✅  Redis OK. Test: {get_value('test:ok')}")
    else:
        print("❌  Redis no disponible.")
