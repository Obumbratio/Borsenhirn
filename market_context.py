"""
market_context.py - Agregador de informacion de mercado en tiempo real.

Fuentes integradas (todas con fallback si fallan):
  - VIX (yfinance)           : volatilidad/miedo del mercado, sin API key
  - Fear & Greed Index       : sentimiento 0-100, sin API key
  - Finnhub                  : noticias, earnings calendar (key en .env opcional)
  - Alpha Vantage            : noticias con sentimiento (key en .env opcional)
  - NewsAPI                  : noticias financieras generales (key en .env opcional)
  - FRED                     : tasas Fed, inflacion, desempleo (key en .env opcional)
  - Polygon.io               : flujo institucional, short interest (key en .env opcional)

Todo se consolida en get_full_context() que retorna un dict listo para usar.
"""

import os, logging, requests
from datetime import datetime, timedelta, timezone

import yfinance as yf
from circuit_breaker import yfinance_cb, finnhub_cb, alphavantage_cb, newsapi_cb, fred_cb, polygon_cb

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# KEYS (todas opcionales — el sistema funciona sin ellas)
# ══════════════════════════════════════════════════════════════
FINNHUB_KEY      = os.getenv("FINNHUB_API_KEY", "")
ALPHAVANTAGE_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
NEWSAPI_KEY      = os.getenv("NEWSAPI_KEY", "")
FRED_KEY         = os.getenv("FRED_API_KEY", "")
POLYGON_KEY      = os.getenv("POLYGON_API_KEY", "")


# ══════════════════════════════════════════════════════════════
# 1. VIX — VOLATILIDAD DEL MERCADO (sin key)
# ══════════════════════════════════════════════════════════════
def get_vix() -> dict:
    """
    Retorna el nivel actual del VIX y su interpretacion.
    VIX < 15  : mercado calmo, favorable para compras
    VIX 15-25 : volatilidad normal
    VIX 25-35 : tension, reducir posiciones
    VIX > 35  : panico, evitar compras nuevas
    """
    if not yfinance_cb.can_call():
        logger.warning("Circuit breaker yfinance abierto — omitiendo get_vix()")
        return {"value": None, "level": "unknown", "signal": "neutral", "summary": "VIX no disponible"}
    try:
        hist  = yf.Ticker("^VIX").history(period="5d")
        if hist.empty:
            return {"value": None, "level": "unknown", "signal": "neutral"}
        current = round(float(hist["Close"].iloc[-1]), 2)
        prev    = round(float(hist["Close"].iloc[-2]), 2) if len(hist) > 1 else current
        change  = round(current - prev, 2)

        if current < 15:
            level, signal = "muy_bajo", "comprar_agresivo"
        elif current < 20:
            level, signal = "bajo", "favorable"
        elif current < 25:
            level, signal = "normal", "neutral"
        elif current < 30:
            level, signal = "elevado", "precaucion"
        elif current < 35:
            level, signal = "alto", "reducir_posicion"
        else:
            level, signal = "panico", "evitar_compras"

        logger.info(f"VIX={current} ({level}) | cambio={change:+.2f}")
        yfinance_cb.record_success()
        return {
            "value":   current,
            "prev":    prev,
            "change":  change,
            "level":   level,
            "signal":  signal,
            "summary": f"VIX={current} ({level.replace('_',' ')})"
        }
    except Exception as e:
        logger.warning(f"VIX error: {e}")
        yfinance_cb.record_failure()
        return {"value": None, "level": "unknown", "signal": "neutral", "summary": "VIX no disponible"}


