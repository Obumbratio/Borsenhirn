"""
Tarjeta de análisis (Paso 3b) — honestidad + determinismo + impersonalidad.

Verifica que la tarjeta SOLO refleja datos reales de la señal (con procedencia),
que la tesis se compone de esos factores (no hay narrativa inventada), y que es
determinista (misma señal → misma tarjeta byte-a-byte).
"""

from __future__ import annotations

from borsenhirn.signals.cards import build_card

_ENTRY = {
    "symbol": "AAPL",
    "price": 190.0,
    "signal": {
        "action": "buy",
        "reason": "RSI bajo + cruce alcista de medias",
        "rsi": 28.0,
        "ma_trend": "up",
        "ml_prob": 0.72,
        "confidence": 0.65,
        "stop_loss": 182.0,
    },
}


def test_card_factores_traen_procedencia_de_datos_reales():
    card = build_card(_ENTRY, "BULL")
    by_factor = {f["factor"]: f for f in card["factores"]}
    # cada factor mapea a un valor REAL de la señal + una fuente
    assert by_factor["RSI"]["valor"] == 28.0
    assert by_factor["Probabilidad del modelo ML"]["valor"] == 0.72
    assert by_factor["Régimen de mercado"]["valor"] == "BULL"
    assert all(f.get("fuente") for f in card["factores"])   # todos citan fuente


def test_tesis_se_compone_de_los_factores_no_inventa():
    card = build_card(_ENTRY, "BULL")
    tesis = card["tesis"]
    # cada número de la tesis viene de la señal real (no hay valores fantasma)
    assert "28.0" in tesis and "0.72" in tesis and "BULL" in tesis
    assert "RSI bajo + cruce alcista de medias" in tesis    # la razón real del scanner
    # niveles: stop = el stop real de la estrategia; target del config
    assert card["levels"]["stop"] == 182.0
    assert card["que_invalida"].startswith("La tesis se invalida")


def test_card_no_inventa_factores_ausentes():
    # señal mínima: sin rsi/ml_prob → esos factores NO deben aparecer
    entry = {"symbol": "QQQ", "price": 400.0,
             "signal": {"action": "buy", "reason": "breakout", "confidence": 0.5}}
    card = build_card(entry, "BULL")
    factores = {f["factor"] for f in card["factores"]}
    assert "RSI" not in factores
    assert "Probabilidad del modelo ML" not in factores
    assert "Razón del scanner" in factores                  # esa sí está


def test_card_es_determinista():
    a = build_card(_ENTRY, "BULL")
    b = build_card(_ENTRY, "BULL")
    assert a == b                                            # byte-a-byte → impersonal estable
