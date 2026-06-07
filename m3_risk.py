"""
m3_risk.py — M3 Market Risk Engine para Börsenhirn.

Evalúa el riesgo de mercado de un símbolo usando indicadores reales:
volatilidad, drawdown, RSI, tendencia, volumen y retornos.

No usa modelos de crédito — el scoring es directo sobre features de mercado.
"""

import os
import logging
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timezone

import config

logger = logging.getLogger(__name__)

RISK_LOW    = 0.35
RISK_MEDIUM = 0.60


class RiskEngine:

    def __init__(self):
        pass

    def _get_market_features(self, symbol: str) -> dict:
        try:
            hist = yf.Ticker(symbol).history(period="90d")
            if hist.empty or len(hist) < 20:
                return self._default_market_features()

            close  = hist["Close"]
            volume = hist["Volume"]
            returns      = close.pct_change().dropna()
            volatility   = float(returns.std() * np.sqrt(252))
            max_drawdown = self._calc_max_drawdown(close)

            sma20     = close.rolling(20).mean().iloc[-1]
            sma50     = close.rolling(min(50, len(close))).mean().iloc[-1]
            price_now = float(close.iloc[-1])
            sma20_val = float(sma20) if not np.isnan(sma20) else price_now
            sma50_val = float(sma50) if not np.isnan(sma50) else price_now
            trend_20  = (price_now - sma20_val) / sma20_val if sma20_val > 0 else 0.0
            trend_50  = (price_now - sma50_val) / sma50_val if sma50_val > 0 else 0.0

            vol_avg   = float(volume.rolling(20).mean().iloc[-1])
            vol_now   = float(volume.iloc[-1])
            vol_ratio = vol_now / vol_avg if vol_avg > 0 else 1.0

            ret_1w = float((close.iloc[-1] - close.iloc[-5])  / close.iloc[-5])  if len(close) >= 5  else 0.0
            ret_1m = float((close.iloc[-1] - close.iloc[-21]) / close.iloc[-21]) if len(close) >= 21 else 0.0
            ret_3m = float((close.iloc[-1] - close.iloc[0])   / close.iloc[0])

            delta = close.diff()
            gain  = delta.clip(lower=0).rolling(14).mean().iloc[-1]
            loss  = (-delta.clip(upper=0)).rolling(14).mean().iloc[-1]
            rsi   = float(100 - (100 / (1 + gain / loss))) if loss > 0 else 50.0

            features = {
                "volatility_annual": volatility, "max_drawdown": max_drawdown,
                "trend_20": trend_20, "trend_50": trend_50,
                "vol_ratio": vol_ratio, "ret_1w": ret_1w,
                "ret_1m": ret_1m, "ret_3m": ret_3m,
                "rsi": rsi, "price": price_now,
            }
            for k, v in features.items():
                if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
                    features[k] = 0.0
                else:
                    features[k] = round(float(v), 4)

            logger.info(f"[M3] {symbol}: vol={volatility:.2%} rsi={rsi:.1f} trend={trend_20:.2%}")
            return features

        except Exception as e:
            logger.error(f"[M3] Error obteniendo datos de {symbol}: {e}")
            return self._default_market_features()

    def _default_market_features(self) -> dict:
        return {
            "volatility_annual": 0.25, "max_drawdown": -0.10,
            "trend_20": 0.0, "trend_50": 0.0, "vol_ratio": 1.0,
            "ret_1w": 0.0, "ret_1m": 0.0, "ret_3m": 0.0,
            "rsi": 50.0, "price": 100.0,
        }

    def _calc_max_drawdown(self, prices: pd.Series) -> float:
        peak = prices.cummax()
        dd   = (prices - peak) / peak
        val  = float(dd.min())
        return val if not np.isnan(val) else 0.0

    def _score_risk(self, market: dict) -> tuple:
        """
        Calcula un score de riesgo 0.0-1.0 basado en features de mercado reales.
        Retorna (score, factores) donde factores es lista de (nombre, contribucion, direccion).
        """
        factors = []

        # 1. Volatilidad anualizada (peso: 25%)
        #    <15% = bajo riesgo, 15-30% = medio, >30% = alto
        vol = market["volatility_annual"]
        if vol < 0.15:
            vol_score = vol / 0.15 * 0.35
        elif vol < 0.30:
            vol_score = 0.35 + (vol - 0.15) / 0.15 * 0.30
        else:
            vol_score = min(0.65 + (vol - 0.30) / 0.20 * 0.35, 1.0)
        factors.append(("Volatilidad anualizada", round(vol_score * 0.25, 4), "aumenta" if vol_score > 0.5 else "reduce"))

        # 2. Max drawdown (peso: 20%)
        dd = abs(market["max_drawdown"])
        if dd < 0.05:
            dd_score = dd / 0.05 * 0.3
        elif dd < 0.15:
            dd_score = 0.3 + (dd - 0.05) / 0.10 * 0.35
        else:
            dd_score = min(0.65 + (dd - 0.15) / 0.15 * 0.35, 1.0)
        factors.append(("Drawdown maximo", round(dd_score * 0.20, 4), "aumenta" if dd_score > 0.5 else "reduce"))

        # 3. RSI extremo (peso: 15%)
        #    RSI >70 o <30 = mayor riesgo (sobrecompra/sobreventa)
        rsi = market["rsi"]
        if 40 <= rsi <= 60:
            rsi_score = 0.1
        elif 30 <= rsi <= 70:
            rsi_score = 0.3
        else:
            rsi_score = 0.6 + min(abs(rsi - 50) - 20, 30) / 30 * 0.4
        factors.append(("RSI extremo", round(rsi_score * 0.15, 4), "aumenta" if rsi > 70 or rsi < 30 else "reduce"))

        # 4. Tendencia negativa (peso: 20%)
        #    Precio bajo SMA20/SMA50 = mayor riesgo
        t20 = market["trend_20"]
        t50 = market["trend_50"]
        if t20 > 0.02 and t50 > 0.02:
            trend_score = 0.1
        elif t20 > 0 or t50 > 0:
            trend_score = 0.3
        elif t20 > -0.05:
            trend_score = 0.5
        else:
            trend_score = min(0.5 + abs(t20) * 5, 1.0)
        factors.append(("Tendencia de precio", round(trend_score * 0.20, 4), "aumenta" if t20 < 0 else "reduce"))

        # 5. Retornos recientes negativos (peso: 15%)
        ret_1m = market["ret_1m"]
        ret_1w = market["ret_1w"]
        if ret_1m > 0.05 and ret_1w > 0:
            ret_score = 0.1
        elif ret_1m > 0:
            ret_score = 0.3
        elif ret_1m > -0.10:
            ret_score = 0.5
        else:
            ret_score = min(0.5 + abs(ret_1m) * 3, 1.0)
        factors.append(("Retornos recientes", round(ret_score * 0.15, 4), "aumenta" if ret_1m < 0 else "reduce"))

        # 6. Volumen anomalo (peso: 5%)
        vol_ratio = market["vol_ratio"]
        if 0.8 <= vol_ratio <= 1.5:
            volr_score = 0.2
        elif vol_ratio > 2.0:
            volr_score = 0.7
        else:
            volr_score = 0.5
        factors.append(("Volumen anomalo", round(volr_score * 0.05, 4), "aumenta" if vol_ratio > 1.5 else "reduce"))

        # Score final ponderado
        score = (vol_score * 0.25 + dd_score * 0.20 + rsi_score * 0.15 +
                 trend_score * 0.20 + ret_score * 0.15 + volr_score * 0.05)

        return round(min(max(score, 0.0), 1.0), 4), factors

    def evaluate(self, symbol: str) -> dict:
        market = self._get_market_features(symbol)
        score, factors = self._score_risk(market)

        if score < RISK_LOW:
            verdict, verdict_es, rec, emoji = "LOW",    "Riesgo bajo",  "COMPRAR",    "✅"
        elif score < RISK_MEDIUM:
            verdict, verdict_es, rec, emoji = "MEDIUM", "Riesgo medio", "PRECAUCION", "⚠️"
        else:
            verdict, verdict_es, rec, emoji = "HIGH",   "Riesgo alto",  "EVITAR",     "🚫"

        # Top 3 factores por impacto
        shap_factors = sorted(
            [{"factor": f[0], "impact": f[1], "direction": f[2]} for f in factors],
            key=lambda x: x["impact"], reverse=True
        )[:3]

        explanation = self._generate_explanation(symbol, score, verdict, market, shap_factors)

        logger.info(f"[M3] {symbol} → {emoji} {verdict_es} | score={score:.2f}")
        return {
            "symbol": symbol, "score": round(score, 4),
            "verdict": verdict, "verdict_es": verdict_es,
            "recommendation": rec, "emoji": emoji,
            "explanation": explanation, "shap_factors": shap_factors,
            "market": {
                "volatility":   f"{market['volatility_annual']:.1%}",
                "max_drawdown": f"{market['max_drawdown']:.1%}",
                "trend_20d":    f"{market['trend_20']:+.1%}",
                "rsi":          round(market["rsi"], 1),
                "ret_1m":       f"{market['ret_1m']:+.1%}",
                "ret_3m":       f"{market['ret_3m']:+.1%}",
            },
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

    def _generate_explanation(self, symbol, score, verdict, market, shap_factors):
        vol, dd, rsi, t20, r1m = (
            market["volatility_annual"], market["max_drawdown"],
            market["rsi"], market["trend_20"], market["ret_1m"]
        )
        lines = [f"{symbol} — Score: {score:.0%}."]
        if verdict == "LOW":
            lines.append(f"Condiciones favorables. Volatilidad {vol:.1%}.")
        elif verdict == "MEDIUM":
            lines.append(f"Riesgo moderado. Volatilidad {vol:.1%}, drawdown {dd:.1%}.")
        else:
            lines.append(f"Riesgo elevado. Volatilidad {vol:.1%} y drawdown {dd:.1%}.")
        if rsi > 70:   lines.append(f"RSI={rsi:.0f}: sobrecomprado.")
        elif rsi < 30: lines.append(f"RSI={rsi:.0f}: sobrevendido.")
        else:          lines.append(f"RSI={rsi:.0f}: zona neutral.")
        if t20 > 0.03:  lines.append(f"Tendencia alcista ({t20:+.1%} sobre SMA20).")
        elif t20 < -0.03: lines.append(f"Tendencia bajista ({t20:+.1%} bajo SMA20).")
        if shap_factors:
            top = shap_factors[0]
            lines.append(f"Factor principal: {top['factor']} {top['direction']} el riesgo.")
        return " ".join(lines)

    def evaluate_watchlist(self, symbols=None):
        if symbols is None:
            symbols = config.WATCHLIST
        logger.info(f"[M3] Evaluando {len(symbols)} símbolos...")
        results = []
        for s in symbols:
            try:
                results.append(self.evaluate(s))
            except Exception as e:
                logger.error(f"[M3] Error en {s}: {e}")
        results.sort(key=lambda x: x["score"])
        low = sum(1 for r in results if r["verdict"] == "LOW")
        med = sum(1 for r in results if r["verdict"] == "MEDIUM")
        high = sum(1 for r in results if r["verdict"] == "HIGH")
        logger.info(f"[M3] LOW={low} | MEDIUM={med} | HIGH={high}")
        return results

    def get_safe_symbols(self, symbols=None, max_score=RISK_MEDIUM):
        return [r for r in self.evaluate_watchlist(symbols) if r["score"] < max_score]


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-8s | %(message)s")
    p = argparse.ArgumentParser()
    p.add_argument("--eval",      type=str)
    p.add_argument("--watchlist", action="store_true")
    p.add_argument("--top",       type=int, default=10)
    a = p.parse_args()

    engine = RiskEngine()

    if a.eval:
        print(f"\n=== EVALUANDO {a.eval.upper()} ===")
        r = engine.evaluate(a.eval.upper())
        print(f"\n  Score:         {r['score']:.4f}")
        print(f"  Veredicto:     {r['emoji']} {r['verdict_es']}")
        print(f"  Recomendación: {r['recommendation']}")
        print(f"\n  Mercado:")
        for k, v in r["market"].items():
            print(f"    {k:15}: {v}")
        print(f"\n  Explicación: {r['explanation']}")
        print(f"\n  Factores de riesgo:")
        for f in r["shap_factors"]:
            print(f"    {f['factor']:25}: {f['direction']} riesgo (impacto={f['impact']:.4f})")

    elif a.watchlist:
        results = engine.evaluate_watchlist()
        print(f"\n{'#':>3} {'Símbolo':>8} {'Score':>7} {'Veredicto':>12} {'Vol':>8} {'RSI':>6} {'1m':>8}")
        print("-" * 62)
        for i, r in enumerate(results[:a.top], 1):
            print(f"  {i:>2}. {r['symbol']:>6}  {r['score']:>6.3f}  "
                  f"{r['emoji']} {r['verdict']:>6}  "
                  f"{r['market']['volatility']:>7}  "
                  f"{r['market']['rsi']:>5}  "
                  f"{r['market']['ret_1m']:>7}")
    else:
        print("Uso: python m3_risk.py --eval AAPL | --watchlist")
