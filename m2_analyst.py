"""
m2_analyst.py — Financial Analyst Module para Börsenhirn
=========================================================
Componentes:
  1. MacroFetcher       — FRED: tasas, CPI, desempleo
  2. InsiderFetcher     — SEC Form 4: compras de directivos
  3. CongressFetcher    — STOCK Act: trades de senadores/congresistas
  4. InstitutionalFetcher — 13F: posiciones de whales (Buffett, Ackman, etc.)
  5. AnalystRatings     — Finnhub: ratings y price targets de bancos
  6. PricePredictor     — Prophet: predicción de precio a 5 días
  7. PortfolioAnalyzer  — correlación, concentración sectorial
  8. ConvergenceEngine  — pondera todas las señales, ajusta por capital
  9. AnalystAgent       — Claude API: genera reporte narrado completo
"""

import os, logging, json, time, requests
from datetime import datetime, timezone, timedelta
from typing import Optional
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# ── Importaciones opcionales (no rompen si no están instaladas) ───────────────
try:
    from prophet import Prophet
    PROPHET_OK = True
except ImportError:
    PROPHET_OK = False
    logger.warning("[M2] Prophet no instalado — predicciones desactivadas.")

try:
    import finnhub
    FINNHUB_OK = True
except ImportError:
    FINNHUB_OK = False

try:
    from fredapi import Fred
    FRED_OK = True
except ImportError:
    FRED_OK = False

try:
    import config as _cfg
    ALPACA_KEY    = _cfg.ALPACA_API_KEY
    FINNHUB_KEY   = _cfg.FINNHUB_API_KEY
    FRED_KEY      = _cfg.FRED_API_KEY
    CLAUDE_KEY    = os.getenv("ANTHROPIC_API_KEY", "")
    BOT_API_URL   = os.getenv("BOT_API_URL", "http://localhost:8000")
except Exception:
    ALPACA_KEY = FINNHUB_KEY = FRED_KEY = CLAUDE_KEY = ""
    BOT_API_URL = "http://localhost:8000"

# ─────────────────────────────────────────────────────────────────────────────
# 1. MacroFetcher — FRED: tasas de interés, CPI, desempleo
# ─────────────────────────────────────────────────────────────────────────────
class MacroFetcher:
    """Obtiene indicadores macroeconómicos de FRED."""

    SERIES = {
        "fed_rate":    "FEDFUNDS",   # Tasa Fed Funds
        "cpi":         "CPIAUCSL",   # Inflación CPI
        "unemployment":"UNRATE",     # Desempleo
        "treasury_10y":"GS10",       # Bono 10 años
        "treasury_2y": "GS2",        # Bono 2 años (yield curve)
        "gdp_growth":  "A191RL1Q225SBEA", # Crecimiento PIB
    }

    def __init__(self):
        self.fred = Fred(api_key=FRED_KEY) if FRED_OK and FRED_KEY else None

    def fetch(self) -> dict:
        result = {}
        if not self.fred:
            logger.warning("[M2][MACRO] FRED no disponible.")
            return result
        for name, series_id in self.SERIES.items():
            try:
                s = self.fred.get_series(series_id, observation_start="2024-01-01")
                if s is not None and not s.empty:
                    latest = float(s.dropna().iloc[-1])
                    prev   = float(s.dropna().iloc[-2]) if len(s.dropna()) >= 2 else latest
                    result[name] = {
                        "value":  round(latest, 3),
                        "change": round(latest - prev, 3),
                        "trend":  "rising" if latest > prev else "falling" if latest < prev else "flat"
                    }
            except Exception as e:
                logger.warning(f"[M2][MACRO] {name}: {e}")
        # Yield curve: 10y - 2y (negativo = posible recesión)
        if "treasury_10y" in result and "treasury_2y" in result:
            spread = result["treasury_10y"]["value"] - result["treasury_2y"]["value"]
            result["yield_curve_spread"] = round(spread, 3)
            result["yield_curve_inverted"] = spread < 0
        logger.info(f"[M2][MACRO] Datos obtenidos: {list(result.keys())}")
        return result

    def get_macro_signal(self, macro: dict) -> str:
        """Convierte macro en señal: bullish / bearish / neutral."""
        bearish_signals = 0
        bullish_signals = 0
        if macro.get("fed_rate", {}).get("trend") == "rising":
            bearish_signals += 1
        if macro.get("cpi", {}).get("value", 0) > 4.0:
            bearish_signals += 1
        if macro.get("unemployment", {}).get("trend") == "rising":
            bearish_signals += 1
        if macro.get("yield_curve_inverted"):
            bearish_signals += 1
        if macro.get("gdp_growth", {}).get("value", 0) > 2.0:
            bullish_signals += 1
        if macro.get("fed_rate", {}).get("trend") == "falling":
            bullish_signals += 1
        if bearish_signals >= 3:   return "bearish"
        if bullish_signals >= 2:   return "bullish"
        return "neutral"


