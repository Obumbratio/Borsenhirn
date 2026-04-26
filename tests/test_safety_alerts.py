"""Tests de borsenhirn.safety.alerts."""

import time

import pytest

from borsenhirn.safety.alerts import (
    AlertLevel,
    AlertManager,
    DiscordChannel,
)


class _FakeChannel:
    name = "fake"

    def __init__(self, return_value=True):
        self.calls = []
        self.return_value = return_value

    def send(self, level, subject, body, meta=None):
        self.calls.append((level, subject, body, meta))
        return self.return_value


# ── Dedupe ────────────────────────────────────────────────────


def test_dedupe_suppresses_identical_within_window():
    ch = _FakeChannel()
    mgr = AlertManager([ch], dedupe_window_sec=60)
    mgr.info("algo", "body1")
    mgr.info("algo", "body2")  # mismo subject
    assert len(ch.calls) == 1, "esperaba dedupe de la segunda"


def test_dedupe_window_expires():
    ch = _FakeChannel()
    mgr = AlertManager([ch], dedupe_window_sec=0)  # ventana cero = sin dedupe
    mgr.info("algo", "body1")
    mgr.info("algo", "body2")
    assert len(ch.calls) == 2


def test_critical_always_passes_dedupe():
    ch = _FakeChannel()
    mgr = AlertManager([ch], dedupe_window_sec=3600)
    mgr.critical("urgente", "1")
    mgr.critical("urgente", "2")
    assert len(ch.calls) == 2, "CRITICAL no debe ser dedupeado"


def test_force_bypasses_dedupe():
    ch = _FakeChannel()
    mgr = AlertManager([ch], dedupe_window_sec=3600)
    mgr.send(AlertLevel.INFO, "x", "1")
    mgr.send(AlertLevel.INFO, "x", "2", force=True)
    assert len(ch.calls) == 2


# ── Level filtering ────────────────────────────────────────────


def test_min_level_filters_info_when_set_to_warn():
    ch = _FakeChannel()
    mgr = AlertManager([ch], dedupe_window_sec=0, min_level=AlertLevel.WARN)
    mgr.info("no pasa", "x")
    mgr.warn("sí pasa", "x")
    assert len(ch.calls) == 1
    assert ch.calls[0][0] == AlertLevel.WARN


# ── Multi-canal ────────────────────────────────────────────────


def test_multiple_channels_all_receive():
    a, b, c = _FakeChannel(), _FakeChannel(), _FakeChannel()
    mgr = AlertManager([a, b, c], dedupe_window_sec=0)
    mgr.info("topic", "body")
    assert len(a.calls) == 1
    assert len(b.calls) == 1
    assert len(c.calls) == 1


def test_one_channel_crash_does_not_affect_others():
    class Crashing:
        name = "crash"
        def send(self, *a, **kw):
            raise RuntimeError("kaboom")

    ok = _FakeChannel()
    mgr = AlertManager([Crashing(), ok], dedupe_window_sec=0)
    res = mgr.info("x", "y")
    assert res["crash"] is False
    assert res["fake"] is True
    assert len(ok.calls) == 1


# ── Helpers info/warn/critical ─────────────────────────────────


def test_helpers_route_to_correct_level():
    ch = _FakeChannel()
    mgr = AlertManager([ch], dedupe_window_sec=0)
    mgr.info("i", "body")
    mgr.warn("w", "body")
    mgr.critical("c", "body")
    levels = [c[0] for c in ch.calls]
    assert levels == [AlertLevel.INFO, AlertLevel.WARN, AlertLevel.CRITICAL]


# ── DiscordChannel: sin webhook URL no rompe ────────────────────


def test_discord_channel_empty_webhook_returns_false():
    dc = DiscordChannel(webhook_url="")
    ok = dc.send(AlertLevel.INFO, "test", "body")
    assert ok is False


def test_discord_channel_invalid_url_returns_false(monkeypatch):
    """Simula requests.post fallando con excepción."""
    import borsenhirn.safety.alerts as alerts_mod

    def fake_post(*a, **kw):
        raise RuntimeError("no network")
    monkeypatch.setattr(alerts_mod.requests, "post", fake_post)

    dc = DiscordChannel(webhook_url="https://invalid.example.com/w")
    ok = dc.send(AlertLevel.INFO, "test", "body")
    assert ok is False


def test_discord_channel_non_2xx_returns_false(monkeypatch):
    import borsenhirn.safety.alerts as alerts_mod

    class FakeResp:
        status_code = 500
        text = "Internal Server Error"
    def fake_post(*a, **kw):
        return FakeResp()
    monkeypatch.setattr(alerts_mod.requests, "post", fake_post)

    dc = DiscordChannel(webhook_url="https://discord.com/api/webhooks/x/y")
    ok = dc.send(AlertLevel.INFO, "t", "b")
    assert ok is False


def test_discord_channel_2xx_returns_true(monkeypatch):
    import borsenhirn.safety.alerts as alerts_mod

    class FakeResp:
        status_code = 204
        text = ""
    captured = {}
    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResp()
    monkeypatch.setattr(alerts_mod.requests, "post", fake_post)

    dc = DiscordChannel(webhook_url="https://discord.com/api/webhooks/x/y")
    ok = dc.send(AlertLevel.CRITICAL, "Kill switch", "pnl bajo límite",
                 meta={"symbol": "SPY", "pnl": -500.0})
    assert ok is True
    assert "embeds" in captured["json"]
    embed = captured["json"]["embeds"][0]
    assert "Kill switch" in embed["title"]
    assert embed["color"] != 0   # color asignado


# ── Fingerprint ────────────────────────────────────────────────


def test_fingerprint_differs_by_level():
    fp_info = AlertManager._fingerprint(AlertLevel.INFO, "x")
    fp_warn = AlertManager._fingerprint(AlertLevel.WARN, "x")
    assert fp_info != fp_warn


def test_fingerprint_stable_for_same_input():
    a = AlertManager._fingerprint(AlertLevel.INFO, "hello")
    b = AlertManager._fingerprint(AlertLevel.INFO, "hello")
    assert a == b
