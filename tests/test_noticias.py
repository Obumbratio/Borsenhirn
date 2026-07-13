"""
Tests del feed de noticias (M-Noticias).

Cubren los invariantes que NO se negocian:
  - COPYRIGHT: el objeto serializado NO trae cuerpo (`content`) ni `author`,
    solo headline + summary + metadatos + link.
  - IMPERSONAL: dos tenants distintos reciben EXACTAMENTE el mismo feed.
  - DEGRADACIÓN: si Alpaca falla, sirve la última cache con 200 (no 500).
  - ?symbol validado contra el universo impersonal (WATCHLIST).

No tocan DB real ni Alpaca: mockean las funciones de I/O del feed.
"""

import pytest
from fastapi.testclient import TestClient

from borsenhirn.api.main import app
from borsenhirn.auth.deps import get_active_tenant
from borsenhirn.news import client as news_client
from borsenhirn.news import feed as news_feed

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

SAMPLE = [
    {"id": 1, "headline": "h1", "summary": "s1", "source": "Benzinga",
     "url": "https://x/1", "symbols": ["AAPL"], "images": [],
     "published_at": "2026-06-24T10:00:00Z"},
    {"id": 2, "headline": "h2", "summary": "s2", "source": "Benzinga",
     "url": "https://x/2", "symbols": ["SPY"], "images": [],
     "published_at": "2026-06-24T09:00:00Z"},
]


@pytest.fixture
def make_client():
    def _mk(tenant):
        app.dependency_overrides[get_active_tenant] = lambda: tenant
        return TestClient(app)
    yield _mk
    app.dependency_overrides.clear()


def test_copyright_safe_article_drops_body():
    """_safe_article jamás proyecta el cuerpo (`content`) ni el `author`."""
    raw = {
        "id": 5, "headline": "H", "summary": "S", "source": "Benzinga",
        "url": "https://x/5", "symbols": ["AAPL"],
        "images": [{"size": "large", "url": "https://img/5"}],
        "created_at": "2026-06-24T10:00:00Z",
        "content": "<p>CUERPO COMPLETO DEL ARTÍCULO — NO DEBE PERSISTIRSE</p>",
        "author": "Jane Doe",
    }
    safe = news_client._safe_article(raw)
    assert "content" not in safe
    assert "author" not in safe
    assert safe["headline"] == "H"
    assert safe["images"] == [{"size": "large", "url": "https://img/5"}]
    assert safe["published_at"] == "2026-06-24T10:00:00Z"


def test_feed_is_impersonal(monkeypatch, make_client):
    """Dos tenants distintos → feed idéntico; y sin campos de copyright."""
    monkeypatch.setattr(news_feed, "_is_stale", lambda: False)
    monkeypatch.setattr(news_feed, "_read_cache", lambda symbol, limit: list(SAMPLE))

    a = make_client(TENANT_A).get("/noticias").json()
    b = make_client(TENANT_B).get("/noticias").json()

    assert a["noticias"] == b["noticias"]
    assert a["impersonal"] is True
    for art in a["noticias"]:
        assert "content" not in art
        assert "author" not in art


def test_alpaca_failure_serves_cache(monkeypatch, make_client):
    """Si Alpaca falla en el refresh → sirve cache, 200, degraded=True."""
    monkeypatch.setattr(news_feed, "_is_stale", lambda: True)

    def boom():
        raise RuntimeError("alpaca down")

    monkeypatch.setattr(news_feed, "_fetch_from_alpaca", boom)
    monkeypatch.setattr(news_feed, "_read_cache", lambda symbol, limit: list(SAMPLE))

    r = make_client(TENANT_A).get("/noticias")
    assert r.status_code == 200
    body = r.json()
    assert body["degraded"] is True
    assert len(body["noticias"]) == 2


def test_symbol_outside_universe_returns_400(monkeypatch, make_client):
    monkeypatch.setattr(news_feed, "_is_stale", lambda: False)
    monkeypatch.setattr(news_feed, "_read_cache", lambda symbol, limit: [])
    r = make_client(TENANT_A).get("/noticias", params={"symbol": "NOTREAL"})
    assert r.status_code == 400


def test_symbol_inside_universe_ok_and_uppercased(monkeypatch, make_client):
    seen = {}

    def fake_read(symbol, limit):
        seen["symbol"] = symbol
        return []

    monkeypatch.setattr(news_feed, "_is_stale", lambda: False)
    monkeypatch.setattr(news_feed, "_read_cache", fake_read)
    r = make_client(TENANT_A).get("/noticias", params={"symbol": "aapl"})
    assert r.status_code == 200
    assert seen["symbol"] == "AAPL"