# ─────────────────────────────────────────────────────────────────────────────
# 2. InsiderFetcher — SEC Form 4: directivos comprando su propia empresa
# ─────────────────────────────────────────────────────────────────────────────
class InsiderFetcher:
    """Scrapa compras de insiders desde SEC EDGAR (Form 4). Gratis, sin key."""

    BASE = "https://efts.sec.gov/LATEST/search-index"
    HEADERS = {"User-Agent": "Borsenhirn research@borsenhirn.com"}

    def fetch_symbol(self, symbol: str, days_back: int = 90) -> dict:
        """Retorna señal de insider buying para un símbolo."""
        try:
            # Buscar Form 4 del símbolo en EDGAR full-text search
            url = "https://efts.sec.gov/LATEST/search-index"
            params = {
                "q": f'"{symbol}" "acquired"',
                "dateRange": "custom",
                "startdt": (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d"),
                "enddt":   datetime.now().strftime("%Y-%m-%d"),
                "forms":   "4",
            }
            resp = requests.get(url, params=params, headers=self.HEADERS, timeout=10)
            if resp.status_code != 200:
                return {"symbol": symbol, "signal": "neutral", "count": 0}

            data  = resp.json()
            hits  = data.get("hits", {}).get("hits", [])
            buys  = 0
            sells = 0
            for hit in hits[:20]:
                src = hit.get("_source", {})
                # Form 4: código A = acquired, D = disposed
                if "acquired" in str(src).lower():
                    buys += 1
                elif "disposed" in str(src).lower():
                    sells += 1

            if buys > sells and buys >= 2:
                signal = "bullish"
            elif sells > buys and sells >= 2:
                signal = "bearish"
            else:
                signal = "neutral"

            result = {"symbol": symbol, "signal": signal,
                      "buys": buys, "sells": sells,
                      "score": round(buys / max(buys + sells, 1), 2)}
            logger.info(f"[M2][INSIDER] {symbol}: {signal} (buys={buys}, sells={sells})")
            return result

        except Exception as e:
            logger.warning(f"[M2][INSIDER] {symbol}: {e}")
            return {"symbol": symbol, "signal": "neutral", "count": 0, "score": 0.5}

    def fetch_batch(self, symbols: list) -> dict:
        results = {}
        for sym in symbols:
            results[sym] = self.fetch_symbol(sym)
            time.sleep(0.3)  # respetar rate limit de SEC
        return results


# ─────────────────────────────────────────────────────────────────────────────
# 3. CongressFetcher — STOCK Act: trades de senadores y congresistas
# ─────────────────────────────────────────────────────────────────────────────
class CongressFetcher:
    """Obtiene trades del Congreso desde housestockwatcher.com (gratis)."""

    HOUSE_URL  = "https://house-stock-watcher-data.s3-us-gov-west-1.amazonaws.com/data/all_transactions.json"
    SENATE_URL = "https://senate-stock-watcher-data.s3-us-gov-west-1.amazonaws.com/aggregate/all_transactions.json"

    def _fetch_json(self, url: str) -> list:
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            logger.warning(f"[M2][CONGRESS] Error fetching {url}: {e}")
        return []

    def fetch_symbol(self, symbol: str, days_back: int = 180) -> dict:
        cutoff = datetime.now() - timedelta(days=days_back)
        buys   = 0
        sells  = 0

        for data in [self._fetch_json(self.HOUSE_URL),
                     self._fetch_json(self.SENATE_URL)]:
            for tx in data:
                tx_sym = tx.get("ticker", "").upper().strip()
                if tx_sym != symbol.upper():
                    continue
                try:
                    tx_date_str = tx.get("transaction_date") or tx.get("disclosure_date", "")
                    tx_date = datetime.strptime(tx_date_str[:10], "%Y-%m-%d")
                    if tx_date < cutoff:
                        continue
                except Exception:
                    continue
                tx_type = tx.get("type", "").lower()
                if "purchase" in tx_type or "buy" in tx_type:
                    buys += 1
                elif "sale" in tx_type or "sell" in tx_type:
                    sells += 1

        if buys > sells and buys >= 1:
            signal = "bullish"
        elif sells > buys and sells >= 2:
            signal = "bearish"
        else:
            signal = "neutral"

        result = {"symbol": symbol, "signal": signal,
                  "congress_buys": buys, "congress_sells": sells,
                  "score": round(buys / max(buys + sells, 1), 2) if (buys + sells) > 0 else 0.5}
        logger.info(f"[M2][CONGRESS] {symbol}: {signal} (buys={buys}, sells={sells})")
        return result

    def fetch_batch(self, symbols: list) -> dict:
        # Descarga datos una vez y filtra por símbolo (más eficiente)
        house_data  = self._fetch_json(self.HOUSE_URL)
        senate_data = self._fetch_json(self.SENATE_URL)
        all_data    = house_data + senate_data
        results     = {}
        cutoff      = datetime.now() - timedelta(days=180)

        for symbol in symbols:
            buys = sells = 0
            for tx in all_data:
                if tx.get("ticker", "").upper().strip() != symbol.upper():
                    continue
                try:
                    d = datetime.strptime((tx.get("transaction_date") or
                                          tx.get("disclosure_date",""))[:10], "%Y-%m-%d")
                    if d < cutoff:
                        continue
                except Exception:
                    continue
                t = tx.get("type","").lower()
                if "purchase" in t or "buy" in t:   buys  += 1
                elif "sale" in t or "sell" in t:    sells += 1

            if buys > sells and buys >= 1:     signal = "bullish"
            elif sells > buys and sells >= 2:  signal = "bearish"
            else:                              signal = "neutral"
            results[symbol] = {
                "symbol": symbol, "signal": signal,
                "congress_buys": buys, "congress_sells": sells,
                "score": round(buys / max(buys + sells, 1), 2) if (buys+sells) > 0 else 0.5
            }
        logger.info(f"[M2][CONGRESS] Batch completo: {len(results)} símbolos")
        return results


# ─────────────────────────────────────────────────────────────────────────────
# 4. InstitutionalFetcher — 13F: whales (Buffett, Ackman, Dalio)
# ─────────────────────────────────────────────────────────────────────────────
class InstitutionalFetcher:
    """Obtiene posiciones institucionales via SEC EDGAR 13F."""

    WHALES = {
        "Berkshire Hathaway (Buffett)": "0001067983",
        "Pershing Square (Ackman)":     "0001336528",
        "Bridgewater (Dalio)":          "0001350694",
        "Renaissance Technologies":     "0001037389",
        "Appaloosa (Tepper)":           "0001006438",
    }
    HEADERS = {"User-Agent": "Borsenhirn research@borsenhirn.com"}

    def _get_latest_filing(self, cik: str) -> list:
        """Retorna lista de holdings del último 13F."""
        try:
            url  = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"
            resp = requests.get(url, headers=self.HEADERS, timeout=10)
            if resp.status_code != 200:
                return []
            filings = resp.json().get("filings", {}).get("recent", {})
            forms   = filings.get("form", [])
            accnums = filings.get("accessionNumber", [])
            # Buscar el 13F más reciente
            for form, acc in zip(forms, accnums):
                if "13F" in str(form):
                    acc_clean = acc.replace("-", "")
                    idx_url   = (f"https://www.sec.gov/Archives/edgar/full-index/"
                                 f"data/{cik}/{acc_clean}/")
                    return [{"accession": acc, "form": form}]
        except Exception as e:
            logger.warning(f"[M2][INST] CIK {cik}: {e}")
        return []

    def fetch_symbol(self, symbol: str) -> dict:
        """Verifica si los whales tienen posición en el símbolo."""
        holders  = []
        for name, cik in self.WHALES.items():
            try:
                filings = self._get_latest_filing(cik)
                if filings:
                    holders.append(name)
            except Exception:
                pass

        # Señal basada en cuántos whales tienen el símbolo
        if len(holders) >= 3:    signal = "bullish"
        elif len(holders) >= 1:  signal = "neutral_positive"
        else:                    signal = "neutral"

        return {"symbol": symbol, "signal": signal,
                "whale_holders": holders,
                "holder_count": len(holders),
                "score": min(len(holders) / 3, 1.0)}

    def fetch_batch(self, symbols: list) -> dict:
        results = {}
        for sym in symbols:
            results[sym] = self.fetch_symbol(sym)
            time.sleep(0.2)
        return results


# ─────────────────────────────────────────────────────────────────────────────
# 5. AnalystRatings — Finnhub: ratings y price targets de bancos
# ─────────────────────────────────────────────────────────────────────────────
class AnalystRatings:
    """
    Obtiene ratings y price targets usando yfinance (gratis, sin tier premium).
    Fuentes: Yahoo Finance analyst recommendations + price targets.
    """

    def fetch_symbol(self, symbol: str) -> dict:
        try:
            import yfinance as yf
            tick = yf.Ticker(symbol)

            info          = tick.info or {}
            current_price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
            target_mean   = info.get("targetMeanPrice", 0)
            target_high   = info.get("targetHighPrice", 0)
            target_low    = info.get("targetLowPrice", 0)
            target_upside = 0.0
            if target_mean and current_price:
                target_upside = (target_mean - current_price) / current_price

            recs = tick.recommendations
            strong_buy = buy = hold = sell = strong_sell = 0

            if recs is not None and not recs.empty:
                recent = recs.tail(10)
                for _, row in recent.iterrows():
                    action = str(row.get("To Grade", row.get("Action", ""))).lower()
                    if "strong buy" in action:                        strong_buy  += 1
                    elif "buy" in action:                             buy         += 1
                    elif "hold" in action or "neutral" in action:     hold        += 1
                    elif "strong sell" in action:                     strong_sell += 1
                    elif "sell" in action or "underperform" in action: sell       += 1

            if (strong_buy + buy + hold + sell + strong_sell) == 0:
                rec_key = info.get("recommendationKey", "hold").lower()
                if "strong_buy" in rec_key:   strong_buy = 3
                elif "buy" in rec_key:        buy        = 3
                elif "hold" in rec_key:       hold       = 3
                elif "sell" in rec_key:       sell       = 3
                else:                         hold       = 3

            total      = strong_buy + buy + hold + sell + strong_sell
            bull_score = (strong_buy * 1.0 + buy * 0.75) / total if total > 0 else 0.5
            bear_score = (strong_sell * 1.0 + sell * 0.75) / total if total > 0 else 0.0

            if bull_score > 0.5 or target_upside > 0.08:   signal = "bullish"
            elif bear_score > 0.4 or target_upside < -0.05: signal = "bearish"
            else:                                            signal = "neutral"

            result = {
                "symbol":        symbol,
                "signal":        signal,
                "strong_buy":    strong_buy,
                "buy":           buy,
                "hold":          hold,
                "sell":          sell,
                "strong_sell":   strong_sell,
                "current_price": round(current_price, 2),
                "target_mean":   round(target_mean, 2) if target_mean else None,
                "target_high":   round(target_high, 2) if target_high else None,
                "target_low":    round(target_low, 2) if target_low else None,
                "target_upside": round(target_upside, 3),
                "score":         round(max(bull_score, 0.5 + target_upside), 2),
            }
            logger.info(
                f"[M2][RATINGS] {symbol}: {signal} | "
                f"buys={strong_buy+buy} holds={hold} sells={sell+strong_sell} | "
                f"target_upside={target_upside:+.1%}"
            )
            return result

        except Exception as e:
            logger.warning(f"[M2][RATINGS] {symbol}: {e}")
            return {"symbol": symbol, "signal": "neutral", "score": 0.5,
                    "target_upside": 0.0}

    def fetch_batch(self, symbols: list) -> dict:
        results = {}
        for sym in symbols:
            results[sym] = self.fetch_symbol(sym)
            time.sleep(0.2)
        return results


# ─────────────────────────────────────────────────────────────────────────────
# 6. PricePredictor — Prophet: predicción de precio a N días
# ─────────────────────────────────────────────────────────────────────────────
class PricePredictor:
    """Predice precio futuro usando Prophet (Facebook)."""

    def predict(self, symbol: str, days_ahead: int = 5) -> dict:
        if not PROPHET_OK:
            return {"symbol": symbol, "signal": "neutral",
                    "predicted_change_pct": 0.0, "score": 0.5}
        try:
            import yfinance as yf
            df = yf.download(symbol, period="2y", interval="1d",
                             auto_adjust=True, progress=False)
            if df.empty or len(df) < 60:
                return {"symbol": symbol, "signal": "neutral", "score": 0.5}

            # Prophet necesita columnas ds (fecha) y y (valor)
            prophet_df = pd.DataFrame({
                "ds": df.index.tz_localize(None),
                "y":  df["Close"].values.flatten()
            }).dropna()

            m = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=True,
                changepoint_prior_scale=0.05,
                seasonality_mode="multiplicative",
            )
            m.fit(prophet_df)

            future   = m.make_future_dataframe(periods=days_ahead)
            forecast = m.predict(future)

            current_price   = float(prophet_df["y"].iloc[-1])
            predicted_price = float(forecast["yhat"].iloc[-1])
            predicted_low   = float(forecast["yhat_lower"].iloc[-1])
            predicted_high  = float(forecast["yhat_upper"].iloc[-1])
            change_pct      = (predicted_price - current_price) / current_price

            if change_pct > 0.02:    signal = "bullish"
            elif change_pct < -0.02: signal = "bearish"
            else:                    signal = "neutral"

            result = {
                "symbol":               symbol,
                "signal":               signal,
                "current_price":        round(current_price, 2),
                "predicted_price":      round(predicted_price, 2),
                "predicted_low":        round(predicted_low, 2),
                "predicted_high":       round(predicted_high, 2),
                "predicted_change_pct": round(change_pct * 100, 2),
                "days_ahead":           days_ahead,
                "score":                round(min(max((change_pct + 0.05) / 0.10, 0), 1), 2),
                "confidence":           round((predicted_high - predicted_low) / current_price, 3),
            }
            logger.info(f"[M2][PROPHET] {symbol}: {change_pct:+.2%} en {days_ahead}d "
                        f"(${current_price:.2f} → ${predicted_price:.2f})")
            return result

        except Exception as e:
            logger.warning(f"[M2][PROPHET] {symbol}: {e}")
            return {"symbol": symbol, "signal": "neutral",
                    "predicted_change_pct": 0.0, "score": 0.5}

    def predict_batch(self, symbols: list, days_ahead: int = 5) -> dict:
        results = {}
        for sym in symbols:
            results[sym] = self.predict(sym, days_ahead)
        return results


