"""
m4_whale.py — Whale Tracker Module para Börsenhirn
====================================================
Monitorea posiciones institucionales via SEC EDGAR 13F.
Detecta movimientos nuevos, evalúa vigencia con contexto actual,
adapta estrategias al capital disponible, y genera señales para el bot.

Componentes:
  1. SECFilingFetcher    — descarga y parsea 13F de SEC EDGAR
  2. WhalePositionTracker — detecta cambios vs trimestre anterior
  3. StrategyValidator   — evalúa si la estrategia sigue vigente hoy
  4. CopyStrategyEngine  — adapta al capital disponible
  5. WhaleAgent          — Claude API: reporte narrado completo
  6. M4WhaleTracker      — orquestador principal
"""

import os, logging, time, json, requests
from datetime import datetime, timezone, timedelta
from typing import Optional
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from bs4 import BeautifulSoup
    BS4_OK = True
except ImportError:
    BS4_OK = False
    logger.warning("[M4] beautifulsoup4 no instalado.")

try:
    import yfinance as yf
    YF_OK = True
except ImportError:
    YF_OK = False

try:
    import config as _cfg
    CLAUDE_KEY  = os.getenv("ANTHROPIC_API_KEY", "")
    BOT_API_URL = os.getenv("BOT_API_URL", "http://localhost:8000")
except Exception:
    CLAUDE_KEY  = ""
    BOT_API_URL = "http://localhost:8000"

SEC_HEADERS = {"User-Agent": "Borsenhirn research@borsenhirn.com"}

# ─────────────────────────────────────────────────────────────────────────────
# REEMPLAZA el diccionario WHALES en m4_whale.py con este
# 47 whales en total — cobertura completa del smart money
# ─────────────────────────────────────────────────────────────────────────────

WHALES = {
    # ── LEGENDS — Value / Macro clásicos (los originales) ────────────────────
    "Berkshire Hathaway (Buffett)": "0001067983",
    "Pershing Square (Ackman)": "0001336528",
    "Bridgewater Associates (Dalio)": "0001350694",
    "Renaissance Technologies": "0001037389",
    "Appaloosa (Tepper)": "0001006438",
    "Duquesne (Druckenmiller)": "0001536411",
    "Baupost Group (Klarman)": "0000886158",
    "Third Point (Loeb)": "0001040273",
    "Viking Global": "0001103804",
    "Coatue Management": "0001336545",
    "Tiger Global": "0001167483",
    "D1 Capital Partners": "0001795028",

    # ── INSTITUCIONALES MASIVOS — mueven el mercado entero ───────────────────
    "BlackRock": "0001364742",
    "Vanguard Group": "0000102909",
    "State Street Global Advisors": "0000093751",
    "Fidelity (FMR)": "0000315066",
    "T. Rowe Price": "0001113169",
    "Capital Group": "0000813672",

    # ── MACRO + ACTIVIST ─────────────────────────────────────────────────────
    "Soros Fund Management": "0001029160",
    "Elliott Management (Singer)": "0000880562",
    "Starboard Value": "0001517767",
    "ValueAct Capital": "0001173334",
    "Jana Partners": "0001159159",
    "Icahn Associates (Icahn)": "0000813762",

    # ── QUANT / MULTI-STRATEGY ───────────────────────────────────────────────
    "Point72 (Cohen)": "0001596662",
    "Citadel Advisors (Griffin)": "0001423298",
    "Two Sigma Investments": "0001442145",
    "DE Shaw": "0001009672",
    "AQR Capital Management": "0001167557",
    "Millennium Management": "0001273931",
    "Balyasny Asset Management": "0001418819",

    # ── TECH + GROWTH FOCUS ──────────────────────────────────────────────────
    "Lone Pine Capital": "0001060349",
    "Sequoia Fund": "0000089180",
    "Greenlight Capital (Einhorn)": "0001079114",
    "Maverick Capital": "0001024491",
    "Matrix Capital": "0001067983",
    "Whale Rock Capital": "0001754170",

    # ── BANCOS — Divisiones de gestión de patrimonio ─────────────────────────
    # (reportan su portafolio propio + managed accounts via 13F)
    "Goldman Sachs Asset Mgmt": "0000886982",
    "JPMorgan Asset Management": "0000019617",
    "Morgan Stanley Investment Mgmt": "0000895421",
    "Bank of America / Merrill Lynch": "0000070858",
    "Wells Fargo Asset Management": "0000072971",
    "Citigroup / Smith Barney": "0000831001",
    "UBS Asset Management": "0001030043",
    "Deutsche Bank Asset Mgmt": "0001060349",
    "Credit Suisse Asset Mgmt": "0000884905",

    # ── SOVEREIGN WEALTH / PENSIONES ─────────────────────────────────────────
    # (algunos reportan 13F si tienen operaciones en EEUU)
    "Norway Sovereign Wealth (Norges)": "0001341439",
    "Teacher Retirement Texas": "0001067294",
    "CalPERS (California Pension)": "0000826644",
    "Ontario Teachers Pension": "0001099590",
}


