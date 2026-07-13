"""
Orquestación del feed de noticias: TTL + cache compartida (noticias_cache).

Patrón MVP (sin workers de fondo):
  - si la cache tiene < TTL → sirve cache
  - si venció → intenta refrescar desde Alpaca; si Alpaca falla → sirve la
    última cache y marca `degraded=True`. NUNCA lanza por fallo de Alpaca.

Impersonal: la consulta NO usa tenant (tabla global, RLS off). El `tenant_id`
del endpoint solo gatea el acceso, no filtra contenido.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import config
import borsenhirn.db as bdb

logger = logging.getLogger(__name__)

_TTL_SEC = int(os.getenv("NOTICIAS_CACHE_TTL", "900"))  # 15 min
_FEED_LIMIT = 50  # tope sano del MVP (sin paginación)

_SAFE_COLS = "id, headline, summary, source, url, symbols, images, published_at"


def is_in_universe(symbol: str) -> bool:
    """¿El símbolo pertenece al universo impersonal (WATCHLIST)?"""
    uni = {s.upper() for s in getattr(config, "WATCHLIST", [])}
    return symbol.upper() in uni


def get_news_feed(symbol: Optional[str] = None) -> dict:
    """Feed impersonal. Refresca si la cache venció; degrada a cache si Alpaca falla."""
    degraded = False
    if _is_stale():
        try:
            rows = _fetch_from_alpaca()
            _upsert(rows)
        except Exception as exc:  # Alpaca caído / sin claves / breaker abierto
            degraded = True
            logger.warning("noticias: refresh falló, sirvo cache. %s", exc)

    articles = _read_cache(symbol=symbol, limit=_FEED_LIMIT)
    return {
        "impersonal": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ttl_sec": _TTL_SEC,
        "degraded": degraded,
        "count": len(articles),
        "noticias": articles,
    }


def _fetch_from_alpaca() -> list[dict]:
    from borsenhirn.news.client import fetch_latest
    return fetch_latest(limit=_FEED_LIMIT)


def _is_stale() -> bool:
    with bdb.get_conn(role="app") as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT max(fetched_at) FROM noticias_cache")
            mx = cur.fetchone()[0]
    if mx is None:
        return True
    return (datetime.now(timezone.utc) - mx).total_seconds() >= _TTL_SEC


def _upsert(rows: list[dict]) -> None:
    if not rows:
        return
    with bdb.get_conn(role="app") as conn:
        with conn.cursor() as cur:
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO noticias_cache
                        (id, headline, summary, source, url, symbols, images, published_at, fetched_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (id) DO UPDATE SET
                        headline     = EXCLUDED.headline,
                        summary      = EXCLUDED.summary,
                        source       = EXCLUDED.source,
                        url          = EXCLUDED.url,
                        symbols      = EXCLUDED.symbols,
                        images       = EXCLUDED.images,
                        published_at = EXCLUDED.published_at,
                        fetched_at   = NOW()
                    """,
                    (
                        r["id"], r["headline"], r["summary"], r["source"], r["url"],
                        r["symbols"], json.dumps(r["images"]), r["published_at"],
                    ),
                )
        conn.commit()


def _read_cache(symbol: Optional[str], limit: int) -> list[dict]:
    with bdb.get_conn(role="app") as conn:
        with conn.cursor() as cur:
            if symbol:
                cur.execute(
                    f"SELECT {_SAFE_COLS} FROM noticias_cache "
                    "WHERE %s = ANY(symbols) ORDER BY published_at DESC LIMIT %s",
                    (symbol.upper(), limit),
                )
            else:
                cur.execute(
                    f"SELECT {_SAFE_COLS} FROM noticias_cache "
                    "ORDER BY published_at DESC LIMIT %s",
                    (limit,),
                )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
