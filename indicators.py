"""
indicators.py - Indicadores técnicos usando la librería 'ta'
Compatible con Python 3.14
"""

import logging
import pandas as pd
import ta
import config

logger = logging.getLogger(__name__)


def add_moving_averages(df, short=config.MA_SHORT_WINDOW, long=config.MA_LONG_WINDOW):
    df[f"sma_{short}"] = df["close"].rolling(window=short).mean()
    df[f"sma_{long}"]  = df["close"].rolling(window=long).mean()
    return df


def add_rsi(df, period=config.RSI_PERIOD):
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=period).rsi()
    return df


def add_macd(df):
    macd_ind = ta.trend.MACD(df["close"])
    df["MACD_12_26_9"]  = macd_ind.macd()
    df["MACDs_12_26_9"] = macd_ind.macd_signal()
    df["MACDh_12_26_9"] = macd_ind.macd_diff()
    return df


def add_bollinger_bands(df, window=config.BB_WINDOW, std=config.BB_STD):
    bb = ta.volatility.BollingerBands(df["close"], window=window, window_dev=std)
    df[f"BBL_{window}_{float(std)}"] = bb.bollinger_lband()
    df[f"BBM_{window}_{float(std)}"] = bb.bollinger_mavg()
    df[f"BBU_{window}_{float(std)}"] = bb.bollinger_hband()
    return df


def add_atr(df, period=config.ATR_PERIOD):
    df["atr"] = ta.volatility.AverageTrueRange(
        df["high"], df["low"], df["close"], window=period
    ).average_true_range()
    return df


def add_all_indicators(df):
    df = add_moving_averages(df)
    df = add_rsi(df)
    df = add_macd(df)
    df = add_bollinger_bands(df)
    df = add_atr(df)
    before = len(df)
    df.dropna(inplace=True)
    logger.info(f"Indicadores OK. Filas: {len(df)} (dropped {before - len(df)})")
    return df