# ══════════════════════════════════════════════════════════════
# 2. FEAR & GREED INDEX (sin key)
# ══════════════════════════════════════════════════════════════
def get_fear_greed() -> dict:
    """
    Indice de miedo/codicia del mercado 0-100.
    0-25  : Miedo extremo (oportunidad de compra contrarian)
    25-45 : Miedo
    45-55 : Neutral
    55-75 : Codicia
    75-100: Codicia extrema (posible techo)
    """
    try:
        r    = requests.get("https://api.alternative.me/fng/?limit=2", timeout=6)
        data = r.json()["data"]
        val  = int(data[0]["value"])
        name = data[0]["value_classification"]
        prev_val = int(data[1]["value"]) if len(data) > 1 else val

        if val <= 25:
            signal = "comprar_contrarian"
        elif val <= 45:
            signal = "oportunidad"
        elif val <= 55:
            signal = "neutral"
        elif val <= 75:
            signal = "precaucion"
        else:
            signal = "evitar_compras"

        logger.info(f"Fear&Greed={val} ({name})")
        return {
            "value":   val,
            "prev":    prev_val,
            "name":    name,
            "signal":  signal,
            "summary": f"Fear&Greed={val}/100 ({name})"
        }
    except Exception as e:
        logger.warning(f"Fear&Greed error: {e}")
        return {"value": None, "name": "unknown", "signal": "neutral", "summary": "Fear&Greed no disponible"}


# ══════════════════════════════════════════════════════════════
# 3. NOTICIAS — FINNHUB (key opcional en .env)
# ══════════════════════════════════════════════════════════════
def get_news_finnhub(symbol: str, days: int = 3) -> list:
    """Noticias recientes del simbolo via Finnhub."""
    if not FINNHUB_KEY or FINNHUB_KEY in ("demo", ""):
        return []
    if not finnhub_cb.can_call():
        logger.warning("Circuit breaker Finnhub abierto — omitiendo get_news_finnhub()")
        return []
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        r = requests.get(
            "https://finnhub.io/api/v1/company-news",
            params={"symbol": symbol, "from": since, "to": today, "token": FINNHUB_KEY},
            timeout=8
        )
        items = r.json()
        if not isinstance(items, list):
            return []
        news = []
        for n in items[:8]:
            news.append({
                "title":   n.get("headline", "")[:120],
                "source":  n.get("source", "Finnhub"),
                "date":    datetime.fromtimestamp(n.get("datetime", 0)).strftime("%Y-%m-%d"),
                "summary": n.get("summary", "")[:200],
            })
        logger.info(f"Finnhub: {len(news)} noticias para {symbol}")
        finnhub_cb.record_success()
        return news
    except Exception as e:
        logger.warning(f"Finnhub noticias error: {e}")
        finnhub_cb.record_failure()
        return []


# ══════════════════════════════════════════════════════════════
# 4. NOTICIAS — ALPHA VANTAGE con sentimiento (key opcional)
# ══════════════════════════════════════════════════════════════
def get_news_alphavantage(symbol: str) -> list:
    """Noticias con score de sentimiento via Alpha Vantage."""
    if not ALPHAVANTAGE_KEY or ALPHAVANTAGE_KEY in ("demo", ""):
        return []
    if not alphavantage_cb.can_call():
        logger.warning("Circuit breaker AlphaVantage abierto — omitiendo get_news_alphavantage()")
        return []
    try:
        r = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "NEWS_SENTIMENT",
                "tickers":  symbol,
                "limit":    8,
                "apikey":   ALPHAVANTAGE_KEY,
            },
            timeout=10
        )
        data = r.json()
        if "feed" not in data:
            return []
        news = []
        for item in data["feed"][:8]:
            sentiment = item.get("overall_sentiment_label", "Neutral")
            score     = float(item.get("overall_sentiment_score", 0))
            news.append({
                "title":     item.get("title", "")[:120],
                "source":    item.get("source", "AlphaVantage"),
                "date":      item.get("time_published", "")[:8],
                "sentiment": sentiment,
                "score":     round(score, 3),
                "summary":   f"[{sentiment} {score:+.2f}] {item.get('summary','')[:150]}",
            })
        logger.info(f"AlphaVantage: {len(news)} noticias para {symbol}")
        alphavantage_cb.record_success()
        return news
    except Exception as e:
        logger.warning(f"AlphaVantage noticias error: {e}")
        alphavantage_cb.record_failure()
        return []


