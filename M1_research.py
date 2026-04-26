"""
m1_research.py — M1 Research Agent para Börsenhirn.

Tres agentes especializados que trabajan juntos:

  Agente 1 — NewsAgent:      agrega noticias de Finnhub + Alpha Vantage + NewsAPI
  Agente 2 — SentimentAgent: analiza sentimiento de mercado (VIX, Fear&Greed, social)
  Agente 3 — OrchestratorAgent: sintetiza todo con Claude API y genera señales

Uso:
    from m1_research import ResearchAgent

    agent = ResearchAgent()

    # Reporte completo de un símbolo
    report = agent.research_symbol("AAPL")
    print(report["summary"])           # resumen en lenguaje natural
    print(report["signal"])            # "bullish" / "bearish" / "neutral"
    print(report["confidence"])        # 0.0 a 1.0

    # Reporte del mercado general
    market = agent.research_market()
    print(market["summary"])
    print(market["top_opportunities"]) # símbolos con mejor contexto

    # Inyectar señales al bot automáticamente
    agent.inject_signals_to_bot(symbols=["AAPL", "MSFT", "XOM"])
"""

import os
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional
import requests

import config

logger = logging.getLogger(__name__)

# ── Configuración ─────────────────────────────────────────────────────────────

BOT_API_URL      = f"http://localhost:{getattr(config, 'API_PORT', 8000)}"
FINNHUB_BASE     = "https://finnhub.io/api/v1"
ALPHAVANTAGE_BASE= "https://www.alphavantage.co/query"
NEWSAPI_BASE     = "https://newsapi.org/v2"
ANTHROPIC_URL    = "https://api.anthropic.com/v1/messages"

# Mapeo de símbolos a sectores para noticias contextuales
SECTOR_MAP = {
    "SPY": "S&P 500 stock market",
    "QQQ": "NASDAQ technology stocks",
    "AAPL": "Apple technology",
    "MSFT": "Microsoft technology cloud",
    "GOOGL": "Google Alphabet technology",
    "META": "Meta Facebook social media",
    "TSLA": "Tesla electric vehicles",
    "AMD": "AMD semiconductors",
    "INTC": "Intel semiconductors",
    "XOM": "ExxonMobil oil energy",
    "CVX": "Chevron oil energy",
    "OXY": "Occidental Petroleum oil",
    "JPM": "JPMorgan Chase banking",
    "BAC": "Bank of America banking",
    "GS": "Goldman Sachs investment bank",
    "JNJ": "Johnson Johnson healthcare",
    "PFE": "Pfizer pharmaceutical",
    "GLD": "gold commodity",
    "TLT": "treasury bonds interest rates",
    "USO": "crude oil commodity",
}


# ── Agente 1: NewsAgent ───────────────────────────────────────────────────────

