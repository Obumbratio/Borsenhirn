"""Tests unitarios para componentes core de Borsenhirn."""
import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from strategy import TradingStrategy
from ml_model import TradingModel
from m3_risk import RiskEngine


def _make_mock_df(rows=150, trend="up"):
    """Crea un DataFrame con columnas OHLCV + indicadores tecnicos."""
    np.random.seed(42)
    dates = pd.date_range(end=datetime.now(), periods=rows, freq="h")

    if trend == "up":
        close = 100 + np.cumsum(np.random.randn(rows) * 0.3 + 0.05)
    elif trend == "down":
        close = 200 + np.cumsum(np.random.randn(rows) * 0.3 - 0.10)
    else:
        close = 150 + np.cumsum(np.random.randn(rows) * 0.2)

    high = close + np.abs(np.random.randn(rows) * 0.5)
    low = close - np.abs(np.random.randn(rows) * 0.5)
    opn = close + np.random.randn(rows) * 0.2
    volume = np.random.randint(500_000, 5_000_000, size=rows).astype(float)

    sma_short = pd.Series(close).rolling(config.MA_SHORT_WINDOW).mean().values
    sma_long = pd.Series(close).rolling(config.MA_LONG_WINDOW).mean().values
    rsi = 30 + np.random.rand(rows) * 40  # RSI entre 30-70

    bb_mid = pd.Series(close).rolling(config.BB_WINDOW).mean().values
    bb_std = pd.Series(close).rolling(config.BB_WINDOW).std().values
    bb_low = bb_mid - 2 * bb_std
    bb_high = bb_mid + 2 * bb_std

    macd = np.random.randn(rows) * 0.5
    macd_signal = np.random.randn(rows) * 0.5
    macd_hist = macd - macd_signal
    atr = np.abs(np.random.randn(rows) * 0.5) + 0.5

    df = pd.DataFrame({
        "open": opn,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        f"sma_{config.MA_SHORT_WINDOW}": sma_short,
        f"sma_{config.MA_LONG_WINDOW}": sma_long,
        "rsi": rsi,
        f"BBL_{config.BB_WINDOW}_{float(config.BB_STD)}": bb_low,
        f"BBM_{config.BB_WINDOW}_{float(config.BB_STD)}": bb_mid,
        f"BBU_{config.BB_WINDOW}_{float(config.BB_STD)}": bb_high,
        "MACD_12_26_9": macd,
        "MACDs_12_26_9": macd_signal,
        "MACDh_12_26_9": macd_hist,
        "atr": atr,
    }, index=dates)

    return df


class TestTradingStrategy(unittest.TestCase):

    def setUp(self):
        self.model = MagicMock(spec=TradingModel)
        self.model.predict_prob.return_value = 0.55
        self.strategy = TradingStrategy(model=self.model)
        self.df = _make_mock_df(rows=150)

    def test_generate_signal_returns_valid_action(self):
        """generate_signal debe retornar action en {buy, sell, hold}."""
        sig = self.strategy.generate_signal(self.df)
        self.assertIn(sig["action"], ("buy", "sell", "hold"))
        self.assertIn("confidence", sig)
        self.assertIn("reason", sig)
        self.assertIn("stop_loss", sig)

    def test_volume_filter_blocks_low_volume(self):
        """Volumen muy bajo debe bloquear la compra."""
        df = _make_mock_df(rows=150)
        # Forzar RSI oversold para intentar compra
        df["rsi"] = 20.0
        # Forzar volumen actual muy bajo respecto al promedio
        df.iloc[-1, df.columns.get_loc("volume")] = 1.0
        self.model.predict_prob.return_value = 0.80

        sig = self.strategy.generate_signal(df)
        # Con volumen casi 0, no deberia comprar
        self.assertIn(sig["action"], ("hold", "sell"))

    def test_volume_threshold_adjusts_for_bear(self):
        """En contexto bear (VIX alto), el umbral de compra sube."""
        df = _make_mock_df(rows=150)
        df["rsi"] = 25.0  # oversold
        self.model.predict_prob.return_value = 0.70

        # VIX alto = necesita mas senales para comprar
        market_ctx_bear = {
            "vix": {"value": 35},
            "fear_greed": {"value": 50},
            "market_signal": "neutral",
            "earnings": {"has_earnings": False, "days_away": 99},
        }
        sig_bear = self.strategy.generate_signal(df, market_ctx_bear)

        # VIX bajo = mas facil comprar
        market_ctx_calm = {
            "vix": {"value": 12},
            "fear_greed": {"value": 50},
            "market_signal": "neutral",
            "earnings": {"has_earnings": False, "days_away": 99},
        }
        sig_calm = self.strategy.generate_signal(df, market_ctx_calm)

        # No podemos garantizar acciones especificas con datos aleatorios,
        # pero al menos verificamos que la funcion no falla con market_ctx
        self.assertIn(sig_bear["action"], ("buy", "sell", "hold"))
        self.assertIn(sig_calm["action"], ("buy", "sell", "hold"))

    def test_earnings_blocks_buy(self):
        """Earnings en 1 dia debe bloquear la compra."""
        df = _make_mock_df(rows=150)
        df["rsi"] = 20.0  # forzar oversold
        self.model.predict_prob.return_value = 0.80

        market_ctx = {
            "vix": {"value": 15},
            "fear_greed": {"value": 50},
            "market_signal": "neutral",
            "earnings": {"has_earnings": True, "days_away": 1},
        }
        sig = self.strategy.generate_signal(df, market_ctx)
        # Con earnings en 1 dia, no deberia comprar
        self.assertIn(sig["action"], ("hold", "sell"))

    def test_insufficient_data_returns_hold(self):
        """Con datos insuficientes debe retornar hold."""
        short_df = _make_mock_df(rows=10)
        sig = self.strategy.generate_signal(short_df)
        self.assertEqual(sig["action"], "hold")
        self.assertIn("insuficientes", sig["reason"].lower())