# ══════════════════════════════════════════════════════════════
# 5. NOTICIAS — NEWSAPI (key opcional)
# ══════════════════════════════════════════════════════════════
def get_news_newsapi(symbol: str) -> list:
    """Noticias financieras generales via NewsAPI."""
    if not NEWSAPI_KEY or NEWSAPI_KEY == "":
        return []
    if not newsapi_cb.can_call():
        logger.warning("Circuit breaker NewsAPI abierto — omitiendo get_news_newsapi()")
        return []
    try:
        query = f"{symbol} stock market"
        since = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        r = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q":        query,
                "from":     since,
                "language": "en",
                "sortBy":   "publishedAt",
                "pageSize": 8,
                "apiKey":   NEWSAPI_KEY,
            },
            timeout=8
        )
        data = r.json()
        if data.get("status") != "ok":
            return []
        news = []
        for a in data.get("articles", [])[:8]:
            news.append({
                "title":   a.get("title", "")[:120],
                "source":  a.get("source", {}).get("name", "NewsAPI"),
                "date":    a.get("publishedAt", "")[:10],
                "summary": a.get("description", "")[:200],
            })
        logger.info(f"NewsAPI: {len(news)} articulos para '{symbol}'")
        newsapi_cb.record_success()
        return news
    except Exception as e:
        logger.warning(f"NewsAPI error: {e}")
        newsapi_cb.record_failure()
        return []


# ══════════════════════════════════════════════════════════════
# 6. EARNINGS CALENDAR — FINNHUB (key opcional)
# ══════════════════════════════════════════════════════════════
def get_earnings_nearby(symbol: str, days_ahead: int = 5) -> dict:
    """
    Verifica si hay earnings del simbolo en los proximos N dias.
    Riesgo: no comprar 2 dias antes ni 1 dia despues de earnings.
    """
    if not FINNHUB_KEY or FINNHUB_KEY in ("demo", ""):
        return {"has_earnings": False, "date": None, "days_away": None}
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        end   = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        r = requests.get(
            "https://finnhub.io/api/v1/calendar/earnings",
            params={"from": today, "to": end, "symbol": symbol, "token": FINNHUB_KEY},
            timeout=8
        )
        data = r.json()
        earnings = data.get("earningsCalendar", [])
        if earnings:
            earn_date = earnings[0].get("date", "")
            days_away = (datetime.strptime(earn_date, "%Y-%m-%d") - datetime.now()).days
            logger.info(f"EARNINGS {symbol}: {earn_date} ({days_away} dias)")
            return {
                "has_earnings": True,
                "date":         earn_date,
                "days_away":    days_away,
                "eps_estimate": earnings[0].get("epsEstimate"),
                "summary":      f"Earnings en {days_away} dias ({earn_date})"
            }
        return {"has_earnings": False, "date": None, "days_away": None}
    except Exception as e:
        logger.warning(f"Earnings error: {e}")
        return {"has_earnings": False, "date": None, "days_away": None}


# ══════════════════════════════════════════════════════════════
# 7. FRED — INDICADORES ECONOMICOS (key opcional)
# ══════════════════════════════════════════════════════════════
def get_fred_data() -> dict:
    """
    Indicadores macro de la Reserva Federal:
    - DFF  : tasa de interes efectiva Fed Funds
    - CPIAUCSL: inflacion (CPI)
    - UNRATE  : desempleo
    """
    if not FRED_KEY or FRED_KEY == "":
        return {}
    if not fred_cb.can_call():
        logger.warning("Circuit breaker FRED abierto — omitiendo get_fred_data()")
        return {}
    result = {}
    series = {
        "fed_rate":    "DFF",
        "inflation":   "CPIAUCSL",
        "unemployment":"UNRATE",
    }
    for name, sid in series.items():
        try:
            r = requests.get(
                "https://api.stlouisfed.org/fred/series/observations",
                params={
                    "series_id":        sid,
                    "api_key":          FRED_KEY,
                    "file_type":        "json",
                    "sort_order":       "desc",
                    "limit":            2,
                    "observation_start":"2020-01-01",
                },
                timeout=8
            )
            obs = r.json().get("observations", [])
            if obs:
                val = obs[0].get("value", ".")
                result[name] = float(val) if val != "." else None
        except Exception as e:
            logger.warning(f"FRED {sid} error: {e}")
            fred_cb.record_failure()
    if result:
        logger.info(f"FRED: tasa={result.get('fed_rate')} | inflacion={result.get('inflation')} | desempleo={result.get('unemployment')}")
        fred_cb.record_success()
    return result