# ─────────────────────────────────────────────────────────────────────────────
# 1. SECFilingFetcher — descarga y parsea 13F de SEC EDGAR
# ─────────────────────────────────────────────────────────────────────────────
class SECFilingFetcher:
    """Descarga el último 13F de un whale y extrae sus posiciones."""

    BASE = "https://data.sec.gov"

    def get_latest_13f_accession(self, cik: str) -> Optional[str]:
        """Retorna el accession number del 13F más reciente."""
        try:
            url  = f"{self.BASE}/submissions/CIK{cik.zfill(10)}.json"
            resp = requests.get(url, headers=SEC_HEADERS, timeout=15)
            if resp.status_code != 200:
                return None
            data     = resp.json()
            filings  = data.get("filings", {}).get("recent", {})
            forms    = filings.get("form", [])
            accnums  = filings.get("accessionNumber", [])
            dates    = filings.get("filingDate", [])

            for form, acc, date in zip(forms, accnums, dates):
                if "13F-HR" in str(form):
                    logger.info(f"[M4][SEC] 13F encontrado: {acc} ({date})")
                    return acc, date
        except Exception as e:
            logger.warning(f"[M4][SEC] CIK {cik}: {e}")
        return None, None

    def get_holdings(self, cik: str, accession: str) -> list:
        """
        Descarga y parsea el XML de holdings del 13F.
        Retorna lista de dicts: {symbol, shares, value, holding_type}
        """
        holdings = []
        try:
            acc_clean = accession.replace("-", "")
            # Buscar el archivo de holdings en el índice
            idx_url = (f"https://www.sec.gov/cgi-bin/browse-edgar?"
                       f"action=getcompany&CIK={cik}&type=13F-HR"
                       f"&dateb=&owner=include&count=1&search_text=")
            # Construir URL directa al filing
            filing_url = (f"https://www.sec.gov/Archives/edgar/data/"
                          f"{int(cik)}/{acc_clean}/")
            resp = requests.get(filing_url, headers=SEC_HEADERS, timeout=15)
            if resp.status_code != 200:
                return holdings

            if BS4_OK:
                soup  = BeautifulSoup(resp.text, "html.parser")
                links = soup.find_all("a", href=True)
                xml_url = None
                for link in links:
                    href = link["href"]
                    if ("infotable" in href.lower() or
                        "13fhr" in href.lower() or
                        href.endswith(".xml")):
                        xml_url = f"https://www.sec.gov{href}"
                        break

                if xml_url:
                    holdings = self._parse_xml_holdings(xml_url)

        except Exception as e:
            logger.warning(f"[M4][SEC] Holdings {cik}/{accession}: {e}")
        return holdings

    def _parse_xml_holdings(self, xml_url: str) -> list:
        """Parsea el XML de infotable del 13F."""
        holdings = []
        try:
            resp = requests.get(xml_url, headers=SEC_HEADERS, timeout=20)
            if resp.status_code != 200:
                return holdings

            if BS4_OK:
                soup = BeautifulSoup(resp.content, "xml")
                # Buscar entries de infotable
                entries = soup.find_all("infoTable") or soup.find_all("ns1:infoTable")
                for entry in entries:
                    try:
                        # Extraer campos — pueden tener namespace o no
                        name     = (entry.find("nameOfIssuer") or
                                    entry.find("ns1:nameOfIssuer"))
                        shares   = (entry.find("sshPrnamt") or
                                    entry.find("ns1:sshPrnamt"))
                        value    = (entry.find("value") or
                                    entry.find("ns1:value"))
                        cusip    = (entry.find("cusip") or
                                    entry.find("ns1:cusip"))
                        h_type   = (entry.find("investmentDiscretion") or
                                    entry.find("ns1:investmentDiscretion"))

                        if name and shares and value:
                            holdings.append({
                                "name":    name.text.strip(),
                                "shares":  int(shares.text.replace(",","").strip()),
                                "value":   int(value.text.replace(",","").strip()) * 1000,
                                "cusip":   cusip.text.strip() if cusip else "",
                                "type":    h_type.text.strip() if h_type else "SOLE",
                            })
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"[M4][XML] {xml_url}: {e}")
        return holdings

    def resolve_symbols(self, holdings: list) -> list:
        """
        Intenta resolver CUSIP → ticker usando yfinance.
        Para holdings que no tienen ticker conocido, usa el nombre.
        """
        # Mapa de nombres comunes → ticker (evita llamadas innecesarias)
        NAME_TO_TICKER = {
            "APPLE": "AAPL", "MICROSOFT": "MSFT", "AMAZON": "AMZN",
            "ALPHABET": "GOOGL", "GOOGLE": "GOOGL", "META": "META",
            "TESLA": "TSLA", "NVIDIA": "NVDA", "BERKSHIRE": "BRK.B",
            "JPMORGAN": "JPM", "BANK OF AMERICA": "BAC", "WELLS FARGO": "WFC",
            "EXXON": "XOM", "CHEVRON": "CVX", "OCCIDENTAL": "OXY",
            "UNITEDHEALTH": "UNH", "JOHNSON": "JNJ", "PFIZER": "PFE",
            "SALESFORCE": "CRM", "ADVANCED MICRO": "AMD", "INTEL": "INTC",
            "COSTCO": "COST", "WALMART": "WMT", "HOME DEPOT": "HD",
            "MCDONALDS": "MCD", "AMERICAN EXPRESS": "AXP",
            "GOLDMAN": "GS", "MORGAN STANLEY": "MS", "CITIGROUP": "C",
            "ELI LILLY": "LLY", "ABBVIE": "ABBV", "MERCK": "MRK",
            "ABBOTT": "ABT", "GOLD": "GLD",
        }
        resolved = []
        for h in holdings:
            ticker = None
            name_upper = h["name"].upper()
            for key, sym in NAME_TO_TICKER.items():
                if key in name_upper:
                    ticker = sym
                    break
            if ticker:
                h["symbol"] = ticker
                resolved.append(h)
            else:
                # Guardar igualmente con símbolo None para análisis parcial
                h["symbol"] = None
                resolved.append(h)
        return resolved

    def fetch_whale(self, name: str, cik: str) -> dict:
        """Pipeline completo para un whale: 13F → holdings → símbolos."""
        logger.info(f"[M4] Procesando {name}...")
        accession, filing_date = self.get_latest_13f_accession(cik)
        if not accession:
            logger.warning(f"[M4] No se encontró 13F para {name}")
            return {"name": name, "cik": cik, "holdings": [],
                    "filing_date": None, "error": "no_filing"}

        holdings = self.get_holdings(cik, accession)
        if not holdings:
            # Fallback: usar datos de M2 InstitutionalFetcher si está disponible
            logger.warning(f"[M4] Sin holdings para {name} — usando datos parciales")
            return {"name": name, "cik": cik, "holdings": [],
                    "filing_date": filing_date, "accession": accession,
                    "error": "no_holdings"}

        holdings = self.resolve_symbols(holdings)
        # Ordenar por valor descendente
        holdings.sort(key=lambda x: x.get("value", 0), reverse=True)

        logger.info(f"[M4] {name}: {len(holdings)} posiciones | "
                    f"top={holdings[0]['name'] if holdings else 'N/A'}")
        return {
            "name":         name,
            "cik":          cik,
            "accession":    accession,
            "filing_date":  filing_date,
            "holdings":     holdings[:50],  # top 50 posiciones
            "total_value":  sum(h.get("value", 0) for h in holdings),
            "error":        None,
        }