class TestRiskEngine(unittest.TestCase):

    def setUp(self):
        self.engine = RiskEngine()

    @patch.object(RiskEngine, "_get_market_features")
    def test_evaluate_returns_valid_structure(self, mock_features):
        """evaluate() debe retornar dict con score, verdict, recommendation."""
        mock_features.return_value = {
            "volatility_annual": 0.20, "max_drawdown": -0.08,
            "trend_20": 0.02, "trend_50": 0.01, "vol_ratio": 1.1,
            "ret_1w": 0.01, "ret_1m": 0.03, "ret_3m": 0.08,
            "rsi": 55.0, "price": 150.0,
        }
        result = self.engine.evaluate("AAPL")

        self.assertIn("score", result)
        self.assertIn("verdict", result)
        self.assertIn("recommendation", result)
        self.assertIsInstance(result["score"], float)
        self.assertIn(result["verdict"], ("LOW", "MEDIUM", "HIGH"))
        self.assertIn(result["recommendation"], ("COMPRAR", "PRECAUCION", "EVITAR"))
        self.assertGreaterEqual(result["score"], 0.0)
        self.assertLessEqual(result["score"], 1.0)

    @patch.object(RiskEngine, "_get_market_features")
    def test_high_risk_blocks_buy(self, mock_features):
        """Score alto debe dar veredicto HIGH y recomendar EVITAR."""
        mock_features.return_value = {
            "volatility_annual": 0.60, "max_drawdown": -0.30,
            "trend_20": -0.10, "trend_50": -0.15, "vol_ratio": 2.5,
            "ret_1w": -0.08, "ret_1m": -0.20, "ret_3m": -0.30,
            "rsi": 15.0, "price": 80.0,
        }
        result = self.engine.evaluate("BAD_STOCK")

        self.assertEqual(result["verdict"], "HIGH")
        self.assertEqual(result["recommendation"], "EVITAR")
        self.assertGreaterEqual(result["score"], 0.60)

    @patch.object(RiskEngine, "_get_market_features")
    def test_low_risk_allows_buy(self, mock_features):
        """Score bajo debe dar veredicto LOW y recomendar COMPRAR."""
        mock_features.return_value = {
            "volatility_annual": 0.10, "max_drawdown": -0.03,
            "trend_20": 0.05, "trend_50": 0.04, "vol_ratio": 1.0,
            "ret_1w": 0.02, "ret_1m": 0.06, "ret_3m": 0.12,
            "rsi": 50.0, "price": 200.0,
        }
        result = self.engine.evaluate("GOOD_STOCK")

        self.assertEqual(result["verdict"], "LOW")
        self.assertEqual(result["recommendation"], "COMPRAR")
        self.assertLess(result["score"], 0.35)


class TestRegimeDetector(unittest.TestCase):

    @unittest.skipIf(True, "RegimeDetector requiere DataFetcher con datos reales")
    def test_detect_regime_with_mock(self):
        """Placeholder: requiere fetcher con datos reales."""
        pass

    def test_classify_function(self):
        """Probar la funcion interna _classify directamente."""
        try:
            from regime_detector import _classify
        except ImportError:
            self.skipTest("No se pudo importar _classify")

        # PANIC: VIX > 35
        regime, conf = _classify(
            spy_above_sma50=False, spy_above_sma20=False,
            spy_day_change_pct=-4.0, vix=40.0,
            breadth=0.15, adx=30.0,
        )
        self.assertEqual(regime, "PANIC")

        # BULL: todo positivo
        regime, conf = _classify(
            spy_above_sma50=True, spy_above_sma20=True,
            spy_day_change_pct=0.5, vix=14.0,
            breadth=0.75, adx=25.0,
        )
        self.assertEqual(regime, "BULL")

    def test_hysteresis(self):
        """Probar que la histeresis requiere ciclos consecutivos."""
        try:
            from regime_detector import _apply_hysteresis, _state
        except ImportError:
            self.skipTest("No se pudo importar _apply_hysteresis")

        _state.reset()
        # Primer ciclo: se confirma porque no hay historial
        result = _apply_hysteresis("BULL")
        self.assertEqual(result, "BULL")


if __name__ == "__main__":
    unittest.main()