# ══════════════════════════════════════════════════════════════
# 8. POLYGON — FLUJO INSTITUCIONAL / SHORT INTEREST (key opcional)
# ══════════════════════════════════════════════════════════════
def get_polygon_data(symbol: str) -> dict:
    """Datos de Polygon: short interest, descripcion del activo."""
    if not POLYGON_KEY or POLYGON_KEY == "":
        return {}
    if not polygon_cb.can_call():
        logger.warning("Circuit breaker Polygon abierto — omitiendo get_polygon_data()")
        return {}
    try:
        r = requests.get(
            f"https://api.polygon.io/v3/reference/tickers/{symbol}",
            params={"apiKey": POLYGON_KEY},
            timeout=8
        )
        data = r.json().get("results", {})
        result = {
            "name":        data.get("name", symbol),
            "description": data.get("description", "")[:300],
            "market_cap":  data.get("market_cap"),
            "employees":   data.get("total_employees"),
        }
        logger.info(f"Polygon: {symbol} — {result['name']}")
        polygon_cb.record_success()
        return result
    except Exception as e:
        logger.warning(f"Polygon error: {e}")
        polygon_cb.record_failure()
        return {}


# ══════════════════════════════════════════════════════════════
# 9. DATOS EXTRA VIA YFINANCE (sin key)
# ══════════════════════════════════════════════════════════════
def get_yfinance_context(symbol: str) -> dict:
    """
    Indices de mercado via yfinance (.history funciona, .info fue bloqueado por Yahoo).
    Retorna SP500, NASDAQ, DOW y VXN con su cambio porcentual diario.
    """
    result  = {}
    indices = {}
    for ticker_sym, name in [("^GSPC", "SP500"), ("^IXIC", "NASDAQ"), ("^DJI", "DOW"), ("^VXN", "VXN")]:
        try:
            hist = yf.Ticker(ticker_sym).history(period="5d")
            if hist.empty or len(hist) < 2:
                continue
            closes = hist["Close"].dropna()
            if len(closes) < 2:
                continue
            curr = float(closes.iloc[-1])
            prev = float(closes.iloc[-2])
            if prev > 0:
                indices[name] = {
                    "value":  round(curr, 2),
                    "change": round((curr - prev) / prev * 100, 2),
                }
        except Exception:
            pass
    result["indices"] = indices
    if indices:
        idx_str = " | ".join([f"{k}={v['change']:+.2f}%" for k, v in indices.items()])
        logger.info(f"Indices: {idx_str}")
    return result


# ══════════════════════════════════════════════════════════════
# FUNCION PRINCIPAL — CONTEXTO COMPLETO
# ══════════════════════════════════════════════════════════════
def get_full_context(symbol: str = "SPY") -> dict:
    """
    Agrega toda la informacion de mercado disponible.
    Siempre retorna un dict (nunca lanza excepcion).
    Los campos que fallan quedan en None o [].
    """
    logger.info(f"Obteniendo contexto completo de mercado para {symbol}...")

    vix      = get_vix()
    fg       = get_fear_greed()
    earnings = get_earnings_nearby(symbol)
    fred     = get_fred_data()
    yf_ctx   = get_yfinance_context(symbol)
    polygon  = get_polygon_data(symbol)

    # Noticias: combina todas las fuentes disponibles
    news = []
    news += get_news_alphavantage(symbol)
    news += get_news_finnhub(symbol)
    news += get_news_newsapi(symbol)
    # Deduplicar por titulo
    seen, unique_news = set(), []
    for n in news:
        key = n.get("title", "")[:60]
        if key and key not in seen:
            seen.add(key)
            unique_news.append(n)

    # Sentimiento agregado de noticias AV
    av_scores = [n.get("score", 0) for n in unique_news if "score" in n]
    avg_sentiment = round(sum(av_scores) / len(av_scores), 3) if av_scores else None

    # Señal compuesta de mercado
    market_signal = _composite_signal(vix, fg, earnings, avg_sentiment)

    ctx = {
        "symbol":          symbol,
        "timestamp":       datetime.now(timezone.utc).isoformat(),
        "vix":             vix,
        "fear_greed":      fg,
        "earnings":        earnings,
        "fred":            fred,
        "yfinance":        yf_ctx,
        "polygon":         polygon,
        "news":            unique_news[:10],
        "news_count":      len(unique_news),
        "avg_sentiment":   avg_sentiment,
        "market_signal":   market_signal,
    }

    logger.info(
        f"Contexto listo | VIX={vix.get('value')} | "
        f"F&G={fg.get('value')} ({fg.get('name')}) | "
        f"Señal={market_signal} | "
        f"Noticias={len(unique_news)} | "
        f"Earnings={'SI' if earnings.get('has_earnings') else 'no'}"
    )
    return ctx