# ─────────────────────────────────────────────────────────────────────────────
# 2. WhalePositionTracker — detecta cambios vs trimestre anterior
# ─────────────────────────────────────────────────────────────────────────────
class WhalePositionTracker:
    """
    Detecta qué movimientos hicieron los whales:
    - Nueva posición (no estaba antes)
    - Aumentó posición (compró más)
    - Redujo posición (vendió parte)
    - Cerró posición (vendió todo)
    """
    CACHE_FILE = "data/whale_cache.json"

    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self.cache = self._load_cache()

    def _load_cache(self) -> dict:
        if os.path.exists(self.CACHE_FILE):
            try:
                with open(self.CACHE_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self):
        with open(self.CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.cache, f, ensure_ascii=False, indent=2)

    def detect_changes(self, whale_data: dict) -> list:
        """
        Compara holdings actuales vs cache anterior.
        Retorna lista de movimientos detectados.
        """
        name     = whale_data["name"]
        current  = {h["symbol"]: h for h in whale_data.get("holdings", [])
                    if h.get("symbol")}
        previous = self.cache.get(name, {})
        changes  = []

        for symbol, holding in current.items():
            prev = previous.get(symbol)
            if prev is None:
                # Nueva posición
                changes.append({
                    "whale":      name,
                    "symbol":     symbol,
                    "action":     "NEW",
                    "shares_now": holding["shares"],
                    "value_now":  holding["value"],
                    "pct_change": None,
                    "strength":   "strong",  # Nueva posición siempre es señal fuerte
                })
            else:
                # Calcular cambio en shares
                prev_shares = prev.get("shares", holding["shares"])
                if prev_shares == 0:
                    continue
                pct = (holding["shares"] - prev_shares) / prev_shares
                if pct > 0.05:   # aumentó más de 5%
                    changes.append({
                        "whale":       name,
                        "symbol":      symbol,
                        "action":      "INCREASED",
                        "shares_now":  holding["shares"],
                        "shares_prev": prev_shares,
                        "pct_change":  round(pct * 100, 1),
                        "value_now":   holding["value"],
                        "strength":    "strong" if pct > 0.25 else "moderate",
                    })
                elif pct < -0.10:  # redujo más de 10%
                    changes.append({
                        "whale":       name,
                        "symbol":      symbol,
                        "action":      "REDUCED",
                        "shares_now":  holding["shares"],
                        "shares_prev": prev_shares,
                        "pct_change":  round(pct * 100, 1),
                        "value_now":   holding["value"],
                        "strength":    "bearish",
                    })

        # Detectar posiciones cerradas
        for symbol in previous:
            if symbol and symbol not in current:
                changes.append({
                    "whale":   name,
                    "symbol":  symbol,
                    "action":  "CLOSED",
                    "strength":"bearish",
                })

        # Guardar estado actual en cache
        if current:
            self.cache[name] = {
                sym: {"shares": h["shares"], "value": h["value"]}
                for sym, h in current.items()
            }
            self._save_cache()

        logger.info(f"[M4][TRACK] {name}: {len(changes)} movimientos detectados")
        return changes

    def aggregate_by_symbol(self, all_changes: list) -> dict:
        """
        Agrupa todos los movimientos por símbolo.
        Retorna dict: symbol → {bullish_whales, bearish_whales, net_signal}
        """
        by_symbol = {}
        for change in all_changes:
            sym = change.get("symbol")
            if not sym:
                continue
            if sym not in by_symbol:
                by_symbol[sym] = {"bullish": [], "bearish": [], "changes": []}

            if change["action"] in ("NEW", "INCREASED"):
                by_symbol[sym]["bullish"].append(change["whale"])
            elif change["action"] in ("REDUCED", "CLOSED"):
                by_symbol[sym]["bearish"].append(change["whale"])
            by_symbol[sym]["changes"].append(change)

        # Calcular señal neta
        for sym, data in by_symbol.items():
            b = len(data["bullish"])
            s = len(data["bearish"])
            if b > s and b >= 2:     data["net_signal"] = "STRONG_BUY"
            elif b > s and b == 1:   data["net_signal"] = "BUY"
            elif s > b and s >= 2:   data["net_signal"] = "STRONG_SELL"
            elif s > b:              data["net_signal"] = "SELL"
            else:                    data["net_signal"] = "NEUTRAL"
            data["whale_score"] = round(b / max(b + s, 1), 2)

        return by_symbol


