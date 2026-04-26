"""
Helpers de cache para APIs externas concretas.

Estos helpers son ejemplos de cómo aplicar @cached a las llamadas más
costosas del proyecto. Importalos y envolvé tus funciones existentes.

TTLs sugeridos (calibrados para trading):
    - Bars históricas (Alpaca/yfinance):    300s (5 min)
    - Latest price (intraday):              10-30s
    - Macro series (FRED):                  3600s (1h) — cambian raro
    - News feed (NewsAPI/Finnhub):          120s (2 min)
    - SEC EDGAR filings:                    1800s (30 min) — diarias
    - LLM responses (Claude):               900s (15 min) — mismo prompt
    - Whale 13F filings:                    14400s (4h) — quarterly
"""

from __future__ import annotations

from borsenhirn.cache.decorators import cached

# Constantes públicas para que las uses tal cual.
TTL_BARS_INTRADAY = 300       # 5 min
TTL_LATEST_PRICE = 15         # 15s
TTL_MACRO = 3600              # 1h
TTL_NEWS = 120                # 2 min
TTL_SEC_FILINGS = 1800        # 30 min
TTL_LLM = 900                 # 15 min
TTL_WHALE_13F = 14400         # 4h


def cache_bars(cache, ttl: int = TTL_BARS_INTRADAY):
    """
    Envuelve get_historical(symbol, start, end, timeframe).
    Key incluye los 4 args para granularidad correcta.

    Uso:
        from data_fetcher import DataFetcher
        from borsenhirn.cache import create_default_cache
        from borsenhirn.cache.api_cache import cache_bars

        cache = create_default_cache()
        fetcher = DataFetcher()
        get_bars = cache_bars(cache)(fetcher.get_historical)
        df = get_bars("SPY", start, end, "1Hour")
    """
    return cached(
        cache,
        key_fn=lambda symbol, start, end, tf, *a, **kw:
            f"{symbol}:{tf}:{start}:{end}",
        ttl=ttl,
        namespace="bars",
    )


def cache_latest_price(cache, ttl: int = TTL_LATEST_PRICE):
    return cached(
        cache,
        key_fn=lambda symbol, *a, **kw: symbol,
        ttl=ttl,
        namespace="price",
    )


def cache_macro(cache, ttl: int = TTL_MACRO):
    """Para FRED.get_series('UNRATE'), etc."""
    return cached(
        cache,
        key_fn=lambda series_id, *a, **kw: series_id,
        ttl=ttl,
        namespace="macro",
    )


def cache_news(cache, ttl: int = TTL_NEWS):
    return cached(
        cache,
        key_fn=lambda symbol, *a, **kw: symbol,
        ttl=ttl,
        namespace="news",
    )


def cache_sec_filings(cache, ttl: int = TTL_SEC_FILINGS):
    return cached(
        cache,
        key_fn=lambda symbol, form_type="form4", *a, **kw:
            f"{symbol}:{form_type}",
        ttl=ttl,
        namespace="sec",
    )


def cache_llm_response(cache, ttl: int = TTL_LLM):
    """
    Cachea respuestas de Claude por prompt + system_prompt.
    Útil para queries "interpreta este 13F" que no varían en el día.

    El key_fn hashea el prompt para keys de tamaño manejable.
    """
    import hashlib

    def _key(prompt, system_prompt="", model="default", *a, **kw):
        h = hashlib.sha1(
            f"{model}|{system_prompt}|{prompt}".encode("utf-8")
        ).hexdigest()
        return h[:24]

    return cached(cache, key_fn=_key, ttl=ttl, namespace="llm")


def cache_whale_13f(cache, ttl: int = TTL_WHALE_13F):
    return cached(
        cache,
        key_fn=lambda cik, quarter, *a, **kw: f"{cik}:{quarter}",
        ttl=ttl,
        namespace="whale13f",
    )
