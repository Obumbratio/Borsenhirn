"""
Meta-labeling: entrenar un segundo modelo para filtrar las señales de un
modelo primario. López de Prado cap. 3.6.

Flujo
-----
1. **Modelo primario**: una regla determinística simple (no ML) que decide
   *cuándo* tomar un trade. En este proyecto usamos una versión simplificada
   de `strategy.py`: RSI oversold + volumen OK (con filtros de trend opcionales).
   El primario tiene alto recall pero baja precision.

2. **Triple-barrier**: para cada evento del primario aplicamos triple-barrier
   y obtenemos `bin_meta ∈ {0, 1}` = trade ganador o perdedor.

3. **Modelo meta**: clasificador binario que aprende a predecir `bin_meta`
   usando features del contexto en el momento del evento. En producción:
   si primario dice BUY y meta predice probabilidad > umbral, se toma el trade.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List

import numpy as np
import pandas as pd

from borsenhirn.ml.labeling import (
    TripleBarrierConfig,
    estimate_volatility,
    triple_barrier,
)

logger = logging.getLogger(__name__)


@dataclass
class PrimaryRuleConfig:
    """
    Regla primaria simplificada. Filosofía: alto recall, baja precision.
    El meta-modelo filtra los falsos positivos.

    Defaults permisivos para que salgan eventos. Si >30% de las barras
    disparan, el primario es inútil — baja `rsi_oversold` o activa
    `require_uptrend_long`.
    """
    rsi_oversold: float = 45.0
    rsi_col: str = "rsi"
    sma_long_col: str = "sma_100"
    sma_short_col: str = "sma_20"
    volume_col: str = "volume"
    volume_lookback: int = 20
    volume_min_ratio: float = 0.6
    require_uptrend_long: bool = False
    require_above_short: bool = False
    cooldown_bars: int = 5


@dataclass
class MetaLabelingConfig:
    primary: PrimaryRuleConfig = field(default_factory=PrimaryRuleConfig)
    barrier: TripleBarrierConfig = field(default_factory=TripleBarrierConfig)
    vol_span: int = 20


def _safe_col(df: pd.DataFrame, name: str) -> pd.Series | None:
    if name in df.columns:
        return df[name]
    matches = [c for c in df.columns if c.startswith(name)]
    return df[matches[0]] if matches else None


def primary_signals(
    df: pd.DataFrame,
    cfg: PrimaryRuleConfig,
    debug: bool = False,
) -> np.ndarray:
    """
    Devuelve las posiciones enteras (iloc) donde dispara la señal primaria.

    Regla long-only:
        - RSI <= rsi_oversold
        - volumen >= volume_min_ratio * avg(last volume_lookback)
        - [opcional] close > sma_long_col
        - [opcional] close > sma_short_col
        - sin señal en las últimas cooldown_bars barras

    Si `debug=True`, imprime cuántas barras cumplen cada condición por
    separado para diagnosticar.
    """
    rsi = _safe_col(df, cfg.rsi_col)
    sma_l = _safe_col(df, cfg.sma_long_col)
    sma_s = _safe_col(df, cfg.sma_short_col)
    vol = _safe_col(df, cfg.volume_col)
    close = df["close"]

    if rsi is None or vol is None:
        logger.error("primary_signals: faltan columnas requeridas (rsi/volume).")
        return np.array([], dtype=int)

    n = len(df)
    cond_rsi = (rsi <= cfg.rsi_oversold).fillna(False)
    vol_avg = vol.rolling(window=cfg.volume_lookback, min_periods=1).mean()
    cond_volume = (vol >= vol_avg * cfg.volume_min_ratio).fillna(False)

    if cfg.require_uptrend_long and sma_l is not None:
        cond_trend_long = (close > sma_l).fillna(False)
    else:
        cond_trend_long = pd.Series(np.ones(n, dtype=bool), index=df.index)

    if cfg.require_above_short and sma_s is not None:
        cond_short = (close > sma_s).fillna(False)
    else:
        cond_short = pd.Series(np.ones(n, dtype=bool), index=df.index)

    raw = (cond_rsi & cond_volume & cond_trend_long & cond_short).values

    if debug:
        logger.info(
            "primary_signals debug: rsi<=%.1f -> %d | vol>=%.2fx -> %d | "
            "trend_long -> %d | above_short -> %d | AND -> %d",
            cfg.rsi_oversold, int(cond_rsi.sum()),
            cfg.volume_min_ratio, int(cond_volume.sum()),
            int(cond_trend_long.sum()), int(cond_short.sum()),
            int(raw.sum()),
        )

    # Cooldown
    filtered = np.zeros(n, dtype=bool)
    last_fire = -10**9
    for i, hit in enumerate(raw):
        if hit and (i - last_fire) > cfg.cooldown_bars:
            filtered[i] = True
            last_fire = i

    event_idx = np.where(filtered)[0]
    logger.info(
        "primary_signals: %d eventos (%.2f%% de las barras, cooldown=%d).",
        len(event_idx), 100 * len(event_idx) / max(1, n), cfg.cooldown_bars,
    )
    return event_idx


def build_meta_dataset(
    df: pd.DataFrame,
    feature_cols: List[str],
    cfg: MetaLabelingConfig | None = None,
    debug: bool = False,
) -> tuple[np.ndarray, np.ndarray, pd.DataFrame]:
    """
    Construye el dataset de meta-labeling a partir del df con indicadores.

    Returns
    -------
    X : np.ndarray (n_events, n_features)
        Features en el momento del evento primario.
    y : np.ndarray (n_events,)
        Label binario: 1 si ret>0, 0 en caso contrario.
    events : pd.DataFrame
        Metadata completa de cada trade (t_in, t_out, ret, barrier, etc.).
    """
    cfg = cfg or MetaLabelingConfig()

    event_idx = primary_signals(df, cfg.primary, debug=debug)
    if len(event_idx) == 0:
        return np.zeros((0, len(feature_cols))), np.zeros(0, dtype=int), pd.DataFrame()

    vol = estimate_volatility(df["close"], span=cfg.vol_span)
    events = triple_barrier(df["close"], event_idx, vol, cfg.barrier)
    if events.empty:
        return np.zeros((0, len(feature_cols))), np.zeros(0, dtype=int), events

    missing = [c for c in feature_cols if c not in df.columns]
    if missing:
        logger.warning("build_meta_dataset: columnas ausentes %s", missing)
    usable = [c for c in feature_cols if c in df.columns]
    X_full = df[usable].values
    X = X_full[events["t_in"].values]
    y = events["bin_meta"].values.astype(int)

    mask = ~np.isnan(X).any(axis=1)
    if (~mask).any():
        logger.warning(
            "build_meta_dataset: %d eventos descartados por NaN en features.",
            int((~mask).sum()),
        )
    return X[mask], y[mask], events.loc[mask].reset_index(drop=True)
