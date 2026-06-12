"""
Feed de señal impersonal del cliente (Paso 2, Opción C) — sin DB ni red.

Mockea el SignalEngine y verifica: (1) analyze se llama IMPERSONAL (memory=None,
held vacío, sin plan), (2) el payload sale bien formado, (3) la caché sirve la
misma referencia hasta vencer.
"""

from __future__ import annotations

from borsenhirn.signals import client_feed


class _FakeSignals:
    regime = "BULL"
    market_ctx: dict = {}
    scan = {"buys": [{"symbol": "AAPL", "price": 190.0, "signal": {"reason": "tesis x"}}],
            "sells": []}


class _FakeEngine:
    def __init__(self):
        self.calls = []

    def analyze(self, **kw):
        self.calls.append(kw)
        return _FakeSignals()


def test_feed_is_impersonal_and_cached(monkeypatch):
    client_feed.reset_cache()
    fake = _FakeEngine()
    monkeypatch.setattr(client_feed, "_engine", fake)

    a = client_feed.get_client_signals(force=True)
    b = client_feed.get_client_signals()          # dentro del TTL → cacheado

    assert a is b                                  # misma referencia (caché)
    assert a["impersonal"] is True
    assert a["regime"] == "BULL"
    assert a["signals"] == [{"symbol": "AAPL", "price": 190.0, "reason": "tesis x"}]

    # analyze se llamó IMPERSONAL: sin memoria, sin cuenta, sin plan
    assert len(fake.calls) == 1                    # la 2da fue caché, no recomputo
    assert fake.calls[0]["memory"] is None
    assert fake.calls[0]["held"] == set()
    assert fake.calls[0]["plan_symbol"] is None

    client_feed.reset_cache()
