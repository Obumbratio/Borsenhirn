"""
Alertas de salida (TP/SL) — aritmética PURA sobre la posición del usuario (Paso 3d).

NUNCA ejecuta ni dice "vendé": describe el escenario ("tu stop se tocó", "estás en
tu objetivo") y deja un `sugerido` que PRE-LLENA el botón. Ejecutar = el usuario
revisa y aprieta (POST /me/orders). Es per-cuenta (sobre las posiciones propias del
user), igual que la calculadora: cuentas sobre lo del usuario, no consejo.

Client-safe: importa solo `config`. NO importa el auto-trader.
"""

from __future__ import annotations

from typing import Any, Dict, List

import config


def position_alerts(*, symbol: str, qty: float, avg_entry: float,
                    current: float) -> List[Dict[str, Any]]:
    """
    Devuelve las alertas TP/SL de UNA posición (sobre el precio de entrada del
    usuario y el actual). Cada alerta trae un `sugerido` (pre-llenado del botón),
    nunca una orden ni un "vendé".
    """
    alerts: List[Dict[str, Any]] = []
    if not avg_entry or avg_entry <= 0 or not current or current <= 0:
        return alerts

    pct = (current - avg_entry) / avg_entry
    sugerido = {"side": "sell", "qty": int(qty), "symbol": symbol}

    if pct >= config.TAKE_PROFIT_PCT:
        alerts.append({
            "tipo": "objetivo_alcanzado",
            "mensaje": (f"{symbol} alcanzó tu nivel objetivo "
                        f"(+{pct:.1%} desde tu entrada ${avg_entry:.2f})."),
            "sugerido": sugerido,
        })
    elif pct <= -config.STOP_LOSS_FROM_ENTRY_PCT:
        alerts.append({
            "tipo": "stop_tocado",
            "mensaje": (f"{symbol} tocó tu stop de referencia "
                        f"({pct:.1%} desde tu entrada ${avg_entry:.2f})."),
            "sugerido": sugerido,
        })
    return alerts


__all__ = ["position_alerts"]