# ─────────────────────────────────────────────────────────────────────────────
# 3. StrategyValidator — evalúa si la estrategia sigue vigente hoy
# ─────────────────────────────────────────────────────────────────────────────
class StrategyValidator:
    """
    Evalúa si el movimiento de un whale sigue siendo válido hoy.
    Considera: lag del 13F, cambio de régimen, rendimiento desde el filing.
    """

    def validate(self, symbol: str, filing_date: str,
                 regime: str = "UNKNOWN",
                 m1_sentiment: float = 0.5) -> dict:
        """
        Retorna dict con validez de la estrategia.
        """
        result = {
            "symbol":       symbol,
            "valid":        True,
            "confidence":   0.7,
            "warnings":     [],
            "price_change_since_filing": None,
        }

        # 1. Calcular lag (días desde el filing)
        lag_days = 999
        if filing_date:
            try:
                fd = datetime.strptime(filing_date[:10], "%Y-%m-%d")
                lag_days = (datetime.now() - fd).days
            except Exception:
                pass

        if lag_days > 90:
            result["warnings"].append(
                f"Filing tiene {lag_days} días de antigüedad — puede estar desactualizado"
            )
            result["confidence"] -= 0.15

        # 2. Rendimiento desde el filing (¿ya subió mucho?)
        if YF_OK and filing_date and lag_days < 200:
            try:
                tick     = yf.Ticker(symbol)
                hist     = tick.history(period="6mo")
                if not hist.empty:
                    price_now = float(hist["Close"].iloc[-1])
                    # Precio aproximado en fecha del filing
                    filing_dt = datetime.strptime(filing_date[:10], "%Y-%m-%d")
                    hist.index = hist.index.tz_localize(None)
                    past = hist[hist.index <= pd.Timestamp(filing_dt)]
                    if not past.empty:
                        price_then = float(past["Close"].iloc[-1])
                        pct_change = (price_now - price_then) / price_then
                        result["price_change_since_filing"] = round(pct_change * 100, 1)

                        if pct_change > 0.30:
                            result["warnings"].append(
                                f"Ya subió {pct_change:.0%} desde el filing — "
                                f"potencial limitado en el corto plazo"
                            )
                            result["confidence"] -= 0.20
                        elif pct_change > 0.15:
                            result["warnings"].append(
                                f"Subió {pct_change:.0%} desde el filing"
                            )
                            result["confidence"] -= 0.10
            except Exception as e:
                logger.debug(f"[M4][VAL] {symbol} price check: {e}")

        # 3. Régimen actual
        if regime in ("PANIC", "BEAR"):
            result["warnings"].append(
                f"Régimen actual: {regime} — estrategia bullish de alto riesgo"
            )
            result["confidence"] -= 0.20

        # 4. Sentimiento M1
        if m1_sentiment < 0.35:
            result["warnings"].append(
                f"Sentimiento de noticias bajo ({m1_sentiment:.0%}) — "
                f"contexto desfavorable"
            )
            result["confidence"] -= 0.10

        result["confidence"] = round(max(result["confidence"], 0.1), 2)
        result["valid"]      = result["confidence"] >= 0.40

        status = "VIGENTE" if result["valid"] else "EXPIRADA/RIESGO"
        logger.info(f"[M4][VAL] {symbol}: {status} | "
                    f"conf={result['confidence']:.0%} | "
                    f"lag={lag_days}d | "
                    f"warnings={len(result['warnings'])}")
        return result


