"""
Cliente del feed de noticias de Alpaca (Benzinga). Claves de PLATAFORMA, NO BYO.

Devuelve SOLO campos seguros (copyright): headline + summary + metadatos + link.
NUNCA el cuerpo del artículo — se pide `include_content=False` y, por las dudas,
`content` jamás se proyecta. Envuelto en el circuit breaker `alpaca_cb`: si la
llamada falla, registra el fallo y relanza para que el feed degrade a cache.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _img_size(size: Any) -> Optional[str]:
    """Normaliza el tamaño de imagen (enum NewsImageSize | str | None) a str."""
    if size is None:
        return None
    return getattr(size, "value", None) or str(size)


def _safe_article(a: Any) -> dict:
    """
    Proyecta un artículo (modelo News o dict) a los campos que SÍ persistimos.
    Deja afuera `content` (cuerpo, copyright) y `author`.
    """
    get = a.get if isinstance(a, dict) else (lambda k, _a=a: getattr(_a, k, None))
    raw_imgs = get("images") or []
    images = []
    for im in raw_imgs:
        ig = im.get if isinstance(im, dict) else (lambda k, _i=im: getattr(_i, k, None))
        images.append({"size": _img_size(ig("size")), "url": ig("url")})
    return {
        "id": int(get("id")),
        "headline": get("headline") or "",
        "summary": get("summary") or "",
        "source": get("source") or "",
        "url": get("url") or "",
        "symbols": list(get("symbols") or []),
        "images": images,
        "published_at": get("created_at"),  # datetime; el feed lo persiste/serializa
    }


def fetch_latest(symbols: Optional[list[str]] = None, limit: int = 50) -> list[dict]:
    """
    Trae las últimas noticias de Alpaca (orden desc por defecto). Devuelve dicts
    SEGUROS (sin content/author). Lanza si faltan claves o si Alpaca falla — el
    caller (feed) decide degradar a cache.
    """
    import config
    from circuit_breaker import alpaca_cb

    key, secret = config.ALPACA_DATA_KEY_ID, config.ALPACA_DATA_SECRET
    if not key or not secret:
        raise RuntimeError("ALPACA_DATA_KEY_ID/ALPACA_DATA_SECRET no configuradas")
    if not alpaca_cb.can_call():
        raise RuntimeError("circuit breaker Alpaca abierto — no se llama")

    try:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest

        kwargs: dict[str, Any] = {
            "limit": max(1, min(int(limit), 50)),
            "include_content": False,      # copyright: nunca traemos el cuerpo
            "exclude_contentless": False,
        }
        if symbols:
            kwargs["symbols"] = ",".join(symbols)
        resp = NewsClient(api_key=key, secret_key=secret).get_news(NewsRequest(**kwargs))
        alpaca_cb.record_success()
    except Exception:
        alpaca_cb.record_failure()
        raise

    # NewsSet.data["news"] -> list[News]; o dict crudo con "news".
    if hasattr(resp, "data"):
        articles = resp.data.get("news", [])
    elif isinstance(resp, dict):
        articles = resp.get("news", [])
    else:
        articles = []
    return [_safe_article(a) for a in articles]
