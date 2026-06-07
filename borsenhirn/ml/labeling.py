"""
Triple-barrier labeling method para trading.

Referencia: López de Prado, M. (2018). Advances in Financial Machine Learning,
cap. 3 — "Labeling".

Idea
----
En vez de etiquetar cada barra con `close[t+h]/close[t] >= threshold` (fixed
horizon, muy ruidoso), definimos tres barreras por cada trade candidato:

    - Take-profit (horizontal superior): +pt_mult * vol
    - Stop-loss   (horizontal inferior): -sl_mult * vol
    - Vertical (tiempo máximo):          t + max_holding barras

El label es la primera barrera que toca el precio. Conceptualmente es cómo
el trader real piensa: "tomo el trade, salgo cuando gano X% o pierdo Y% o
paso N barras, lo que ocurra primero".

Para meta-labeling (cap. 3.6), el label binario es simplemente:
    1 = el trade cerró en ganancia neta (ret > 0)
    0 = el trade cerró en pérdida o flat

Esto genera un dataset MUCHO más balanceado y orientado a la pregunta real
que le importa al bot: "¿vale la pena tomar este trade?".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TripleBarrierConfig:
    """Configuración de las tres barreras."""
    pt_mult: float = 2.0       # take-profit = pt_mult * vol
    sl_mult: float = 1.0       # stop-loss   = sl_mult * vol
    max_holding: int = 20      # vertical barrier (en barras)
    min_vol: float = 1e-4      # piso de volatilidad para evitar barriers planas


def estimate_volatility(
    close: pd.Series,
    span: int = 20,
    method: str = "ewm_return",
) -> pd.Series:
    """
    Estima volatilidad por barra.

    method='ewm_return': std exponencial de retornos log (recomendado).
    method='rolling':    std rolling de retornos log.

    Retorna serie con la volatilidad en el mismo índice que close.
    """
    logret = np.log(close / close.shift(1))
    if method == "ewm_return":
        vol = logret.ewm(span=span, min_periods=span).std()
    elif method == "rolling":
        vol = logret.rolling(window=span, min_periods=span).std()
    else:
        raise ValueError(f"method '{method}' no soportado")
    # Backfill manual vía numpy (evita deprecations de pandas con fillna/bfill).
    vals = vol.to_numpy(copy=True)
    mask = np.isnan(vals)
    if mask.any() and (~mask).any():
        first_valid = int(np.argmax(~mask))
        vals[:first_valid] = vals[first_valid]
    vals = np.where(np.isnan(vals), 0.0, vals)
    return pd.Series(vals, index=vol.index, name=vol.name)


def triple_barrier(
    close: pd.Series,
    event_indices: np.ndarray,
    volatility: pd.Series,
    cfg: Optional[TripleBarrierConfig] = None,
    side: pd.Series | None = None,
) -> pd.DataFrame:
    """
    Aplica triple-barrier a cada evento (barra donde hay señal primaria).

    Parameters
    ----------
    close : pd.Series
        Serie de precios de cierre, indexada por timestamp.
    event_indices : np.ndarray[int]
        Posiciones enteras en `close` donde se dispara cada evento/señal.
    volatility : pd.Series
        Volatilidad estimada por barra (misma longitud que close).
    cfg : TripleBarrierConfig
        Parámetros de las barreras.
    side : pd.Series, optional
        Lado del trade: +1 = long, -1 = short. Si es None, asume todo long.
        Debe tener el mismo índice que close.

    Returns
    -------
    pd.DataFrame con columnas:
        - t_in:      iloc inicial del trade (el evento)
        - t_out:     iloc donde se cierra (primera barrera tocada)
        - close_in:  precio de entrada
        - close_out: precio de salida
        - ret:       retorno del trade, ya con signo según side
        - barrier:   {'pt', 'sl', 'vertical'}
        - bin_meta:  {1 si ret > 0, 0 si ret <= 0} — label para meta-labeling
        - bin_dir:   {+1 pt, -1 sl, 0 vertical} — label direccional (no binario)
    """
    cfg = cfg or TripleBarrierConfig()
    n = len(close)
    close_arr = close.values
    vol_arr = volatility.reindex(close.index).fillna(0.0).values
    vol_arr = np.where(vol_arr < cfg.min_vol, cfg.min_vol, vol_arr)

    if side is None:
        side_arr = np.ones(n, dtype=int)
    else:
        side_arr = side.reindex(close.index).fillna(1).astype(int).values

    rows = []
    for t_in in event_indices:
        if t_in < 0 or t_in >= n - 1:
            continue
        s = int(side_arr[t_in])
        if s == 0:
            continue
        entry = close_arr[t_in]
        vol_t = vol_arr[t_in]
        # Niveles de las barreras (expresados como retorno log-symmetric aprox)
        pt_level = entry * (1 + s * cfg.pt_mult * vol_t)
        sl_level = entry * (1 + s * (-cfg.sl_mult) * vol_t)
        # Ventana desde t_in+1 hasta t_in + max_holding (inclusive)
        t_vert = min(t_in + cfg.max_holding, n - 1)
        window = close_arr[t_in + 1: t_vert + 1]

        # Búsqueda de la PRIMERA barrera tocada
        # Para long (s=+1): pt = close >= pt_level; sl = close <= sl_level
        # Para short (s=-1): invertimos
        if s == 1:
            pt_hit = np.argmax(window >= pt_level) if (window >= pt_level).any() else -1
            sl_hit = np.argmax(window <= sl_level) if (window <= sl_level).any() else -1
        else:  # s == -1 (short)
            pt_hit = np.argmax(window <= pt_level) if (window <= pt_level).any() else -1
            sl_hit = np.argmax(window >= sl_level) if (window >= sl_level).any() else -1

        if pt_hit == -1 and sl_hit == -1:
            t_out = t_vert
            barrier = "vertical"
            bin_dir = 0
        elif pt_hit == -1:
            t_out = t_in + 1 + sl_hit
            barrier = "sl"
            bin_dir = -1
        elif sl_hit == -1:
            t_out = t_in + 1 + pt_hit
            barrier = "pt"
            bin_dir = 1
        else:
            if pt_hit < sl_hit:
                t_out = t_in + 1 + pt_hit
                barrier = "pt"
                bin_dir = 1
            elif sl_hit < pt_hit:
                t_out = t_in + 1 + sl_hit
                barrier = "sl"
                bin_dir = -1
            else:
                # Empate raro: preferimos stop-loss (conservador)
                t_out = t_in + 1 + sl_hit
                barrier = "sl"
                bin_dir = -1

        exit_px = close_arr[t_out]
        ret = s * (exit_px / entry - 1.0)
        rows.append({
            "t_in": int(t_in),
            "t_out": int(t_out),
            "close_in": float(entry),
            "close_out": float(exit_px),
            "ret": float(ret),
            "barrier": barrier,
            "bin_meta": 1 if ret > 0 else 0,
            "bin_dir": int(bin_dir),
            "side": int(s),
            "holding_bars": int(t_out - t_in),
        })

    out = pd.DataFrame(rows)
    if out.empty:
        logger.warning("triple_barrier: 0 eventos válidos.")
    else:
        logger.info(
            "triple_barrier: %d eventos | pt=%.1f%% sl=%.1f%% vert=%.1f%% | win_rate=%.1f%%",
            len(out),
            100 * (out["barrier"] == "pt").mean(),
            100 * (out["barrier"] == "sl").mean(),
            100 * (out["barrier"] == "vertical").mean(),
            100 * out["bin_meta"].mean(),
        )
    return out