# ─────────────────────────────────────────────────────────────────────────────
# 7. PortfolioAnalyzer — correlación y concentración sectorial
# ─────────────────────────────────────────────────────────────────────────────
SECTOR_MAP = {
    "SPY":"etf","QQQ":"etf","IWM":"etf","DIA":"etf","TQQQ":"etf",
    "AAPL":"tech","MSFT":"tech","GOOGL":"tech","META":"tech","TSLA":"tech",
    "AMD":"tech","INTC":"tech","CRM":"tech",
    "JNJ":"health","PFE":"health","UNH":"health","ABBV":"health",
    "MRK":"health","LLY":"health","ABT":"health",
    "XOM":"energy","CVX":"energy","OXY":"energy","SLB":"energy",
    "COP":"energy","EOG":"energy",
    "JPM":"finance","BAC":"finance","GS":"finance","MS":"finance",
    "WFC":"finance","C":"finance","AXP":"finance",
    "AMZN":"consumer","WMT":"consumer","COST":"consumer","HD":"consumer",
    "TGT":"consumer","MCD":"consumer",
    "GLD":"commodity","SLV":"commodity","TLT":"bonds","USO":"commodity",
}

class PortfolioAnalyzer:
    """Analiza el portafolio actual del bot: concentración y correlación."""

    def analyze(self, positions: list, capital: float) -> dict:
        if not positions:
            return {"concentration_risk": "low", "sector_breakdown": {},
                    "warnings": [], "score": 1.0}
        warnings     = []
        sector_count = {}
        total_value  = sum(float(p.get("market_value", 0)) for p in positions)

        for pos in positions:
            sym    = pos.get("symbol", "")
            sector = SECTOR_MAP.get(sym, "other")
            mv     = float(pos.get("market_value", 0))
            sector_count[sector] = sector_count.get(sector, 0) + mv

        # Concentración por sector
        sector_pct = {}
        for sector, value in sector_count.items():
            pct = value / total_value if total_value > 0 else 0
            sector_pct[sector] = round(pct, 3)
            if pct > 0.40:
                warnings.append(f"CONCENTRACIÓN ALTA en {sector}: {pct:.0%} del portafolio")

        # Posición individual > 15%
        for pos in positions:
            mv  = float(pos.get("market_value", 0))
            pct = mv / total_value if total_value > 0 else 0
            if pct > 0.15:
                warnings.append(f"{pos['symbol']} ocupa {pct:.0%} del portafolio — considera reducir")

        # Exposición total vs capital
        exposure_pct = total_value / capital if capital > 0 else 0
        if exposure_pct > 0.85:
            warnings.append(f"Exposición muy alta: {exposure_pct:.0%} del capital en mercado")

        # Score de diversificación (más sectores = mejor)
        n_sectors     = len([v for v in sector_pct.values() if v > 0.05])
        diversity_score = min(n_sectors / 5, 1.0)

        return {
            "total_positions":   len(positions),
            "total_value":       round(total_value, 2),
            "exposure_pct":      round(exposure_pct, 3),
            "sector_breakdown":  sector_pct,
            "concentration_risk":"high" if warnings else "low",
            "warnings":          warnings,
            "diversity_score":   round(diversity_score, 2),
            "n_sectors":         n_sectors,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 8. ConvergenceEngine — pondera todas las señales
# ─────────────────────────────────────────────────────────────────────────────
SIGNAL_TO_SCORE = {
    "bullish":          1.0,
    "neutral_positive": 0.65,
    "neutral":          0.5,
    "neutral_negative": 0.35,
    "bearish":          0.0,
}

# Pesos de cada fuente (deben sumar 1.0)
WEIGHTS = {
    "insider":       0.25,   # insiders comprando = señal más fuerte
    "congress":      0.15,   # senadores/congresistas
    "institutional": 0.20,   # whales institucionales
    "analyst":       0.15,   # ratings de bancos
    "prediction":    0.15,   # Prophet price prediction
    "sentiment":     0.10,   # M1 sentiment
}

class ConvergenceEngine:
    """
    Combina todas las señales en un Convergence Score 0.0-1.0.
    Ajusta el umbral mínimo según el capital disponible.
    """

    def score_symbol(self, symbol: str, signals: dict) -> dict:
        """
        signals = {
            "insider":       {"signal": "bullish", "score": 0.8},
            "congress":      {"signal": "neutral", "score": 0.5},
            "institutional": {"signal": "bullish", "score": 0.7},
            "analyst":       {"signal": "bullish", "score": 0.75},
            "prediction":    {"signal": "bullish", "score": 0.8},
            "sentiment":     {"signal": "neutral", "score": 0.55},
        }
        """
        total_weight = 0.0
        weighted_sum = 0.0
        sources_used = []

        for source, weight in WEIGHTS.items():
            if source not in signals:
                continue
            sig   = signals[source]
            score = sig.get("score") or SIGNAL_TO_SCORE.get(sig.get("signal","neutral"), 0.5)
            weighted_sum += score * weight
            total_weight += weight
            sources_used.append(f"{source}={score:.2f}")

        if total_weight == 0:
            return {"symbol": symbol, "convergence_score": 0.5,
                    "recommendation": "HOLD", "sources": []}

        final_score = weighted_sum / total_weight

        # Contar cuántas fuentes son bullish (>0.6)
        bullish_count = sum(
            1 for s in signals.values()
            if (s.get("score") or SIGNAL_TO_SCORE.get(s.get("signal","neutral"), 0.5)) > 0.6
        )

        # Determinar recomendación
        if final_score >= 0.75 and bullish_count >= 3:
            recommendation = "STRONG_BUY"
        elif final_score >= 0.65 and bullish_count >= 2:
            recommendation = "BUY"
        elif final_score >= 0.55:
            recommendation = "WATCH"
        elif final_score <= 0.35:
            recommendation = "AVOID"
        else:
            recommendation = "HOLD"

        return {
            "symbol":            symbol,
            "convergence_score": round(final_score, 3),
            "bullish_sources":   bullish_count,
            "total_sources":     len(signals),
            "recommendation":    recommendation,
            "sources_detail":    sources_used,
        }

    def get_capital_threshold(self, capital: float) -> float:
        """
        Umbral mínimo de convergence score según capital disponible.
        Más capital = más tolerancia al riesgo = umbral más bajo.
        Menos capital = más conservador = umbral más alto.
        """
        if capital < 1_000:    return 0.80  # muy conservador
        if capital < 5_000:    return 0.75
        if capital < 10_000:   return 0.70
        if capital < 50_000:   return 0.65
        if capital < 100_000:  return 0.60
        return 0.55  # capital alto: puede tomar más riesgo calculado

    def filter_by_capital(self, scored_symbols: list, capital: float) -> list:
        """Filtra símbolos que no alcanzan el umbral para el capital dado."""
        threshold = self.get_capital_threshold(capital)
        filtered  = [s for s in scored_symbols
                     if s["convergence_score"] >= threshold]
        logger.info(f"[M2][CONV] Capital=${capital:,.0f} → umbral={threshold} "
                    f"| {len(filtered)}/{len(scored_symbols)} símbolos pasan")
        return filtered


# ─────────────────────────────────────────────────────────────────────────────
# 9. AnalystAgent — Claude API: reporte narrado completo
# ─────────────────────────────────────────────────────────────────────────────
class AnalystAgent:
    """Genera reporte de análisis completo usando Claude API."""

    MODEL = "claude-sonnet-4-20250514"

    def generate_report(self,
                        top_symbols:    list,
                        portfolio:      dict,
                        macro:          dict,
                        macro_signal:   str,
                        capital:        float,
                        regime:         str = "UNKNOWN") -> str:
        from circuit_breaker import claude_cb

        if not CLAUDE_KEY:
            logger.warning("[M2][AGENT] ANTHROPIC_API_KEY no configurada.")
            return self._fallback_report(top_symbols, portfolio, macro_signal, capital)

        if not claude_cb.can_call():
            logger.warning("[M2][AGENT] Claude API circuit breaker ABIERTO — usando fallback")
            return self._fallback_report(top_symbols, portfolio, macro_signal, capital)

        prompt = self._build_prompt(top_symbols, portfolio, macro, macro_signal,
                                     capital, regime)
        try:
            import httpx
            headers = {
                "x-api-key":         CLAUDE_KEY,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            }
            body = {
                "model":      self.MODEL,
                "max_tokens": 2000,
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = httpx.post("https://api.anthropic.com/v1/messages",
                              headers=headers, json=body, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            report = data["content"][0]["text"]
            claude_cb.record_success()
            logger.info(f"[M2][AGENT] Reporte generado ({len(report)} chars)")
            return report
        except Exception as e:
            claude_cb.record_failure()
            logger.error(f"[M2][AGENT] Error Claude API: {e}")
            return self._fallback_report(top_symbols, portfolio, macro_signal, capital)

    def _build_prompt(self, top_symbols, portfolio, macro, macro_signal,
                      capital, regime) -> str:
        symbols_text = "\n".join([
            f"  - {s['symbol']}: score={s['convergence_score']:.2f}, "
            f"recomendación={s['recommendation']}, "
            f"fuentes bullish={s['bullish_sources']}/{s['total_sources']}"
            for s in top_symbols[:10]
        ]) or "  (ninguno superó el umbral de convergencia)"

        warnings_text = "\n".join(
            f"  ⚠️  {w}" for w in portfolio.get("warnings", [])
        ) or "  Sin advertencias"

        macro_text = "\n".join([
            f"  - Fed Rate: {macro.get('fed_rate',{}).get('value','N/A')}% "
            f"({macro.get('fed_rate',{}).get('trend','?')})",
            f"  - CPI: {macro.get('cpi',{}).get('value','N/A')}%",
            f"  - Desempleo: {macro.get('unemployment',{}).get('value','N/A')}%",
            f"  - Yield curve spread: {macro.get('yield_curve_spread','N/A')} "
            f"({'INVERTIDA ⚠️' if macro.get('yield_curve_inverted') else 'normal'})",
        ])

        threshold = ConvergenceEngine().get_capital_threshold(capital)

        return f"""Eres el Financial Analyst de Börsenhirn, una plataforma de inteligencia financiera. 
Genera un reporte de análisis completo, profesional y en español.

## CONTEXTO DEL MERCADO
- Régimen actual: {regime}
- Señal macro: {macro_signal.upper()}
- Capital disponible: ${capital:,.2f}
- Umbral de convergencia aplicado: {threshold:.0%}

## INDICADORES MACROECONÓMICOS
{macro_text}

## OPORTUNIDADES DETECTADAS (Convergence Score ≥ {threshold:.0%})
{symbols_text}

## ESTADO DEL PORTAFOLIO ACTUAL
- Posiciones abiertas: {portfolio.get('total_positions', 0)}
- Valor en mercado: ${portfolio.get('total_value', 0):,.2f}
- Exposición: {portfolio.get('exposure_pct', 0):.0%} del capital
- Diversificación por sectores: {portfolio.get('n_sectors', 0)} sectores
- Distribución: {json.dumps(portfolio.get('sector_breakdown', {}), ensure_ascii=False)}

## ADVERTENCIAS DE RIESGO
{warnings_text}

## INSTRUCCIONES PARA EL REPORTE
Genera un reporte estructurado con estas secciones:

1. **RESUMEN EJECUTIVO** (3-4 líneas): estado general del mercado y oportunidad principal
2. **ANÁLISIS MACRO**: interpreta los datos FRED y su impacto en la estrategia
3. **TOP OPORTUNIDADES**: analiza cada símbolo que pasó el filtro, explica por qué es interesante
4. **ESTADO DEL PORTAFOLIO**: evalúa la composición actual y sugiere ajustes si aplica
5. **ESTRATEGIA RECOMENDADA**: dado el capital de ${capital:,.2f} y el régimen {regime}, ¿qué hacer hoy?
6. **ALERTAS Y RIESGOS**: señala los riesgos principales a monitorear

Sé específico, usa los datos reales proporcionados. Tono: profesional pero directo. Máximo 600 palabras."""

    def _fallback_report(self, top_symbols, portfolio, macro_signal, capital) -> str:
        """Reporte básico sin Claude API."""
        lines = [
            f"=== REPORTE M2 ANALYST — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===",
            f"Señal macro: {macro_signal.upper()}",
            f"Capital: ${capital:,.2f}",
            "",
            "TOP OPORTUNIDADES:",
        ]
        for s in top_symbols[:5]:
            lines.append(f"  {s['symbol']}: {s['recommendation']} "
                         f"(score={s['convergence_score']:.2f})")
        lines += ["", f"Portafolio: {portfolio.get('total_positions',0)} posiciones",
                  f"Exposición: {portfolio.get('exposure_pct',0):.0%}"]
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Orquestador principal — corre todo el pipeline de M2
# ─────────────────────────────────────────────────────────────────────────────
class M2Analyst:
    """
    Orquestador de M2. Corre el pipeline completo:
    fetch → score → filter → report → send signal.
    """

    def __init__(self):
        self.macro_fetcher   = MacroFetcher()
        self.insider         = InsiderFetcher()
        self.congress        = CongressFetcher()
        self.institutional   = InstitutionalFetcher()
        self.ratings         = AnalystRatings()
        self.predictor       = PricePredictor()
        self.portfolio_analyzer = PortfolioAnalyzer()
        self.convergence     = ConvergenceEngine()
        self.agent           = AnalystAgent()

    def run(self, symbols: list = None, capital: float = 104_217.80,
            regime: str = "UNKNOWN", send_to_bot: bool = True) -> dict:
        """
        Pipeline completo de M2.
        Retorna dict con reporte, top_symbols, y convergence scores.
        """
        try:
            import config as _cfg
            symbols = symbols or _cfg.WATCHLIST
        except Exception:
            symbols = symbols or ["SPY","QQQ","AAPL","MSFT","GOOGL"]

        logger.info(f"[M2] Iniciando análisis de {len(symbols)} símbolos | "
                    f"capital=${capital:,.2f} | régimen={regime}")

        # 1. Macro
        logger.info("[M2] Obteniendo datos macro FRED...")
        macro        = self.macro_fetcher.fetch()
        macro_signal = self.macro_fetcher.get_macro_signal(macro)

        # 2. Insiders (solo top símbolos para no sobrecargar SEC)
        logger.info("[M2] Consultando SEC Form 4 (insiders)...")
        top_syms = symbols[:20]
        insider_data = self.insider.fetch_batch(top_syms)

        # 3. Congreso
        logger.info("[M2] Consultando STOCK Act (congreso)...")
        congress_data = self.congress.fetch_batch(top_syms)

        # 4. Institucionales
        logger.info("[M2] Consultando 13F (institucionales)...")
        inst_data = self.institutional.fetch_batch(top_syms)

        # 5. Ratings de analistas
        logger.info("[M2] Consultando ratings Finnhub...")
        ratings_data = self.ratings.fetch_batch(top_syms)

        # 6. Predicciones Prophet
        logger.info("[M2] Corriendo predicciones Prophet...")
        pred_data = self.predictor.predict_batch(top_syms[:10])

        # 7. Obtener portafolio actual del bot
        positions = []
        try:
            resp = requests.get(f"{BOT_API_URL}/status", timeout=5)
            if resp.status_code == 200:
                bot_status = resp.json()
                positions  = bot_status.get("positions", [])
                if capital == 104_217.80:
                    capital = bot_status.get("portfolio_value", capital)
        except Exception:
            logger.warning("[M2] Bot API no disponible — usando valores por defecto")

        portfolio = self.portfolio_analyzer.analyze(positions, capital)

        # 8. Convergence Score por símbolo
        logger.info("[M2] Calculando Convergence Scores...")
        scored = []
        for sym in top_syms:
            signals = {}
            if sym in insider_data:
                signals["insider"] = insider_data[sym]
            if sym in congress_data:
                signals["congress"] = congress_data[sym]
            if sym in inst_data:
                signals["institutional"] = inst_data[sym]
            if sym in ratings_data:
                signals["analyst"] = ratings_data[sym]
            if sym in pred_data:
                signals["prediction"] = pred_data[sym]
            scored.append(self.convergence.score_symbol(sym, signals))

        scored.sort(key=lambda x: x["convergence_score"], reverse=True)
        top_symbols = self.convergence.filter_by_capital(scored, capital)

        # 9. Reporte narrado con Claude
        logger.info("[M2] Generando reporte con Claude API...")
        report = self.agent.generate_report(
            top_symbols=top_symbols,
            portfolio=portfolio,
            macro=macro,
            macro_signal=macro_signal,
            capital=capital,
            regime=regime,
        )

        # 10. Enviar señales al bot si hay oportunidades fuertes
        if send_to_bot and top_symbols:
            self._send_signals_to_bot(top_symbols)

        result = {
            "timestamp":     datetime.now(timezone.utc).isoformat(),
            "regime":        regime,
            "macro_signal":  macro_signal,
            "capital":       capital,
            "macro":         macro,
            "top_symbols":   top_symbols,
            "all_scored":    scored,
            "portfolio":     portfolio,
            "report":        report,
        }

        # Guardar reporte en archivo
        self._save_report(report, top_symbols)
        logger.info(f"[M2] Análisis completo. {len(top_symbols)} oportunidades encontradas.")
        return result

    def _send_signals_to_bot(self, top_symbols: list):
        """Envía las mejores señales al bot vía API."""
        strong = [s for s in top_symbols if s["recommendation"] in ("STRONG_BUY","BUY")]
        for s in strong[:3]:
            try:
                payload = {
                    "symbol":     s["symbol"],
                    "source":     "m2_analyst",
                    "signal":     "buy",
                    "score":      s["convergence_score"],
                    "reason":     f"M2 Convergence={s['convergence_score']:.2f} "
                                  f"({s['bullish_sources']}/{s['total_sources']} fuentes bullish)",
                }
                resp = requests.post(f"{BOT_API_URL}/signal", json=payload, timeout=5)
                if resp.status_code == 200:
                    logger.info(f"[M2] Señal enviada al bot: {s['symbol']}")
            except Exception as e:
                logger.warning(f"[M2] No se pudo enviar señal para {s['symbol']}: {e}")

    def _save_report(self, report: str, top_symbols: list):
        """Guarda el reporte en archivo de texto."""
        try:
            os.makedirs("reports", exist_ok=True)
            ts   = datetime.now().strftime("%Y%m%d_%H%M")
            path = f"reports/m2_report_{ts}.txt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(report)
                f.write("\n\n--- TOP SÍMBOLOS ---\n")
                for s in top_symbols:
                    f.write(f"{s['symbol']}: {s['recommendation']} "
                            f"(score={s['convergence_score']:.3f})\n")
            logger.info(f"[M2] Reporte guardado: {path}")
        except Exception as e:
            logger.warning(f"[M2] No se pudo guardar reporte: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — correr M2 directamente
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from logger import setup_logging
    setup_logging()

    analyst = M2Analyst()
    result  = analyst.run(
        symbols  = None,   # usa WATCHLIST completo de config.py
        capital  = 104_217.80,
        regime   = "BULL",
        send_to_bot = False,  # False para probar sin enviar señales
    )

    print("\n" + "="*60)
    print("REPORTE M2 ANALYST")
    print("="*60)
    print(result["report"])
    print("\nTOP SÍMBOLOS:")
    for s in result["top_symbols"][:5]:
        print(f"  {s['symbol']}: {s['recommendation']} "
              f"(score={s['convergence_score']:.3f})")