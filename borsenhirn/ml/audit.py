"""
Auditorías pre-entrenamiento del dataset.

  - population_stability_index: detecta drift de cada feature entre train y test.
  - check_label_leakage: heurística para detectar features que correlacionan
    sospechosamente con close futuro (lookahead bias).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def population_stability_index(
    train: np.ndarray, test: np.ndarray, n_bins: int = 10
) -> float:
    """
    Population Stability Index entre dos distribuciones.

    Interpretación estándar en riesgo de crédito / ML ops:
      - PSI < 0.10  → estable
      - 0.10 - 0.25 → cambio moderado (vigilar)
      - PSI > 0.25  → cambio significativo (reentrenar / investigar)

    Se usan quantiles del train como breakpoints, y luego se compara la
    proporción de muestras de test que caen en cada bin.
    """
    train = np.asarray(train, dtype=float)
    test = np.asarray(test, dtype=float)
    train = train[~np.isnan(train)]
    test = test[~np.isnan(test)]
    if len(train) < n_bins or len(test) < n_bins:
        return float("nan")

    breakpoints = np.quantile(train, np.linspace(0, 1, n_bins + 1))
    # Extremos abiertos para capturar out-of-range
    breakpoints[0] = -np.inf
    breakpoints[-1] = np.inf
    # Binning
    train_counts, _ = np.histogram(train, bins=breakpoints)
    test_counts, _ = np.histogram(test, bins=breakpoints)
    train_pct = train_counts / max(1, len(train))
    test_pct = test_counts / max(1, len(test))
    # Smoothing para evitar log(0)
    eps = 1e-6
    train_pct = np.clip(train_pct, eps, None)
    test_pct = np.clip(test_pct, eps, None)
    return float(np.sum((test_pct - train_pct) * np.log(test_pct / train_pct)))


def check_label_leakage(
    df: pd.DataFrame,
    label_horizon: int,
    corr_threshold: float = 0.95,
    min_overlap: int = 30,
    ignore_cols: tuple = ("open", "high", "low", "close", "volume"),
) -> Dict[str, Any]:
    """
    Heurística para detectar lookahead bias en features.

    Calcula, para cada feature y cada horizonte h en [1, label_horizon],
    la correlación con `close.shift(-h)` (valor futuro de close). Si es
    muy alta, es sospechoso.

    Limitaciones: puede falsear positivos si el feature es un proxy obvio
    del precio (p.ej. un SMA corto). Los positivos reales requieren revisión
    manual — esta función no bloquea, solo advierte.
    """
    if "close" not in df.columns:
        return {"warnings": [], "clean": True, "note": "close ausente"}

    close = df["close"]
    warnings_list: List[Dict[str, Any]] = []

    for col in df.columns:
        if col in ignore_cols:
            continue
        for h in range(1, max(1, label_horizon) + 1):
            future = close.shift(-h)
            mask = df[col].notna() & future.notna()
            if int(mask.sum()) < min_overlap:
                continue
            try:
                corr = float(df.loc[mask, col].corr(future.loc[mask]))
            except Exception as exc:  # pragma: no cover
                logger.debug("corr falló en %s h=%d: %s", col, h, exc)
                continue
            if np.isnan(corr):
                continue
            if abs(corr) > corr_threshold:
                warnings_list.append(
                    {
                        "feature": col,
                        "horizon": h,
                        "corr_with_future_close": corr,
                    }
                )

    return {
        "warnings": warnings_list,
        "clean": len(warnings_list) == 0,
        "corr_threshold": corr_threshold,
    }
