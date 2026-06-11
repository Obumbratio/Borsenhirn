"""
Aislamiento per-tenant del motor: alertas, trade log CSV y plan de usuario.

Testea los helpers de `BotEngine` (`_alert`, `_trades_log_path`, `_log_trade`)
sin construir el engine completo (vía `__new__`, sin DB/red), y las rutas de
plan por tenant en `my_plan`.
"""

from __future__ import annotations

import config
import my_plan
from borsenhirn.engine import BotEngine
from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID

OTHER = "00000000-0000-0000-0000-000000000099"
OTHER2 = "00000000-0000-0000-0000-000000000098"


# ── Alertas: cada engine rutea a SU propia alert_mgr ────────────────

def test_alert_routes_to_own_safety():
    eng = BotEngine.__new__(BotEngine)

    calls = []

    class _FakeSafety:
        def alert_from_logger(self, level, message):
            calls.append((level, message))

    eng.safety = _FakeSafety()
    eng._alert("hola", "WARN")
    eng._alert("default level")
    assert calls == [("WARN", "hola"), ("INFO", "default level")]


def test_alert_never_raises_on_safety_error():
    eng = BotEngine.__new__(BotEngine)

    class _BoomSafety:
        def alert_from_logger(self, level, message):
            raise RuntimeError("canal caído")

    eng.safety = _BoomSafety()
    # No debe propagar: una alerta nunca tumba el ciclo.
    eng._alert("x")


def test_two_engines_alert_to_distinct_managers():
    a = BotEngine.__new__(BotEngine)
    b = BotEngine.__new__(BotEngine)
    seen_a, seen_b = [], []

    class _S:
        def __init__(self, sink):
            self._sink = sink
        def alert_from_logger(self, level, message):
            self._sink.append(message)

    a.safety = _S(seen_a)
    b.safety = _S(seen_b)
    a._alert("para A")
    b._alert("para B")
    assert seen_a == ["para A"] and seen_b == ["para B"]


# ── Trade log CSV: ruta scoped por tenant ───────────────────────────

def test_trades_log_path_default_is_global(monkeypatch):
    monkeypatch.setattr(config, "TRADES_LOG", "reports/trades.csv")
    eng = BotEngine.__new__(BotEngine)
    eng.tenant_id = DEFAULT_TENANT_UUID
    assert eng._trades_log_path() == "reports/trades.csv"


def test_trades_log_path_other_tenant_is_suffixed(monkeypatch):
    monkeypatch.setattr(config, "TRADES_LOG", "reports/trades.csv")
    eng = BotEngine.__new__(BotEngine)
    eng.tenant_id = OTHER
    assert eng._trades_log_path() == f"reports/trades.{OTHER}.csv"


def test_log_trade_writes_to_tenant_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRADES_LOG", str(tmp_path / "trades.csv"))

    eng_default = BotEngine.__new__(BotEngine)
    eng_default.tenant_id = DEFAULT_TENANT_UUID
    eng_default._log_trade("buy", "AAPL", 100.0, 2, "x")

    eng_other = BotEngine.__new__(BotEngine)
    eng_other.tenant_id = OTHER
    eng_other._log_trade("sell", "MSFT", 200.0, 1, "y")

    base = tmp_path / "trades.csv"
    tenant_file = tmp_path / f"trades.{OTHER}.csv"
    assert base.exists() and tenant_file.exists()
    # No se mezclan: cada archivo tiene su propio símbolo
    assert "AAPL" in base.read_text() and "AAPL" not in tenant_file.read_text()
    assert "MSFT" in tenant_file.read_text() and "MSFT" not in base.read_text()


# ── Plan de usuario: archivo scoped por tenant ──────────────────────

def test_plan_path_isolation():
    assert my_plan._plan_path(DEFAULT_TENANT_UUID) == my_plan.PLAN_FILE
    assert my_plan._plan_path(None) == my_plan.PLAN_FILE
    p_other = my_plan._plan_path(OTHER)
    assert p_other != my_plan.PLAN_FILE and OTHER in p_other


def test_plan_save_load_per_tenant(tmp_path, monkeypatch):
    monkeypatch.setattr(my_plan, "PLAN_FILE", str(tmp_path / "plan.json"))

    my_plan.save_plan({"symbol": "QQQ", "activo": True}, OTHER)
    my_plan.save_plan({"symbol": "GLD", "activo": True}, OTHER2)

    # Cada tenant ve solo lo suyo; el DEFAULT no ve nada
    assert my_plan.load_plan(OTHER)["symbol"] == "QQQ"
    assert my_plan.load_plan(OTHER2)["symbol"] == "GLD"
    assert my_plan.load_plan(DEFAULT_TENANT_UUID) == {}
