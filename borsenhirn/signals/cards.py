"""
Tarjeta de análisis IMPERSONAL y HONESTA (Paso 3b).

Convierte una señal del scanner en una "tarjeta" explicada: tesis + niveles +
qué invalida. Dos invariantes que NO se negocian:

1. IMPERSONAL: la tarjeta es sobre la EMPRESA/el setup, idéntica para todos. No
   mira la cuenta de nadie. Determinista → byte-a-byte igual para dos usuarios.
2. HONESTA (anti-AI-washing): cada parte sale de un dato REAL computado por el
   sistema (RSI, tendencia de medias, prob. del modelo ML, confianza, régimen,
   razón del scanner, stop de la estrategia). NADA de narrativa inventada. El
   array `factores` expone la PROCEDENCIA de cada dato; la `tesis`/`que_invalida`
   se renderizan SOLO a partir de esos factores (sin LLM que "rellene").

Las claves de la señal vienen garantizadas por `strategy.generate_signal`
(action/confidence/stop_loss/reason/rsi/ma_trend/ml_prob).
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import config

_DISCLAIMER = (
    "Análisis informativo e impersonal (igual para todos). No es recomendación "
    "de inversión; tú eliges, calculas tu tamaño y ejecutas."
)


def build_card(entry: Dict[str, Any], regime: Optional[str]) -> Dict[str, Any]:
    """
    Arma la tarjeta a partir de `entry = {"symbol", "signal", "price"}` (del scanner)
    y el `regime` del ciclo. Todo determinista; cada factor lleva su `fuente`.
    """
    sig: Dict[str, Any] = entry.get("signal") or {}
    symbol = entry.get("symbol")
    price = entry.get("price")

    # ── Factores: SOLO los que existen de verdad, con procedencia ──
    factores = []

    def add(factor: str, valor: Any, fuente: str) -> None:
        if valor is not None and valor != "":
            factores.append({"factor": factor, "valor": valor, "fuente": fuente})

    add("RSI", sig.get("rsi"), "indicators (técnico)")
    add("Tendencia de medias", sig.get("ma_trend"), "strategy (técnico)")
    add("Probabilidad del modelo ML", sig.get("ml_prob"), "ml_model (.pkl)")
    add("Confianza de la señal", sig.get("confidence"), "strategy")
    add("Régimen de mercado", regime, "regime_detector")
    add("Razón del scanner", sig.get("reason"), "strategy/scanner")

    # ── Niveles (deterministas; mismos para todos) ──
    stop = sig.get("stop_loss")
    stop_fuente = "strategy (stop calculado)"
    if not stop or float(stop) <= 0:
        stop = round(price * (1 - config.STOP_LOSS_FROM_ENTRY_PCT), 2) if price else None
        stop_fuente = f"config (STOP_LOSS_FROM_ENTRY_PCT={config.STOP_LOSS_FROM_ENTRY_PCT})"
    else:
        stop = round(float(stop), 2)
    target = round(price * (1 + config.TAKE_PROFIT_PCT), 2) if price else None
    levels = {
        "entry": price,
        "stop": stop,
        "target": target,
        "trailing_pct": config.TRAILING_STOP_PCT,
        "fuentes": {
            "entry": "precio de mercado",
            "stop": stop_fuente,
            "target": f"config (TAKE_PROFIT_PCT={config.TAKE_PROFIT_PCT})",
        },
    }

    # ── Tesis: renderizada DE los factores (sin nada inventado) ──
    bits = []
    if sig.get("rsi") is not None:
        bits.append(f"RSI {sig['rsi']}")
    if sig.get("ma_trend"):
        bits.append(f"tendencia de medias {sig['ma_trend']}")
    if sig.get("ml_prob") is not None:
        bits.append(f"prob. del modelo {sig['ml_prob']}")
    if sig.get("confidence") is not None:
        bits.append(f"confianza {sig['confidence']}")
    tesis = f"Setup en {symbol}"
    if regime:
        tesis += f" (régimen {regime})"
    if bits:
        tesis += ": " + ", ".join(bits) + "."
    else:
        tesis += "."
    if sig.get("reason"):
        tesis += f" Razón: {sig['reason']}"

    if stop is not None:
        que_invalida = (
            f"La tesis se invalida si {symbol} pierde el nivel de stop de referencia "
            f"(~${stop})" + (f" o si el régimen deja de ser {regime}." if regime else ".")
        )
    else:
        que_invalida = (
            f"La tesis se invalida si el régimen deja de ser {regime}."
            if regime else "La tesis se invalida si cambian las condiciones del setup."
        )

    return {
        "symbol": symbol,
        "price": price,
        "levels": levels,
        "tesis": tesis,
        "que_invalida": que_invalida,
        "factores": factores,
        "disclaimer": _DISCLAIMER,
    }


__all__ = ["build_card"]