def _composite_signal(vix: dict, fg: dict, earnings: dict,
                      avg_sentiment: float = None) -> str:
    """
    Combina VIX + Fear&Greed + Earnings + Sentimiento noticias.
    Retorna: 'comprar_agresivo' | 'favorable' | 'neutral' | 'precaucion' | 'evitar_compras'
    """
    score = 0

    vix_val = vix.get("value")
    if vix_val is not None:
        if vix_val < 15:   score += 2
        elif vix_val < 20: score += 1
        elif vix_val < 25: score += 0
        elif vix_val < 30: score -= 1
        elif vix_val < 35: score -= 2
        else:              score -= 3

    fg_val = fg.get("value")
    if fg_val is not None:
        if fg_val <= 25:   score += 1   # miedo extremo = oportunidad contrarian
        elif fg_val <= 45: score += 0
        elif fg_val <= 55: score += 0
        elif fg_val <= 75: score -= 1
        else:              score -= 2

    # Earnings proximos = riesgo adicional
    if earnings.get("has_earnings") and (earnings.get("days_away") or 99) <= 2:
        score -= 2

    # Sentimiento de noticias (AlphaVantage, rango -1 a +1)
    if avg_sentiment is not None:
        if avg_sentiment >= 0.3:    score += 2   # muy positivo
        elif avg_sentiment >= 0.1:  score += 1   # positivo
        elif avg_sentiment <= -0.3: score -= 2   # muy negativo
        elif avg_sentiment <= -0.1: score -= 1   # negativo
        logger.info(f"Sentimiento noticias={avg_sentiment:+.3f} → ajuste score")

    if score >= 3:    return "comprar_agresivo"
    elif score >= 1:  return "favorable"
    elif score == 0:  return "neutral"
    elif score >= -1: return "precaucion"
    else:             return "evitar_compras"


def format_news_for_report(news: list) -> str:
    """Formatea noticias para incluir en reportes y prompts de IA."""
    if not news:
        return "Sin noticias disponibles."
    lines = []
    for n in news[:8]:
        sentiment_tag = ""
        if "sentiment" in n:
            sentiment_tag = f" [{n['sentiment']} {n.get('score', 0):+.2f}]"
        lines.append(f"• [{n.get('source','?')} {n.get('date','')}]{sentiment_tag} {n.get('title','')}")
        if n.get("summary"):
            lines.append(f"  {n['summary'][:120]}")
    return "\n".join(lines)


def format_context_summary(ctx: dict) -> str:
    """Resumen compacto del contexto para logs y alertas."""
    vix  = ctx.get("vix", {})
    fg   = ctx.get("fear_greed", {})
    earn = ctx.get("earnings", {})
    fred = ctx.get("fred", {})
    idx  = ctx.get("yfinance", {}).get("indices", {})

    lines = [
        f"VIX={vix.get('value','?')} ({vix.get('level','?')}) | "
        f"Fear&Greed={fg.get('value','?')}/100 ({fg.get('name','?')}) | "
        f"Señal={ctx.get('market_signal','?')}",
    ]
    if idx:
        idx_str = "  ".join([f"{k}={v.get('change',0):+.2f}%" for k, v in idx.items()])
        lines.append(f"Indices: {idx_str}")
    if fred:
        lines.append(
            f"Fed Rate={fred.get('fed_rate','?')}% | "
            f"Inflacion={fred.get('inflation','?')} | "
            f"Desempleo={fred.get('unemployment','?')}%"
        )
    if earn.get("has_earnings"):
        lines.append(f"EARNINGS en {earn.get('days_away')} dias ({earn.get('date')})")
    if ctx.get("news_count", 0) > 0:
        lines.append(f"Noticias disponibles: {ctx['news_count']}")
    return "\n".join(lines)