# ─────────────────────────────────────────────────────────────────────────────
# 4. CopyStrategyEngine — adapta la estrategia al capital disponible
# ─────────────────────────────────────────────────────────────────────────────
class CopyStrategyEngine:
    """
    Dado un movimiento de whale válido, calcula:
    - ¿Vale la pena replicarlo con nuestro capital?
    - ¿Cuánto invertir proporcionalmente?
    - ¿Qué porcentaje del portafolio?
    """

    # Máximo % del capital en una sola copy strategy
    MAX_PCT_PER_COPY  = 0.08   # 8% por símbolo
    MAX_PCT_TOTAL     = 0.30   # 30% total en whale copies

    def evaluate(self, symbol: str, whale_name: str,
                 whale_value: float, whale_total_portfolio: float,
                 capital: float, validation: dict,
                 whale_score: float = 0.5) -> dict:
        """
        Evalúa si y cuánto invertir replicando al whale.
        """
        # % que el whale puso en ese símbolo
        whale_pct = whale_value / whale_total_portfolio if whale_total_portfolio > 0 else 0.01

        # Escalar al capital nuestro pero con límite
        raw_allocation = capital * whale_pct
        max_allocation = capital * self.MAX_PCT_PER_COPY
        allocation     = min(raw_allocation, max_allocation)

        # Ajustar por confianza de la validación
        confidence = validation.get("confidence", 0.5)
        allocation = allocation * confidence

        # Calcular shares aproximadas
        price = 0
        if YF_OK:
            try:
                tick  = yf.Ticker(symbol)
                info  = tick.info
                price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
            except Exception:
                pass

        shares = int(allocation / price) if price > 0 else 0

        # Decisión final
        min_investment = 500  # mínimo $500 para que valga la pena
        should_copy    = (
            allocation >= min_investment and
            validation.get("valid", False) and
            whale_score >= 0.5 and
            confidence >= 0.45
        )

        result = {
            "symbol":          symbol,
            "whale":           whale_name,
            "should_copy":     should_copy,
            "allocation":      round(allocation, 2),
            "allocation_pct":  round(allocation / capital * 100, 1),
            "whale_pct":       round(whale_pct * 100, 2),
            "shares_suggested":shares,
            "price":           round(price, 2),
            "confidence":      confidence,
            "reason":          self._reason(should_copy, allocation,
                                            confidence, validation),
        }
        logger.info(f"[M4][COPY] {symbol} ({whale_name[:20]}): "
                    f"copy={'SÍ' if should_copy else 'NO'} | "
                    f"${allocation:,.0f} ({result['allocation_pct']:.1f}%) | "
                    f"conf={confidence:.0%}")
        return result

    def _reason(self, should_copy, allocation, confidence, validation) -> str:
        if not should_copy:
            if not validation.get("valid"):
                return "Estrategia expirada o de alto riesgo"
            if allocation < 500:
                return "Asignación muy pequeña — no vale los costos de transacción"
            return "Confianza insuficiente para replicar"
        warnings = validation.get("warnings", [])
        if warnings:
            return f"Replicar con precaución — {warnings[0]}"
        return f"Replicar — confianza {confidence:.0%}"


