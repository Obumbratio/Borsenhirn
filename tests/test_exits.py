"""
Alertas TP/SL (Paso 3d) — aritmética pura. NUNCA ejecuta ni ordena vender.
"""

from __future__ import annotations

import config
from borsenhirn.signals.exits import position_alerts


def test_objetivo_alcanzado_es_alerta_con_sugerido_no_orden():
    avg = 100.0
    cur = avg * (1 + config.TAKE_PROFIT_PCT + 0.01)
    alerts = position_alerts(symbol="AAPL", qty=10, avg_entry=avg, current=cur)
    assert len(alerts) == 1
    a = alerts[0]
    assert a["tipo"] == "objetivo_alcanzado"
    # el sugerido PRE-LLENA el botón, no es una orden ejecutada
    assert a["sugerido"] == {"side": "sell", "qty": 10, "symbol": "AAPL"}
    # describe el escenario, no ordena "vendé"
    assert "objetivo" in a["mensaje"].lower()


def test_stop_tocado():
    avg = 100.0
    cur = avg * (1 - config.STOP_LOSS_FROM_ENTRY_PCT - 0.01)
    alerts = position_alerts(symbol="MSFT", qty=5, avg_entry=avg, current=cur)
    assert len(alerts) == 1 and alerts[0]["tipo"] == "stop_tocado"
    assert alerts[0]["sugerido"]["side"] == "sell"


def test_sin_alerta_dentro_del_rango():
    assert position_alerts(symbol="AAPL", qty=5, avg_entry=100.0, current=100.5) == []


def test_inputs_invalidos_no_crashean():
    assert position_alerts(symbol="X", qty=1, avg_entry=0, current=10) == []
    assert position_alerts(symbol="X", qty=1, avg_entry=100, current=0) == []
