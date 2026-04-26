"""
Meta-features para el modelo de meta-labeling.

Input: DataFrame con columnas mínimas ['open','high','low','close','volume']
       más los indicadores técnicos básicos (rsi, atr, sma_20, sma_100,
       Bollinger bands, MACD).

Output: mismo DataFrame con ~18 columnas nuevas que aportan contexto:
    - Temporales (hora, día de semana, mes).
    - Régimen de mercado derivado (tendencia long/short + vol regime).
    - Rolling percentiles (RSI, volumen, ATR) — dónde está el indicador dentro
      de su distribución reciente, no su valor absoluto.
    - Retornos multi-escala (1, 5, 20, 60 barras).
    - Distancias normalizadas por ATR (precio vs SMAs, Bollinger position).
    - Vol-of-vol.

No depende de APIs externas — todo se deriva del DataFrame.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


META_FEATURE_COLS = [
    # Temporales
    "mf_hour", "mf_dow", "mf_is_monday", "mf_is_friday",
    # Régimen derivado
    "mf_trend_regime",       # +1 bull, 0 side, -1 bear
    "mf_vol_regime",         # +1 alta vol, 0 normal, -1 baja vol
    # Percentiles rolling
    "mf_rsi_pct_100",        # percentile del RSI en las últimas 100 barras
    "mf_atr_pct_100",        # percentile del ATR en las últimas 100 barras
    "mf_vol_pct_100",        # percentile del volumen
    # Retornos multi-escala
    "mf_ret_1", "mf_ret_5", "mf_ret_20", "mf_ret_60",
    # Distancias normalizadas por ATR
    "mf_price_sma20_atr", "mf_price_sma100_atr",
    "mf_bb_position",        # (close - BBL) / (BBU - BBL), 0=suelo, 1=techo
    # Volatilidad compuesta
    "mf_vol_of_vol",         # std del ATR rolling 20
    "mf_realized_vol_20",    # std de retornos rolling 20
    "mf_vol_expansion",      # vol_20 / vol_100
]


def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    """Percentile del último valor dentro de la ventana rolling [0, 1]."""
    return series.rolling(window, min_periods=max(10, window // 4)).rank(pct=True)


def _safe_col(df: pd.DataFrame, prefix: str) -> pd.Series | None:
    if prefix in df.columns:
        return df[prefix]
    matches = [c for c in df.columns if c.startswith(prefix)]
    return df[matches[0]] if matches else None


def add_meta_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Añade las columnas META_FEATURE_COLS al df. Modifica y devuelve el df.

    Asume que el índice es DatetimeIndex (si no lo es, las features
    temporales se llenan con 0).
    """
    out = df.copy()
    close = out["close"]

    # ── Temporales ──────────────────────────────────────
    if isinstance(out.index, pd.DatetimeIndex):
        out["mf_hour"] = out.index.hour.astype(float)
        out["mf_dow"] = out.index.dayofweek.astype(float)
        out["mf_is_monday"] = (out.index.dayofweek == 0).astype(float)
        out["mf_is_friday"] = (out.index.dayofweek == 4).astype(float)
    else:
        out["mf_hour"] = 0.0
        out["mf_dow"] = 0.0
        out["mf_is_monday"] = 0.0
        out["mf_is_friday"] = 0.0

    # ── Régimen derivado ────────────────────────────────
    sma20 = _safe_col(out, "sma_20")
    sma100 = _safe_col(out, "sma_100")
    atr = _safe_col(out, "atr")

    if sma20 is not None and sma100 is not None:
        # trend: +1 si sma20>sma100 y close>sma20, -1 si opuesto
        bull = (sma20 > sma100) & (close > sma20)
        bear = (sma20 < sma100) & (close < sma20)
        trend_regime = pd.Series(0.0, index=out.index)
        trend_regime[bull] = 1.0
        trend_regime[bear] = -1.0
        out["mf_trend_regime"] = trend_regime
    else:
        out["mf_trend_regime"] = 0.0

    if atr is not None:
        atr_median = atr.rolling(200, min_periods=50).median()
        atr_ratio = atr / atr_median
        vol_regime = pd.Series(0.0, index=out.index)
        vol_regime[atr_ratio > 1.25] = 1.0
        vol_regime[atr_ratio < 0.75] = -1.0
        out["mf_vol_regime"] = vol_regime.fillna(0.0)
    else:
        out["mf_vol_regime"] = 0.0

    # ── Percentiles rolling ─────────────────────────────
    rsi = _safe_col(out, "rsi")
    if rsi is not None:
        out["mf_rsi_pct_100"] = _rolling_percentile(rsi, 100).fillna(0.5)
    else:
        out["mf_rsi_pct_100"] = 0.5

    if atr is not None:
        out["mf_atr_pct_100"] = _rolling_percentile(atr, 100).fillna(0.5)
    else:
        out["mf_atr_pct_100"] = 0.5

    if "volume" in out.columns:
        out["mf_vol_pct_100"] = _rolling_percentile(out["volume"], 100).fillna(0.5)
    else:
        out["mf_vol_pct_100"] = 0.5

    # ── Retornos multi-escala ───────────────────────────
    for h in [1, 5, 20, 60]:
        col = f"mf_ret_{h}"
        ret = close.pct_change(h)
        out[col] = ret.replace([np.inf, -np.inf], 0.0).fillna(0.0)

    # ── Distancias normalizadas por ATR ─────────────────
    if sma20 is not None and atr is not None:
        safe_atr = atr.replace(0, np.nan)
        out["mf_price_sma20_atr"] = ((close - sma20) / safe_atr).replace(
            [np.inf, -np.inf], 0.0).fillna(0.0)
    else:
        out["mf_price_sma20_atr"] = 0.0

    if sma100 is not None and atr is not None:
        safe_atr = atr.replace(0, np.nan)
        out["mf_price_sma100_atr"] = ((close - sma100) / safe_atr).replace(
            [np.inf, -np.inf], 0.0).fillna(0.0)
    else:
        out["mf_price_sma100_atr"] = 0.0

    # Bollinger position
    bbl = _safe_col(out, "BBL_")
    bbu = _safe_col(out, "BBU_")
    if bbl is not None and bbu is not None:
        band_width = (bbu - bbl).replace(0, np.nan)
        out["mf_bb_position"] = ((close - bbl) / band_width).clip(-1, 2).fillna(0.5)
    else:
        out["mf_bb_position"] = 0.5

    # ── Volatilidad compuesta ───────────────────────────
    logret = np.log(close / close.shift(1))
    rvol_20 = logret.rolling(20, min_periods=5).std()
    rvol_100 = logret.rolling(100, min_periods=25).std()
    out["mf_realized_vol_20"] = rvol_20.fillna(0.0)
    vol_exp = (rvol_20 / rvol_100.replace(0, np.nan)).replace(
        [np.inf, -np.inf], 1.0).fillna(1.0)
    out["mf_vol_expansion"] = vol_exp

    if atr is not None:
        vol_of_vol = atr.rolling(20, min_periods=5).std()
        out["mf_vol_of_vol"] = vol_of_vol.fillna(0.0)
    else:
        out["mf_vol_of_vol"] = 0.0

    return out


def get_meta_feature_cols() -> list[str]:
    """Lista de columnas agregadas por add_meta_features."""
    return list(META_FEATURE_COLS)