class NewsAgent:
    """
    Agrega noticias de múltiples fuentes para un símbolo o tema.
    """

    def __init__(self):
        self.finnhub_key    = getattr(config, "FINNHUB_API_KEY", "")
        self.alphav_key     = getattr(config, "ALPHAVANTAGE_API_KEY", "")
        self.newsapi_key    = getattr(config, "NEWSAPI_KEY", "")

    def get_finnhub_news(self, symbol: str, days_back: int = 2) -> list:
        """Obtiene noticias de Finnhub para un símbolo."""
        if not self.finnhub_key:
            return []
        try:
            end   = datetime.now(timezone.utc)
            start = end - timedelta(days=days_back)
            url   = f"{FINNHUB_BASE}/company-news"
            params = {
                "symbol": symbol,
                "from":   start.strftime("%Y-%m-%d"),
                "to":     end.strftime("%Y-%m-%d"),
                "token":  self.finnhub_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                news = resp.json()
                logger.info(f"[M1-News] Finnhub: {len(news)} noticias para {symbol}")
                return news[:10]  # máximo 10
        except Exception as e:
            logger.warning(f"[M1-News] Finnhub error: {e}")
        return []

    def get_alphavantage_news(self, symbol: str) -> list:
        """Obtiene noticias de Alpha Vantage."""
        if not self.alphav_key:
            return []
        try:
            params = {
                "function": "NEWS_SENTIMENT",
                "tickers":  symbol,
                "limit":    10,
                "apikey":   self.alphav_key,
            }
            resp = requests.get(ALPHAVANTAGE_BASE, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                feed = data.get("feed", [])
                logger.info(f"[M1-News] AlphaVantage: {len(feed)} noticias para {symbol}")
                return feed[:10]
        except Exception as e:
            logger.warning(f"[M1-News] AlphaVantage error: {e}")
        return []

    def get_newsapi_news(self, symbol: str) -> list:
        """Obtiene noticias generales de NewsAPI."""
        if not self.newsapi_key:
            return []
        try:
            query   = SECTOR_MAP.get(symbol, symbol)
            end     = datetime.now(timezone.utc)
            start   = end - timedelta(days=2)
            params  = {
                "q":        query,
                "from":     start.strftime("%Y-%m-%dT%H:%M:%S"),
                "sortBy":   "relevancy",
                "language": "en",
                "pageSize": 10,
                "apiKey":   self.newsapi_key,
            }
            resp = requests.get(f"{NEWSAPI_BASE}/everything", params=params, timeout=10)
            if resp.status_code == 200:
                articles = resp.json().get("articles", [])
                logger.info(f"[M1-News] NewsAPI: {len(articles)} noticias para {symbol}")
                return articles[:10]
        except Exception as e:
            logger.warning(f"[M1-News] NewsAPI error: {e}")
        return []

    def aggregate(self, symbol: str) -> dict:
        """
        Agrega noticias de todas las fuentes y extrae los titulares más relevantes.
        """
        finnhub_news  = self.get_finnhub_news(symbol)
        alphav_news   = self.get_alphavantage_news(symbol)
        newsapi_news  = self.get_newsapi_news(symbol)

        headlines = []

        # Finnhub
        for n in finnhub_news:
            if n.get("headline"):
                headlines.append({
                    "title":   n["headline"],
                    "source":  n.get("source", "Finnhub"),
                    "summary": n.get("summary", "")[:200],
                    "time":    n.get("datetime", 0),
                })

        # Alpha Vantage
        for n in alphav_news:
            if n.get("title"):
                sentiment = n.get("overall_sentiment_label", "neutral")
                headlines.append({
                    "title":     n["title"],
                    "source":    n.get("source", "AlphaVantage"),
                    "summary":   n.get("summary", "")[:200],
                    "sentiment": sentiment,
                    "time":      n.get("time_published", ""),
                })

        # NewsAPI
        for n in newsapi_news:
            if n.get("title"):
                headlines.append({
                    "title":   n["title"],
                    "source":  n.get("source", {}).get("name", "NewsAPI"),
                    "summary": n.get("description", "")[:200],
                    "time":    n.get("publishedAt", ""),
                })

        total = len(headlines)
        logger.info(f"[M1-News] {symbol}: {total} titulares agregados de {3} fuentes")

        return {
            "symbol":     symbol,
            "headlines":  headlines[:15],  # top 15
            "total":      total,
            "sources":    ["Finnhub", "AlphaVantage", "NewsAPI"],
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


# ── Agente 2: SentimentAgent ──────────────────────────────────────────────────

class SentimentAgent:
    """
    Analiza el sentimiento general del mercado usando múltiples indicadores.
    """

    def __init__(self):
        self.finnhub_key = getattr(config, "FINNHUB_API_KEY", "")

    def get_fear_greed(self) -> dict:
        """Obtiene el índice Fear & Greed de CNN."""
        try:
            url  = "https://fear-and-greed-index.p.rapidapi.com/v1/fgi"
            headers = {
                "x-rapidapi-host": "fear-and-greed-index.p.rapidapi.com",
                "x-rapidapi-key":  "demo",
            }
            # Fallback: usar el valor del market_context si está disponible
            return {"value": 25, "label": "Fear", "source": "estimate"}
        except Exception:
            return {"value": 50, "label": "Neutral", "source": "default"}

    def get_finnhub_sentiment(self, symbol: str) -> dict:
        """Obtiene el sentimiento social de Finnhub."""
        if not self.finnhub_key:
            return {}
        try:
            url    = f"{FINNHUB_BASE}/news-sentiment"
            params = {"symbol": symbol, "token": self.finnhub_key}
            resp   = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "buzz":             data.get("buzz", {}),
                    "sentiment":        data.get("sentiment", {}),
                    "company_news_score": data.get("companyNewsScore", 0),
                    "sector_avg_bullish": data.get("sectorAverageBullishPercent", 0),
                }
        except Exception as e:
            logger.warning(f"[M1-Sentiment] Finnhub sentiment error: {e}")
        return {}

    def get_insider_sentiment(self, symbol: str) -> dict:
        """Obtiene el sentimiento insider de Finnhub."""
        if not self.finnhub_key:
            return {}
        try:
            end   = datetime.now(timezone.utc)
            start = end - timedelta(days=90)
            url   = f"{FINNHUB_BASE}/stock/insider-sentiment"
            params = {
                "symbol": symbol,
                "from":   start.strftime("%Y-%m-%d"),
                "to":     end.strftime("%Y-%m-%d"),
                "token":  self.finnhub_key,
            }
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                if data:
                    latest = data[-1]
                    return {
                        "change":  latest.get("change", 0),
                        "mspr":    latest.get("mspr", 0),  # Monthly Share Purchase Ratio
                        "month":   latest.get("month", ""),
                    }
        except Exception as e:
            logger.warning(f"[M1-Sentiment] Insider error: {e}")
        return {}

    def analyze(self, symbol: str, vix: float = None, fg_value: int = None) -> dict:
        """
        Analiza el sentimiento completo para un símbolo.
        """
        social    = self.get_finnhub_sentiment(symbol)
        insider   = self.get_insider_sentiment(symbol)
        fear_greed = {"value": fg_value or 50, "label": "Unknown"}

        # Calcular score de sentimiento 0-1
        # 0 = muy bearish, 0.5 = neutral, 1 = muy bullish
        sentiment_score = 0.5

        # Ajustar por Fear & Greed
        fg = fear_greed.get("value", 50)
        if fg <= 20:
            sentiment_score -= 0.15   # miedo extremo = presión bajista
        elif fg >= 80:
            sentiment_score += 0.10   # codicia extrema = cuidado
        elif fg >= 55:
            sentiment_score += 0.10   # optimismo moderado

        # Ajustar por VIX
        if vix:
            if vix >= 35:
                sentiment_score -= 0.20
            elif vix >= 25:
                sentiment_score -= 0.10
            elif vix <= 15:
                sentiment_score += 0.10

        # Ajustar por sentimiento social (Finnhub)
        if social:
            buzz        = social.get("buzz", {})
            sentiment_d = social.get("sentiment", {})
            bullish_pct = float(sentiment_d.get("bullishPercent", 0.5))
            bearish_pct = float(sentiment_d.get("bearishPercent", 0.5))
            if bullish_pct > 0.6:
                sentiment_score += 0.10
            elif bearish_pct > 0.6:
                sentiment_score -= 0.10

        # Ajustar por insider
        if insider:
            mspr = float(insider.get("mspr", 0))
            if mspr > 0.1:
                sentiment_score += 0.05   # insiders comprando
            elif mspr < -0.1:
                sentiment_score -= 0.05   # insiders vendiendo

        sentiment_score = round(max(0.0, min(1.0, sentiment_score)), 3)

        # Etiqueta
        if sentiment_score >= 0.65:
            label = "bullish"
        elif sentiment_score <= 0.35:
            label = "bearish"
        else:
            label = "neutral"

        result = {
            "symbol":          symbol,
            "score":           sentiment_score,
            "label":           label,
            "fear_greed":      fear_greed,
            "vix":             vix,
            "social":          social,
            "insider":         insider,
            "analyzed_at":     datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            f"[M1-Sentiment] {symbol}: {label} score={sentiment_score:.2f} | "
            f"VIX={vix} | F&G={fg}"
        )
        return result


# ── Agente 3: OrchestratorAgent ───────────────────────────────────────────────

class OrchestratorAgent:
    """
    Sintetiza los outputs de NewsAgent y SentimentAgent usando Claude API.
    Genera un reporte en lenguaje natural y señales estructuradas.
    """

    def __init__(self):
        self.api_key = getattr(config, "ANTHROPIC_API_KEY", "")
        if not self.api_key:
            logger.warning("[M1-Orchestrator] ANTHROPIC_API_KEY no configurada.")

    def _call_claude(self, prompt: str, max_tokens: int = 800) -> str:
        """Llama a Claude API con el prompt dado."""
        from circuit_breaker import claude_cb

        if not self.api_key:
            return "Sin API key de Anthropic configurada."
        if not claude_cb.can_call():
            logger.warning("[M1-Orchestrator] Claude API circuit breaker ABIERTO — usando fallback")
            return ""
        try:
            headers = {
                "x-api-key":         self.api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            }
            body = {
                "model":      "claude-opus-4-6",
                "max_tokens": max_tokens,
                "messages":   [{"role": "user", "content": prompt}],
            }
            resp = requests.post(ANTHROPIC_URL, headers=headers,
                                 json=body, timeout=30)
            if resp.status_code == 200:
                claude_cb.record_success()
                return resp.json()["content"][0]["text"]
            else:
                logger.error(f"[M1-Orchestrator] Claude API error: {resp.status_code} {resp.text[:200]}")
                claude_cb.record_failure()
                return ""
        except Exception as e:
            logger.error(f"[M1-Orchestrator] Error: {e}")
            claude_cb.record_failure()
            return ""

    def synthesize_symbol(self, symbol: str, news: dict, sentiment: dict) -> dict:
        """
        Sintetiza noticias + sentimiento en un reporte con señal estructurada.
        """
        headlines_text = "\n".join([
            f"- {h['title']} ({h.get('source', 'Unknown')})"
            for h in news.get("headlines", [])[:8]
        ]) or "Sin noticias disponibles."

        prompt = f"""Eres un analista financiero experto. Analiza el siguiente contexto para {symbol} y responde ÚNICAMENTE en JSON válido sin texto adicional.

NOTICIAS RECIENTES ({news.get('total', 0)} artículos):
{headlines_text}

SENTIMIENTO DE MERCADO:
- Score de sentimiento: {sentiment.get('score', 0.5)} (0=bearish, 1=bullish)
- Etiqueta: {sentiment.get('label', 'neutral')}
- VIX actual: {sentiment.get('vix', 'N/A')}
- Fear & Greed: {sentiment.get('fear_greed', {}).get('value', 'N/A')}/100

Responde SOLO con este JSON (sin markdown, sin texto extra):
{{
  "signal": "bullish" o "bearish" o "neutral",
  "confidence": número entre 0.0 y 1.0,
  "summary": "resumen en 2-3 oraciones en español",
  "key_factors": ["factor1", "factor2", "factor3"],
  "risks": ["riesgo1", "riesgo2"],
  "recommendation": "COMPRAR" o "ESPERAR" o "EVITAR",
  "time_horizon": "corto" o "medio" o "largo"
}}"""

        raw = self._call_claude(prompt, max_tokens=500)

        # Parsear JSON
        try:
            if not raw:
                raise ValueError("Claude API no disponible")
            # Limpiar posibles backticks
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            result = json.loads(clean.strip())
        except Exception as e:
            logger.warning(f"[M1-Orchestrator] JSON parse error o API caída: {e} — usando fallback con datos disponibles")
            result = {
                "signal":         sentiment.get("label", "neutral"),
                "confidence":     sentiment.get("score", 0.5),
                "summary":        f"Análisis de {symbol} (sin IA): sentimiento {sentiment.get('label', 'neutral')}, "
                                  f"{news.get('total', 0)} noticias encontradas.",
                "key_factors":    [f"Sentimiento: {sentiment.get('label', 'neutral')}",
                                   f"VIX: {sentiment.get('vix', 'N/A')}",
                                   f"Noticias: {news.get('total', 0)} artículos"],
                "risks":          ["Volatilidad de mercado", "Análisis sin IA — datos limitados"],
                "recommendation": "ESPERAR",
                "time_horizon":   "corto",
            }

        result["symbol"]      = symbol
        result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        result["news_count"]  = news.get("total", 0)

        logger.info(
            f"[M1-Orchestrator] {symbol}: {result['signal']} "
            f"conf={result.get('confidence', 0):.2f} → {result.get('recommendation', 'N/A')}"
        )
        return result

    def synthesize_market(self, market_data: dict) -> dict:
        """Genera un reporte general del mercado."""
        prompt = f"""Eres un analista financiero experto. Analiza el estado actual del mercado y responde ÚNICAMENTE en JSON válido.

DATOS DEL MERCADO:
- VIX: {market_data.get('vix', 'N/A')}
- Fear & Greed: {market_data.get('fear_greed', 'N/A')}/100
- Régimen detectado: {market_data.get('regime', 'N/A')}
- SP500 cambio: {market_data.get('sp500_change', 'N/A')}%
- NASDAQ cambio: {market_data.get('nasdaq_change', 'N/A')}%
- Sectores alcistas: {market_data.get('bull_sectors', [])}
- Sectores bajistas: {market_data.get('bear_sectors', [])}

Responde SOLO con este JSON:
{{
  "market_signal": "risk_on" o "risk_off" o "neutral",
  "confidence": número entre 0.0 y 1.0,
  "summary": "resumen del mercado en 2-3 oraciones en español",
  "top_sectors": ["sector1", "sector2"],
  "avoid_sectors": ["sector1", "sector2"],
  "key_risks": ["riesgo1", "riesgo2"],
  "strategy": "descripción de estrategia recomendada en 1 oración"
}}"""

        raw    = self._call_claude(prompt, max_tokens=400)
        try:
            if not raw:
                raise ValueError("Claude API no disponible")
            clean = raw.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"):
                    clean = clean[4:]
            result = json.loads(clean.strip())
        except Exception:
            logger.warning("[M1-Orchestrator] Fallback mercado — sin Claude API")
            result = {
                "market_signal": "neutral",
                "confidence":    0.5,
                "summary":       f"Mercado sin análisis IA. VIX={market_data.get('vix','N/A')}, "
                                 f"régimen={market_data.get('regime','N/A')}.",
                "top_sectors":   [],
                "avoid_sectors": [],
                "key_risks":     ["Volatilidad", "Análisis sin IA — datos limitados"],
                "strategy":      "Mantener posiciones defensivas hasta restaurar análisis completo.",
            }

        result["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        return result


# ── ResearchAgent — interfaz principal ───────────────────────────────────────

class ResearchAgent:
    """
    Interfaz principal de M1. Orquesta los tres agentes.
    """

    def __init__(self):
        self.news_agent      = NewsAgent()
        self.sentiment_agent = SentimentAgent()
        self.orchestrator    = OrchestratorAgent()
        logger.info("[M1] Research Agent inicializado.")

    def research_symbol(self, symbol: str,
                        vix: float = None,
                        fg_value: int = None) -> dict:
        """
        Genera un reporte completo para un símbolo.
        """
        logger.info(f"[M1] Investigando {symbol}...")

        # Agente 1 — Noticias
        news = self.news_agent.aggregate(symbol)

        # Agente 2 — Sentimiento
        sentiment = self.sentiment_agent.analyze(symbol, vix=vix, fg_value=fg_value)

        # Agente 3 — Síntesis LLM
        report = self.orchestrator.synthesize_symbol(symbol, news, sentiment)

        # Combinar todo
        report["news"]      = news
        report["sentiment"] = sentiment

        return report

    def research_market(self, vix: float = None,
                        fg_value: int = None,
                        regime: str = None) -> dict:
        """
        Genera un reporte del estado general del mercado.
        """
        logger.info("[M1] Analizando mercado general...")

        market_data = {
            "vix":          vix or 20,
            "fear_greed":   fg_value or 50,
            "regime":       regime or "UNKNOWN",
            "sp500_change": None,
            "nasdaq_change": None,
            "bull_sectors": [],
            "bear_sectors": [],
        }

        report = self.orchestrator.synthesize_market(market_data)
        report["market_data"] = market_data
        return report

    def inject_signals_to_bot(self, symbols: list,
                               vix: float = None,
                               fg_value: int = None) -> dict:
        """
        Investiga símbolos e inyecta señales al bot vía API.
        Retorna resumen de señales inyectadas.
        """
        injected = []
        skipped  = []

        for symbol in symbols:
            try:
                report = self.research_symbol(symbol, vix=vix, fg_value=fg_value)
                signal = report.get("signal", "neutral")
                conf   = float(report.get("confidence", 0.5))

                # Solo inyectar si la señal es clara (no neutral con baja confianza)
                if signal == "neutral" and conf < 0.6:
                    skipped.append(symbol)
                    continue

                # Mapear señal de M1 a acción del bot
                action = "buy" if signal == "bullish" else "sell" if signal == "bearish" else "hold"

                payload = {
                    "symbol":            symbol,
                    "source":            "M1",
                    "action":            action,
                    "confidence":        conf,
                    "reason":            report.get("summary", "")[:200],
                    "expires_in_cycles": 3,
                }

                resp = requests.post(
                    f"{BOT_API_URL}/signal",
                    json=payload,
                    timeout=5,
                )
                if resp.status_code == 200:
                    injected.append({"symbol": symbol, "action": action, "confidence": conf})
                    logger.info(f"[M1] Señal inyectada: {symbol} {action} conf={conf:.2f}")
                else:
                    logger.warning(f"[M1] Error inyectando señal para {symbol}: {resp.status_code}")
                    skipped.append(symbol)

                time.sleep(0.5)  # rate limiting

            except Exception as e:
                logger.error(f"[M1] Error procesando {symbol}: {e}")
                skipped.append(symbol)

        result = {
            "injected": injected,
            "skipped":  skipped,
            "total":    len(injected),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        logger.info(f"[M1] Señales inyectadas: {len(injected)} | Saltadas: {len(skipped)}")
        return result

    def daily_report(self, watchlist: list = None,
                     vix: float = None,
                     fg_value: int = None,
                     regime: str = None) -> dict:
        """
        Genera el reporte diario completo — mercado + top símbolos.
        Diseñado para correrse una vez al día al abrir el mercado.
        """
        if watchlist is None:
            watchlist = config.WATCHLIST[:10]  # top 10 por defecto

        logger.info(f"[M1] Generando reporte diario para {len(watchlist)} símbolos...")

        # Reporte de mercado general
        market_report = self.research_market(vix=vix, fg_value=fg_value, regime=regime)

        # Reportes por símbolo (limitado para no exceder rate limits)
        symbol_reports = {}
        for symbol in watchlist[:5]:  # máximo 5 en reporte diario
            try:
                symbol_reports[symbol] = self.research_symbol(
                    symbol, vix=vix, fg_value=fg_value
                )
                time.sleep(1)  # respetar rate limits
            except Exception as e:
                logger.error(f"[M1] Error en reporte de {symbol}: {e}")

        # Clasificar por señal
        bullish_symbols = [s for s, r in symbol_reports.items() if r.get("signal") == "bullish"]
        bearish_symbols = [s for s, r in symbol_reports.items() if r.get("signal") == "bearish"]
        neutral_symbols = [s for s, r in symbol_reports.items() if r.get("signal") == "neutral"]

        report = {
            "date":             datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "market":           market_report,
            "symbols":          symbol_reports,
            "bullish_symbols":  bullish_symbols,
            "bearish_symbols":  bearish_symbols,
            "neutral_symbols":  neutral_symbols,
            "generated_at":     datetime.now(timezone.utc).isoformat(),
        }

        logger.info(
            f"[M1] Reporte diario completo | "
            f"Mercado: {market_report.get('market_signal')} | "
            f"Bullish: {bullish_symbols} | Bearish: {bearish_symbols}"
        )
        return report


# ── CLI para testing ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)-8s | %(message)s")

    p = argparse.ArgumentParser(description="M1 Research Agent")
    p.add_argument("--symbol",  type=str, help="Investigar un símbolo (ej: AAPL)")
    p.add_argument("--market",  action="store_true", help="Reporte del mercado general")
    p.add_argument("--daily",   action="store_true", help="Reporte diario completo")
    p.add_argument("--inject",  type=str, help="Inyectar señales al bot (ej: AAPL,MSFT,XOM)")
    p.add_argument("--vix",     type=float, default=None)
    p.add_argument("--fg",      type=int,   default=None)
    a = p.parse_args()

    agent = ResearchAgent()

    if a.symbol:
        print(f"\n=== INVESTIGANDO {a.symbol.upper()} ===")
        report = agent.research_symbol(a.symbol.upper(), vix=a.vix, fg_value=a.fg)
        print(f"\n  Señal:          {report.get('signal', 'N/A').upper()}")
        print(f"  Confianza:      {report.get('confidence', 0):.2f}")
        print(f"  Recomendación:  {report.get('recommendation', 'N/A')}")
        print(f"\n  Resumen:")
        print(f"    {report.get('summary', 'N/A')}")
        print(f"\n  Factores clave:")
        for f in report.get("key_factors", []):
            print(f"    • {f}")
        print(f"\n  Riesgos:")
        for r in report.get("risks", []):
            print(f"    ⚠ {r}")
        print(f"\n  Noticias: {report.get('news_count', 0)} artículos encontrados")

    elif a.market:
        print("\n=== REPORTE DE MERCADO ===")
        report = agent.research_market(vix=a.vix, fg_value=a.fg)
        print(f"\n  Señal:          {report.get('market_signal', 'N/A').upper()}")
        print(f"  Confianza:      {report.get('confidence', 0):.2f}")
        print(f"\n  Resumen:")
        print(f"    {report.get('summary', 'N/A')}")
        print(f"\n  Sectores top:  {report.get('top_sectors', [])}")
        print(f"  Evitar:        {report.get('avoid_sectors', [])}")
        print(f"\n  Estrategia: {report.get('strategy', 'N/A')}")

    elif a.daily:
        print("\n=== REPORTE DIARIO ===")
        report = agent.daily_report(vix=a.vix, fg_value=a.fg)
        print(f"\n  Fecha: {report['date']}")
        print(f"  Mercado: {report['market'].get('market_signal', 'N/A')}")
        print(f"  Bullish: {report['bullish_symbols']}")
        print(f"  Bearish: {report['bearish_symbols']}")
        print(f"  Neutral: {report['neutral_symbols']}")

    elif a.inject:
        symbols = [s.strip().upper() for s in a.inject.split(",")]
        print(f"\n=== INYECTANDO SEÑALES: {symbols} ===")
        result = agent.inject_signals_to_bot(symbols, vix=a.vix, fg_value=a.fg)
        print(f"\n  Inyectadas: {result['total']}")
        for s in result["injected"]:
            print(f"    ✅ {s['symbol']} {s['action']} conf={s['confidence']:.2f}")
        if result["skipped"]:
            print(f"  Saltadas: {result['skipped']}")

    else:
        print("\nUso:")
        print("  python m1_research.py --symbol AAPL")
        print("  python m1_research.py --symbol AAPL --vix 28 --fg 15")
        print("  python m1_research.py --market --vix 28 --fg 15")
        print("  python m1_research.py --daily")
        print("  python m1_research.py --inject AAPL,MSFT,XOM")