# ─────────────────────────────────────────────────────────────────────────────
# 5. WhaleAgent — Claude API: reporte narrado completo
# ─────────────────────────────────────────────────────────────────────────────
class WhaleAgent:
    """Genera reporte de whale analysis usando Claude API."""

    MODEL = "claude-sonnet-4-20250514"

    def generate_report(self, top_opportunities: list,
                        all_changes: list,
                        capital: float,
                        regime: str = "UNKNOWN") -> str:
        from circuit_breaker import claude_cb

        if not CLAUDE_KEY:
            return self._fallback_report(top_opportunities, capital)

        if not claude_cb.can_call():
            logger.warning("[M4][AGENT] Claude API circuit breaker ABIERTO — usando fallback")
            return self._fallback_report(top_opportunities, capital)

        # Resumir cambios más importantes
        new_positions = [c for c in all_changes if c["action"] == "NEW"][:5]
        increased     = [c for c in all_changes if c["action"] == "INCREASED"][:5]
        closed        = [c for c in all_changes if c["action"] == "CLOSED"][:3]

        opp_text = "\n".join([
            f"  - {o['symbol']}: {o['whale'][:30]} | "
            f"copiar={'SÍ' if o['should_copy'] else 'NO'} | "
            f"${o['allocation']:,.0f} ({o['allocation_pct']:.1f}%) | "
            f"conf={o['confidence']:.0%} | {o['reason']}"
            for o in top_opportunities[:8]
        ]) or "  (sin oportunidades con suficiente confianza)"

        new_text = "\n".join([
            f"  - {c['whale'][:25]} abrió nueva posición en {c['symbol']}"
            for c in new_positions
        ]) or "  (ninguna)"

        inc_text = "\n".join([
            f"  - {c['whale'][:25]} aumentó {c['symbol']} "
            f"+{c.get('pct_change','?')}%"
            for c in increased
        ]) or "  (ninguna)"

        cls_text = "\n".join([
            f"  - {c['whale'][:25]} cerró posición en {c['symbol']}"
            for c in closed
        ]) or "  (ninguna)"

        prompt = f"""Eres el Whale Tracker de Börsenhirn, especializado en seguimiento de inversores institucionales.
Genera un reporte profesional en español sobre los movimientos recientes del "smart money".

## CONTEXTO
- Régimen de mercado: {regime}
- Capital disponible: ${capital:,.2f}
- Whales monitoreados: {len(WHALES)}

## MOVIMIENTOS DETECTADOS ESTE TRIMESTRE

### Nuevas posiciones (whales comprando por primera vez):
{new_text}

### Posiciones aumentadas (whales comprando más):
{inc_text}

### Posiciones cerradas (whales vendiendo todo):
{cls_text}

## OPORTUNIDADES DE COPY TRADING
{opp_text}

## INSTRUCCIONES
Genera un reporte con estas secciones:

1. **RESUMEN EJECUTIVO** — ¿Qué dice el smart money sobre el mercado ahora mismo?
2. **MOVIMIENTOS CLAVE** — Analiza los movimientos más importantes y su significado
3. **COPY OPPORTUNITIES** — Para cada oportunidad de copiar, explica el razonamiento
4. **LO QUE LOS WHALES ESTÁN EVITANDO** — Qué está saliendo del radar institucional
5. **ESTRATEGIA SUGERIDA** — Dado el capital de ${capital:,.2f} y régimen {regime}, ¿qué hacer?
6. **ADVERTENCIAS** — Riesgos del lag del 13F y otros factores a considerar

Sé directo y específico. Usa los datos reales. Máximo 550 palabras."""

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
                "messages":   [{"role": "user", "content": prompt}],
            }
            resp = httpx.post("https://api.anthropic.com/v1/messages",
                              headers=headers, json=body, timeout=60)
            resp.raise_for_status()
            report = resp.json()["content"][0]["text"]
            claude_cb.record_success()
            logger.info(f"[M4][AGENT] Reporte generado ({len(report)} chars)")
            return report
        except Exception as e:
            claude_cb.record_failure()
            logger.error(f"[M4][AGENT] Claude API: {e}")
            return self._fallback_report(top_opportunities, capital)

    def _fallback_report(self, opportunities: list, capital: float) -> str:
        lines = [
            f"=== WHALE TRACKER REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M')} ===",
            f"Capital: ${capital:,.2f}",
            "",
            "OPORTUNIDADES DE COPY TRADING:",
        ]
        for o in opportunities:
            copy = "✅ COPIAR" if o["should_copy"] else "❌ NO COPIAR"
            lines.append(f"  {o['symbol']} | {copy} | ${o['allocation']:,.0f} | {o['reason']}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# 6. M4WhaleTracker — orquestador principal
# ─────────────────────────────────────────────────────────────────────────────
class M4WhaleTracker:
    """
    Orquestador de M4. Pipeline completo:
    fetch 13F → detect changes → validate → copy eval → report → signal
    """

    def __init__(self):
        self.fetcher    = SECFilingFetcher()
        self.tracker    = WhalePositionTracker()
        self.validator  = StrategyValidator()
        self.copy_engine= CopyStrategyEngine()
        self.agent      = WhaleAgent()

    def run(self, capital: float = 104_217.80,
            regime: str = "UNKNOWN",
            m1_sentiments: dict = None,
            send_to_bot: bool = True,
            whales_to_run: list = None) -> dict:
        """
        Pipeline completo de M4.
        whales_to_run: lista de nombres de whales (None = todos)
        """
        m1_sentiments = m1_sentiments or {}
        whales_subset = {k: v for k, v in WHALES.items()
                         if whales_to_run is None or k in whales_to_run}

        logger.info(f"[M4] Iniciando Whale Tracker | "
                    f"{len(whales_subset)} whales | capital=${capital:,.2f}")

        # 1. Fetch 13F de cada whale
        whale_data_list = []
        for name, cik in whales_subset.items():
            data = self.fetcher.fetch_whale(name, cik)
            whale_data_list.append(data)
            time.sleep(0.5)  # respetar rate limit SEC

        # 2. Detectar cambios vs trimestre anterior
        all_changes = []
        for wdata in whale_data_list:
            if not wdata.get("error") or wdata.get("holdings"):
                changes = self.tracker.detect_changes(wdata)
                all_changes.extend(changes)

        logger.info(f"[M4] Total movimientos detectados: {len(all_changes)}")

        # 3. Agrupar por símbolo
        by_symbol = self.tracker.aggregate_by_symbol(all_changes)

        # 4. Validar vigencia y evaluar copy strategy
        opportunities = []
        filing_dates  = {w["name"]: w.get("filing_date")
                         for w in whale_data_list}

        for symbol, agg in by_symbol.items():
            if agg["net_signal"] not in ("STRONG_BUY", "BUY"):
                continue

            # Usar el filing date del whale más bullish
            bullish_whales = agg["bullish"]
            if not bullish_whales:
                continue

            main_whale = bullish_whales[0]
            filing_date = filing_dates.get(main_whale)

            # Obtener sentimiento M1 si está disponible
            sentiment = m1_sentiments.get(symbol, 0.5)

            # Validar vigencia
            validation = self.validator.validate(
                symbol=symbol,
                filing_date=filing_date,
                regime=regime,
                m1_sentiment=sentiment,
            )

            # Encontrar valor de posición del whale principal
            whale_value = 0
            whale_total = 0
            for wdata in whale_data_list:
                if wdata["name"] == main_whale:
                    whale_total = wdata.get("total_value", 0)
                    for h in wdata.get("holdings", []):
                        if h.get("symbol") == symbol:
                            whale_value = h.get("value", 0)
                            break
                    break

            # Evaluar copy strategy
            copy_eval = self.copy_engine.evaluate(
                symbol=symbol,
                whale_name=main_whale,
                whale_value=whale_value,
                whale_total_portfolio=whale_total,
                capital=capital,
                validation=validation,
                whale_score=agg["whale_score"],
            )
            copy_eval["bullish_whales"] = bullish_whales
            copy_eval["whale_count"]    = len(bullish_whales)
            opportunities.append(copy_eval)

        # Ordenar por confianza × whale_count
        opportunities.sort(
            key=lambda x: x["confidence"] * x.get("whale_count", 1),
            reverse=True
        )

        # 5. Reporte narrado
        logger.info("[M4] Generando reporte con Claude API...")
        report = self.agent.generate_report(
            top_opportunities=opportunities,
            all_changes=all_changes,
            capital=capital,
            regime=regime,
        )

        # 6. Enviar señales al bot
        if send_to_bot:
            self._send_signals(opportunities)

        result = {
            "timestamp":      datetime.now(timezone.utc).isoformat(),
            "regime":         regime,
            "capital":        capital,
            "whales_checked": len(whale_data_list),
            "total_changes":  len(all_changes),
            "opportunities":  opportunities,
            "by_symbol":      by_symbol,
            "report":         report,
        }

        self._save_report(report, opportunities)
        logger.info(f"[M4] Completado. {len(opportunities)} oportunidades de copy.")
        return result

    def _send_signals(self, opportunities: list):
        """Envía señales de copy al bot vía API."""
        for opp in opportunities:
            if not opp.get("should_copy"):
                continue
            try:
                payload = {
                    "symbol":  opp["symbol"],
                    "source":  "m4_whale",
                    "signal":  "buy",
                    "score":   opp["confidence"],
                    "reason":  (f"Whale copy: {', '.join(opp['bullish_whales'][:2])} | "
                                f"conf={opp['confidence']:.0%}"),
                }
                resp = requests.post(f"{BOT_API_URL}/signal",
                                     json=payload, timeout=5)
                if resp.status_code == 200:
                    logger.info(f"[M4] Señal enviada: {opp['symbol']}")
            except Exception as e:
                logger.warning(f"[M4] Señal fallida {opp['symbol']}: {e}")

    def _save_report(self, report: str, opportunities: list):
        try:
            os.makedirs("reports", exist_ok=True)
            ts   = datetime.now().strftime("%Y%m%d_%H%M")
            path = f"reports/m4_whale_report_{ts}.txt"
            with open(path, "w", encoding="utf-8") as f:
                f.write(report)
                f.write("\n\n--- COPY OPPORTUNITIES ---\n")
                for o in opportunities:
                    copy = "✅" if o["should_copy"] else "❌"
                    f.write(f"{copy} {o['symbol']} | ${o['allocation']:,.0f} | "
                            f"conf={o['confidence']:.0%} | {o['reason']}\n")
            logger.info(f"[M4] Reporte guardado: {path}")
        except Exception as e:
            logger.warning(f"[M4] No se pudo guardar: {e}")

    def get_top_whale_symbols(self, n: int = 10) -> list:
        """
        Retorna los símbolos más frecuentes en portfolios de whales.
        Útil para que M2 los priorice en su análisis.
        """
        symbol_count = {}
        for name, cik in list(WHALES.items())[:5]:  # top 5 whales
            try:
                acc, _ = self.fetcher.get_latest_13f_accession(cik)
                if acc:
                    holdings = self.fetcher.get_holdings(cik, acc)
                    holdings = self.fetcher.resolve_symbols(holdings)
                    for h in holdings[:20]:
                        sym = h.get("symbol")
                        if sym:
                            symbol_count[sym] = symbol_count.get(sym, 0) + 1
                time.sleep(0.3)
            except Exception:
                pass

        sorted_syms = sorted(symbol_count.items(),
                             key=lambda x: x[1], reverse=True)
        return [s[0] for s in sorted_syms[:n]]


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from logger import setup_logging
    setup_logging()

    tracker = M4WhaleTracker()
    result  = tracker.run(
        capital      = 104_217.80,
        regime       = "BULL",
        send_to_bot  = False,
        # Para prueba rápida, solo 3 whales — quita esto para correr todos
        whales_to_run = [
            "Berkshire Hathaway (Buffett)",
            "Pershing Square (Ackman)",
            "Bridgewater Associates (Dalio)",
        ]
    )

    print("\n" + "="*60)
    print("REPORTE M4 WHALE TRACKER")
    print("="*60)
    print(result["report"])
    print(f"\nWhales revisados: {result['whales_checked']}")
    print(f"Movimientos detectados: {result['total_changes']}")
    print(f"\nOPORTUNIDADES DE COPY:")
    for o in result["opportunities"]:
        copy = "✅ COPIAR" if o["should_copy"] else "❌ NO"
        print(f"  {copy} | {o['symbol']} | ${o['allocation']:,.0f} | "
              f"conf={o['confidence']:.0%} | {o['reason']}")