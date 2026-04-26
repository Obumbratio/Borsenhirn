"""
reporter.py - Sistema completo de informes, planes y asesor IA.

Uso:
    python reporter.py --daily       # reporte diario completo + PDF
    python reporter.py --monthly     # PDF mensual
    python reporter.py --advisor     # chat interactivo con IA
    python reporter.py --plan "idea" # analizar una idea
"""

import os, csv, json, argparse, logging
from datetime import datetime, timezone, timedelta
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests

import config
from logger import setup_logging
from execution import Executor
from market_context import get_full_context, format_news_for_report, format_context_summary

setup_logging()
logger = logging.getLogger(__name__)

try:
    from fpdf import FPDF
    PDF_OK = True
except ImportError:
    PDF_OK = False

PLANS_FILE = "reports/plans.json"
os.makedirs("reports", exist_ok=True)


# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════
def _claude(messages: list, system: str, max_tokens: int = 2000) -> str:
    """Llama a Claude API con autenticación correcta."""
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
            },
            timeout=40,
        )
        data = resp.json()
        if "content" not in data:
            return f"Error API ({resp.status_code}): {data.get('error', {}).get('message', str(data))}"
        return data["content"][0]["text"]
    except Exception as e:
        return f"[Error IA: {e}]"


def _get_market_news() -> str:
    """Obtiene noticias financieras recientes vía API gratuita."""
    try:
        # Alpha Vantage news (gratuito, sin key para noticias generales)
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "NEWS_SENTIMENT",
            "tickers": config.SYMBOL,
            "limit": 5,
            "apikey": "demo",
        }
        r = requests.get(url, params=params, timeout=8)
        data = r.json()
        if "feed" in data:
            news = []
            for item in data["feed"][:5]:
                news.append(f"• {item.get('title','')[:100]} "
                             f"[sentiment: {item.get('overall_sentiment_label','')}]")
            return "\n".join(news)
    except Exception:
        pass

    # Fallback: finnhub news (también gratuito)
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        week  = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        r = requests.get(
            f"https://finnhub.io/api/v1/company-news",
            params={"symbol": config.SYMBOL, "from": week, "to": today,
                    "token": "demo"},
            timeout=8,
        )
        items = r.json()
        if isinstance(items, list) and items:
            news = [f"• {n.get('headline','')[:100]}" for n in items[:5]]
            return "\n".join(news)
    except Exception:
        pass

    return "Noticias no disponibles en este momento."


def _load_plans() -> dict:
    """Carga los planes guardados."""
    if os.path.exists(PLANS_FILE):
        with open(PLANS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"mision_principal": "", "planes": []}


def _save_plans(plans: dict):
    """Guarda los planes."""
    with open(PLANS_FILE, "w", encoding="utf-8") as f:
        json.dump(plans, f, ensure_ascii=False, indent=2)


def _load_trades_today() -> list:
    """Carga los trades de hoy desde el CSV."""
    today  = datetime.now(timezone.utc).date()
    trades = []
    if os.path.exists(config.TRADES_LOG):
        with open(config.TRADES_LOG, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("timestamp", "").startswith(str(today)):
                    trades.append(row)
    return trades


def _load_all_trades() -> list:
    """Carga todos los trades históricos."""
    if not os.path.exists(config.TRADES_LOG):
        return []
    with open(config.TRADES_LOG, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _portfolio_context(executor: Executor) -> dict:
    """Obtiene contexto completo del portfolio."""
    acc  = executor.get_account()
    pos  = executor.get_positions()
    all_trades = _load_all_trades()
    sells = [t for t in all_trades if t.get("action") == "sell"]
    wins  = [t for t in sells if float(t.get("value",0)) > 0]
    return {
        "equity":       acc.get("equity", config.CAPITAL) if acc else config.CAPITAL,
        "cash":         acc.get("cash", 0) if acc else 0,
        "buying_power": acc.get("buying_power", 0) if acc else 0,
        "pnl_total":    (acc.get("equity", config.CAPITAL) - config.CAPITAL) if acc else 0,
        "positions":    pos,
        "total_trades": len(all_trades),
        "win_rate":     (len(wins)/len(sells)*100) if sells else 0,
        "trades_today": _load_trades_today(),
    }


# ══════════════════════════════════════════════════════════════
# REPORTE DIARIO COMPLETO
# ══════════════════════════════════════════════════════════════
def daily_report(executor: Executor = None, save_pdf: bool = True):
    """
    Reporte diario completo que incluye:
    - Resumen financiero del día
    - Explicación de decisiones del bot
    - Noticias relevantes del mercado
    - Proyecciones a corto plazo
    - Mejoras sugeridas por la IA
    - Estado de los planes activos
    """
    if executor is None:
        executor = Executor()

    today   = datetime.now(timezone.utc).date()
    ctx     = _portfolio_context(executor)
    plans   = _load_plans()
    print("\n  Obteniendo contexto completo del mercado...")
    mkt     = get_full_context(config.SYMBOL)
    news    = format_news_for_report(mkt.get("news", []))
    mkt_summary = format_context_summary(mkt)
    trades  = ctx["trades_today"]

    print(f"\n{'═'*58}")
    print(f"  📊  REPORTE DIARIO — {today}")
    print(f"{'═'*58}")

    # ── Sistema prompt para IA ────────────────────────────────
    system = f"""
Eres el sistema de inteligencia del trading bot. Tu misión es generar el reporte diario completo.

ESTADO DEL PORTFOLIO HOY ({today}):
- Equity: ${ctx['equity']:,.2f}
- PnL total vs inicio: ${ctx['pnl_total']:+,.2f}
- Cash disponible: ${ctx['cash']:,.2f}
- Posiciones abiertas: {ctx['positions'] if ctx['positions'] else 'ninguna'}
- Trades realizados hoy: {trades if trades else 'ninguno'}
- Win rate histórico: {ctx['win_rate']:.1f}%
- Total operaciones históricas: {ctx['total_trades']}

ESTRATEGIA DEL BOT:
- Activo: {config.SYMBOL} | Timeframe: {config.TIMEFRAME}
- SMA{config.MA_SHORT_WINDOW}/{config.MA_LONG_WINDOW} + RSI({config.RSI_PERIOD}) + Bollinger Bands + Random Forest ML
- Stop-loss: {config.STOP_LOSS_ATR_MULT}x ATR | Max posición: {config.MAX_POSITION_PCT*100}%
- Umbral ML venta: {config.ML_SELL_PROB_THRESHOLD*100}%

CONTEXTO DE MERCADO EN TIEMPO REAL:
{mkt_summary}

VIX: {mkt.get('vix', {}).get('value','N/A')} ({mkt.get('vix', {}).get('level','?')})
Fear & Greed: {mkt.get('fear_greed', {}).get('value','N/A')}/100 ({mkt.get('fear_greed', {}).get('name','?')})
Señal de mercado: {mkt.get('market_signal','N/A')}
Indices: {mkt.get('yfinance', {}).get('indices', {})}
FRED macro: {mkt.get('fred', {})}
Earnings proximos: {mkt.get('earnings', {}).get('summary', 'ninguno')}

MISIÓN PRINCIPAL: {plans.get('mision_principal', 'Maximizar retorno ajustado por riesgo en SPY')}
PLANES ACTIVOS: {json.dumps(plans.get('planes', []), ensure_ascii=False)}

NOTICIAS DEL MERCADO HOY:
{news}

INSTRUCCIONES — Genera el reporte con estas secciones EXACTAS:

## 1. RESUMEN FINANCIERO DEL DÍA
(números concretos, ganancias/pérdidas, comparación con ayer)

## 2. DECISIONES DEL BOT — POR QUÉ
(explica cada trade de hoy con razonamiento técnico. Si no hubo trades, explica por qué el bot decidió no operar)

## 3. ANÁLISIS DE MERCADO Y NOTICIAS
(cómo las noticias afectan la estrategia y el activo)

## 4. PROYECCIONES A CORTO PLAZO (3-5 días)
(3 escenarios: optimista, base, pesimista con probabilidades)

## 5. ESTADO DE LOS PLANES
(progreso de cada plan activo hacia su objetivo)

## 6. MEJORAS SUGERIDAS PARA MAÑANA
(3-5 mejoras concretas y accionables para optimizar la estrategia)

Responde en español. Sé directo y usa datos concretos.
"""

    print("\n⏳ Generando análisis con IA...\n")
    analysis = _claude([{"role":"user","content":"Genera el reporte diario completo."}], system, max_tokens=2500)

    print(analysis)
    print(f"\n{'═'*58}\n")

    # ── Guardar TXT ───────────────────────────────────────────
    txt_path = f"reports/daily_{today}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"REPORTE DIARIO — {today}\n{'='*50}\n\n")
        f.write(f"Equity: ${ctx['equity']:,.2f} | PnL: ${ctx['pnl_total']:+,.2f}\n\n")
        f.write(analysis)
    logger.info(f"Reporte diario guardado en {txt_path}")

    # ── Generar PDF ───────────────────────────────────────────
    if save_pdf:
        _make_daily_pdf(today, ctx, analysis, trades, news)

    return analysis


def _clean(text: str) -> str:
    """Elimina caracteres no soportados por fpdf latin-1."""
    replacements = {
        "\u2014": "-", "\u2013": "-", "\u2019": "'", "\u2018": "'",
        "\u201c": '"', "\u201d": '"', "\u2022": "*", "\u2026": "...",
        "\u2192": "->", "\u2191": "^", "\u2193": "v", "\u2713": "OK",
        "\u274c": "X", "\u2705": "OK", "\u26a0": "!", "\u2b50": "*",
        "\u0301": "", "\u200b": "",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="replace").decode("latin-1")

def _make_daily_pdf(today, ctx, analysis, trades, news):
    """Genera el PDF del reporte diario."""
    if not PDF_OK:
        print("⚠️  fpdf2 no instalado. Solo se guardó el TXT.")
        return

    # Gráfico equity
    chart_path = f"reports/chart_{today}.png"
    eq_path    = "results/backtest_equity.csv"
    fig, axes  = plt.subplots(1, 2, figsize=(14, 4))

    if os.path.exists(eq_path):
        eq_df = pd.read_csv(eq_path, index_col=0, parse_dates=True)
        axes[0].plot(eq_df.index, eq_df["equity"], color="royalblue", linewidth=1.5)
        axes[0].axhline(config.CAPITAL, color="gray", linestyle="--", linewidth=0.8)
        axes[0].set_title("Curva de Capital"); axes[0].grid(alpha=0.3)
    else:
        axes[0].text(0.5,0.5,"Sin datos", ha="center"); axes[0].set_title("Equity")

    # Mini resumen en el gráfico
    axes[1].axis("off")
    txt = (f"RESUMEN {today}\n\n"
           f"Equity:     ${ctx['equity']:>12,.2f}\n"
           f"PnL total:  ${ctx['pnl_total']:>+12,.2f}\n"
           f"Cash:       ${ctx['cash']:>12,.2f}\n"
           f"Trades hoy: {len(trades)}\n"
           f"Win rate:   {ctx['win_rate']:.1f}%")
    axes[1].text(0.05, 0.5, txt, transform=axes[1].transAxes,
                 fontsize=12, va="center", fontfamily="monospace",
                 bbox=dict(boxstyle="round", facecolor="lightyellow", alpha=0.8))
    plt.tight_layout()
    plt.savefig(chart_path, dpi=130, bbox_inches="tight"); plt.close()

    # PDF
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Header
    pdf.set_fill_color(30, 60, 120)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 14, _clean(f"Reporte Diario de Trading — {today}"), ln=True, fill=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    # KPIs
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(230, 240, 255)
    pdf.cell(0, 8, "Metricas Clave", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 11)
    kpis = [
        ("Equity Total",    f"${ctx['equity']:,.2f}"),
        ("PnL vs Inicio",   f"${ctx['pnl_total']:+,.2f}"),
        ("Cash",            f"${ctx['cash']:,.2f}"),
        ("Trades Hoy",      str(len(trades))),
        ("Win Rate Hist.",  f"{ctx['win_rate']:.1f}%"),
    ]
    for i, (k, v) in enumerate(kpis):
        fill = i % 2 == 0
        pdf.set_fill_color(245,245,255) if fill else pdf.set_fill_color(255,255,255)
        pdf.cell(95, 7, k, border=1, fill=fill)
        pdf.cell(95, 7, v, border=1, fill=fill, ln=True)
    pdf.ln(4)

    # Gráfico
    pdf.image(chart_path, x=10, w=185)
    pdf.ln(4)

    # Análisis IA
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_fill_color(230, 240, 255)
    pdf.cell(0, 8, "Analisis Completo del Bot", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 9)
    # Escribir análisis línea por línea
    for line in analysis.split("\n"):
        line = line.strip()
        if not line:
            pdf.ln(2); continue
        if line.startswith("##"):
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_fill_color(220, 230, 255)
            pdf.cell(0, 7, _clean(line.replace("##","").strip()), ln=True, fill=True)
            pdf.set_font("Helvetica", "", 9)
        else:
            line = _clean(line)
            while len(line) > 110:
                pdf.cell(0, 5, line[:110], ln=True)
                line = line[110:]
            if line:
                pdf.cell(0, 5, line, ln=True)

    # Trades del día
    if trades:
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_fill_color(230, 240, 255)
        pdf.cell(0, 8, "Trades de Hoy", ln=True, fill=True)
        pdf.set_font("Helvetica", "B", 9)
        for h, w in zip(["Hora","Accion","Precio","Qty","Valor","Razon"],
                        [28,18,20,15,22,87]):
            pdf.cell(w, 6, h, border=1, fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for t in trades:
            for v, w in zip([
                t.get("timestamp","")[:16],
                t.get("action","").upper(),
                f"${float(t.get('price',0)):.2f}",
                t.get("qty",""),
                f"${float(t.get('value',0)):.2f}",
                t.get("reason","")[:40],
            ], [28,18,20,15,22,87]):
                pdf.cell(w, 5, str(v), border=1)
            pdf.ln()

    pdf_path = f"reports/daily_{today}.pdf"
    pdf.output(pdf_path)
    print(f"✅ PDF diario guardado en: {pdf_path}")


# ══════════════════════════════════════════════════════════════
# GESTOR DE PLANES
# ══════════════════════════════════════════════════════════════
def manage_plans(executor: Executor = None):
    """Gestiona la misión principal y los planes del usuario."""
    if executor is None:
        executor = Executor()

    plans = _load_plans()
    ctx   = _portfolio_context(executor)

    print(f"\n{'═'*55}")
    print(f"  📋  GESTOR DE PLANES")
    print(f"{'═'*55}")
    print(f"\n🎯 MISIÓN PRINCIPAL:")
    print(f"   {plans.get('mision_principal') or '(no definida)'}")
    print(f"\n📌 PLANES ACTIVOS ({len(plans.get('planes',[]))}):")
    for i, p in enumerate(plans.get("planes",[]), 1):
        print(f"   {i}. [{p.get('estado','activo').upper()}] {p.get('nombre','')} — {p.get('objetivo','')}")

    print(f"\n{'─'*55}")
    print("Opciones:")
    print("  1. Definir/cambiar misión principal")
    print("  2. Agregar nuevo plan")
    print("  3. Analizar un plan con IA")
    print("  4. Ver análisis completo de todos los planes")
    print("  5. Volver")
    opt = input("\nElige (1-5): ").strip()

    if opt == "1":
        mision = input("\nDefine la misión principal del bot\n(ej: 'Crecer $100k a $150k en 12 meses con riesgo controlado')\n→ ").strip()
        plans["mision_principal"] = mision
        _save_plans(plans)
        print(f"\n✅ Misión guardada: {mision}")

    elif opt == "2":
        nombre   = input("Nombre del plan: ").strip()
        objetivo = input("Objetivo concreto (ej: 'ganar 5% en 30 días con QQQ'): ").strip()
        plazo    = input("Plazo (ej: '30 días', '3 meses'): ").strip()
        plan = {"nombre":nombre,"objetivo":objetivo,"plazo":plazo,
                "estado":"activo","creado":str(datetime.now().date())}

        # IA evalúa el plan
        system = f"""
Eres un asesor de trading. Evalúa este plan:
Portfolio actual: ${ctx['equity']:,.2f} | Cash: ${ctx['cash']:,.2f}
Estrategia actual: {config.SYMBOL} {config.TIMEFRAME} con ML

Plan propuesto:
- Nombre: {nombre}
- Objetivo: {objetivo}  
- Plazo: {plazo}

Responde con:
1. VEREDICTO: ÓPTIMO / VIABLE / NO RECOMENDADO
2. Por qué (2-3 frases)
3. Riesgos principales
4. Ajuste sugerido si aplica

Responde en español, sé directo.
"""
        print("\n⏳ La IA está evaluando tu plan...\n")
        eval_ia = _claude([{"role":"user","content":"Evalúa este plan."}], system)
        plan["evaluacion_ia"] = eval_ia
        plans.setdefault("planes",[]).append(plan)
        _save_plans(plans)
        print(f"\n🧠 EVALUACIÓN IA:\n{eval_ia}")
        print(f"\n✅ Plan guardado.")

    elif opt == "3":
        if not plans.get("planes"):
            print("No hay planes activos.")
            return
        for i, p in enumerate(plans["planes"], 1):
            print(f"  {i}. {p.get('nombre','')}")
        idx = int(input("Elige el número del plan: ").strip()) - 1
        if 0 <= idx < len(plans["planes"]):
            plan = plans["planes"][idx]
            system = f"""
Analiza el progreso de este plan de trading:
Plan: {json.dumps(plan, ensure_ascii=False)}
Portfolio actual: ${ctx['equity']:,.2f} | PnL: ${ctx['pnl_total']:+,.2f}
Win rate: {ctx['win_rate']:.1f}% | Trades totales: {ctx['total_trades']}

Dime:
1. ¿Va bien el plan? ¿Está en camino al objetivo?
2. Probabilidad de lograrlo (%)
3. Qué ajustar para mejorar las probabilidades
Responde en español.
"""
            resp = _claude([{"role":"user","content":"Analiza el progreso."}], system)
            print(f"\n🧠 ANÁLISIS DE PROGRESO:\n{resp}")

    elif opt == "4":
        system = f"""
Analiza todos los planes activos y da un reporte ejecutivo:
Misión: {plans.get('mision_principal','')}
Planes: {json.dumps(plans.get('planes',[]), ensure_ascii=False)}
Portfolio: ${ctx['equity']:,.2f} | PnL: ${ctx['pnl_total']:+,.2f} | Win rate: {ctx['win_rate']:.1f}%

Para cada plan: estado, probabilidad de éxito, acción recomendada.
Luego da una recomendación global de prioridades.
Responde en español.
"""
        resp = _claude([{"role":"user","content":"Reporte ejecutivo de planes."}], system)
        print(f"\n{'═'*55}\n🧠 REPORTE EJECUTIVO DE PLANES:\n\n{resp}\n{'═'*55}")

        if PDF_OK:
            pdf_path = f"reports/planes_{datetime.now().strftime('%Y%m%d')}.pdf"
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Helvetica","B",16)
            pdf.cell(0,12,"Reporte de Planes",ln=True,align="C")
            pdf.set_font("Helvetica","",10)
            for line in resp.split("\n"):
                pdf.cell(0,5,line[:110],ln=True)
            pdf.output(pdf_path)
            print(f"✅ PDF guardado: {pdf_path}")


# ══════════════════════════════════════════════════════════════
# CHAT ASESOR IA
# ══════════════════════════════════════════════════════════════
def interactive_advisor(executor: Executor = None):
    """Chat interactivo con el asesor IA con contexto completo."""
    if executor is None:
        executor = Executor()

    ctx   = _portfolio_context(executor)
    plans = _load_plans()
    print("\n  Obteniendo contexto del mercado...")
    mkt   = get_full_context(config.SYMBOL)
    news  = format_news_for_report(mkt.get("news", []))

    system = f"""
Eres el asesor IA integrado del trading bot. Tienes acceso completo al estado del portfolio y del mercado.

PORTFOLIO HOY:
- Equity: ${ctx['equity']:,.2f} | PnL: ${ctx['pnl_total']:+,.2f}
- Cash: ${ctx['cash']:,.2f} | Posiciones: {ctx['positions']}
- Win rate: {ctx['win_rate']:.1f}% | Total trades: {ctx['total_trades']}

ESTRATEGIA ACTIVA:
- {config.SYMBOL} {config.TIMEFRAME} | SMA{config.MA_SHORT_WINDOW}/{config.MA_LONG_WINDOW}
- RSI({config.RSI_PERIOD}) | Bollinger Bands | Random Forest ML
- Stop-loss: {config.STOP_LOSS_ATR_MULT}x ATR | Max posicion: {config.MAX_POSITION_PCT*100}%

CONTEXTO DE MERCADO EN TIEMPO REAL:
- VIX: {mkt.get('vix',{}).get('value','N/A')} ({mkt.get('vix',{}).get('level','?')}) — señal: {mkt.get('vix',{}).get('signal','?')}
- Fear & Greed: {mkt.get('fear_greed',{}).get('value','N/A')}/100 ({mkt.get('fear_greed',{}).get('name','?')})
- Señal compuesta mercado: {mkt.get('market_signal','N/A')}
- Indices: {mkt.get('yfinance',{}).get('indices',{})}
- Earnings proximos: {mkt.get('earnings',{}).get('summary','ninguno')}
- Datos macro FRED: {mkt.get('fred',{})}

MISIÓN: {plans.get('mision_principal','Maximizar retorno con riesgo controlado')}
PLANES: {json.dumps(plans.get('planes',[]), ensure_ascii=False)}

NOTICIAS ACTUALES:
{news}

PUEDES:
- Evaluar ideas y planes de trading
- Explicar decisiones del bot
- Sugerir mejoras a la estrategia  
- Dar proyecciones con escenarios
- Armar planes detallados
- Analizar si algo es óptimo o riesgoso

Responde siempre en español. Sé directo, usa datos concretos, avisa de riesgos.
"""

    history = []
    print(f"\n{'═'*58}")
    print(f"  🧠  ASESOR IA — Chat Interactivo")
    print(f"  Equity: ${ctx['equity']:,.2f} | PnL: ${ctx['pnl_total']:+,.2f}")
    print(f"  Escribe 'salir' para terminar")
    print(f"  Escribe 'planes' para gestionar tus planes")
    print(f"{'═'*58}\n")

    while True:
        user_input = input("Tú: ").strip()
        if user_input.lower() in ("salir","exit","q"): break
        if user_input.lower() == "planes":
            manage_plans(executor); continue
        if not user_input: continue

        history.append({"role":"user","content":user_input})
        print("\n⏳ Pensando...\n")
        resp = _claude(history, system, max_tokens=1500)
        history.append({"role":"assistant","content":resp})
        print(f"🧠 Asesor: {resp}\n{'─'*58}\n")

        # Guardar conversación
        with open(f"reports/chat_{datetime.now().strftime('%Y%m%d')}.txt",
                  "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().strftime('%H:%M')}] TÚ: {user_input}\n")
            f.write(f"[{datetime.now().strftime('%H:%M')}] IA: {resp}\n")

    print("Chat cerrado. Conversación guardada en reports/")


# ══════════════════════════════════════════════════════════════
# REPORTE SEMANAL DETALLADO
# ══════════════════════════════════════════════════════════════
def _load_trades_range(start_date: str, end_date: str) -> list:
    """Carga trades del CSV entre dos fechas (YYYY-MM-DD)."""
    trades = []
    if not os.path.exists(config.TRADES_LOG):
        return trades
    with open(config.TRADES_LOG, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ts = row.get("timestamp", "")[:10]
            if start_date <= ts <= end_date:
                trades.append(row)
    return trades


def _parse_pnl(reason: str) -> float | None:
    """Extrae PnL del campo reason si contiene PnL=$+123.45 o PnL=$-123.45."""
    import re
    m = re.search(r"PnL=\$([+-]?[\d,.]+)", reason)
    if m:
        return float(m.group(1).replace(",", ""))
    return None


def _extract_ml(reason: str) -> float | None:
    """Extrae probabilidad ML del campo reason."""
    import re
    m = re.search(r"ML=([0-9.]+)", reason)
    return float(m.group(1)) if m else None


def _extract_vix(reason: str) -> float | None:
    """Extrae VIX del campo reason."""
    import re
    m = re.search(r"VIX=([0-9.]+)", reason)
    return float(m.group(1)) if m else None


def _extract_fg(reason: str) -> int | None:
    """Extrae Fear & Greed del campo reason."""
    import re
    m = re.search(r"F&G=(\d+)", reason)
    return int(m.group(1)) if m else None


def _parse_daily_equity_from_logs(start_date: str, end_date: str) -> list:
    """Parsea equity diario de los archivos de log."""
    import re, glob as glob_mod
    results = []
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    for log_file in sorted(glob_mod.glob(os.path.join(log_dir, "trading_bot_*.log"))):
        fname = os.path.basename(log_file)
        m = re.search(r"trading_bot_(\d{4}-\d{2}-\d{2})", fname)
        if not m:
            continue
        log_date = m.group(1)
        if not (start_date <= log_date <= end_date):
            continue
        equity = None
        vix_val = None
        fg_val = None
        regime = None
        try:
            with open(log_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "day_start_equity" in line:
                        em = re.search(r"day_start_equity['\"]?\s*[:=]\s*([0-9,.]+)", line)
                        if em:
                            equity = float(em.group(1).replace(",", ""))
                    if "Equity:" in line and equity is None:
                        em = re.search(r"Equity:\s*\$?([0-9,.]+)", line)
                        if em:
                            equity = float(em.group(1).replace(",", ""))
                    if "VIX:" in line or "vix" in line.lower():
                        vm = re.search(r"VIX[:\s=]+([0-9.]+)", line, re.IGNORECASE)
                        if vm and vix_val is None:
                            vix_val = float(vm.group(1))
                    if "fear" in line.lower() and "greed" in line.lower():
                        fm = re.search(r"(?:F&G|fear.*greed)[:\s=]+(\d+)", line, re.IGNORECASE)
                        if fm and fg_val is None:
                            fg_val = int(fm.group(1))
                    if "Regimen:" in line or "regime" in line.lower():
                        rm = re.search(r"(?:Regimen|regime)[:\s=]+(\w+)", line, re.IGNORECASE)
                        if rm and regime is None:
                            regime = rm.group(1).upper()
        except Exception:
            pass
        if equity or vix_val or fg_val or regime:
            results.append({
                "date": log_date, "equity": equity,
                "vix": vix_val, "fg": fg_val, "regime": regime
            })
    return results


def weekly_report(executor: Executor = None, start: str = None, end: str = None):
    """Reporte semanal/quincenal detallado con documentacion completa."""
    if executor is None:
        executor = Executor()

    today = datetime.now(timezone.utc).date()
    if not end:
        end = str(today)
    if not start:
        start = str(today - timedelta(days=14))

    trades = _load_trades_range(start, end)
    ctx = _portfolio_context(executor)

    # --- Calcular metricas ---
    buys  = [t for t in trades if t.get("action") == "buy"]
    sells = [t for t in trades if t.get("action") == "sell"]

    pnl_by_symbol = {}
    wins, losses = [], []
    stop_losses = []
    for t in sells:
        sym = t.get("symbol", "")
        reason = t.get("reason", "")
        pnl = _parse_pnl(reason)
        if pnl is not None:
            pnl_by_symbol.setdefault(sym, []).append(pnl)
            if pnl >= 0:
                wins.append(t)
            else:
                losses.append(t)
        if "Stop-loss" in reason:
            stop_losses.append(t)

    total_pnl = sum(p for lst in pnl_by_symbol.values() for p in lst)
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / (win_count + loss_count) * 100) if (win_count + loss_count) > 0 else 0
    avg_win = sum(_parse_pnl(t.get("reason","")) or 0 for t in wins) / win_count if wins else 0
    avg_loss = sum(_parse_pnl(t.get("reason","")) or 0 for t in losses) / loss_count if losses else 0

    trades_by_day = {}
    for t in trades:
        day = t.get("timestamp", "")[:10]
        trades_by_day.setdefault(day, []).append(t)

    sym_total_pnl = {}
    for sym, pnls in pnl_by_symbol.items():
        sym_total_pnl[sym] = sum(pnls)
    top_winners = sorted(sym_total_pnl.items(), key=lambda x: x[1], reverse=True)[:5]
    top_losers = sorted(sym_total_pnl.items(), key=lambda x: x[1])[:5]

    # Sector mapping
    SECTORS = {
        "Tecnologia": ["AAPL","MSFT","GOOGL","META","TSLA","AMD","INTC","CRM","NVDA"],
        "Salud": ["JNJ","PFE","UNH","ABBV","MRK","LLY","ABT"],
        "Energia": ["XOM","CVX","OXY","SLB","COP","USO"],
        "Finanzas": ["BAC","JPM","WFC","C","AXP","MS","GS"],
        "Consumo": ["MCD","HD","WMT","COST","TGT","AMZN"],
        "ETFs": ["SPY","QQQ","IWM","DIA","TQQQ","SQQQ"],
        "Commodities/Bonos": ["GLD","SLV","TLT"],
    }
    def get_sector(sym):
        for sec, syms in SECTORS.items():
            if sym in syms:
                return sec
        return "Otro"

    # PnL por sector
    sector_pnl = {}
    sector_trades = {}
    for t in trades:
        sec = get_sector(t.get("symbol",""))
        sector_trades.setdefault(sec, []).append(t)
    for sec in sector_trades:
        sells_sec = [t for t in sector_trades[sec] if t.get("action")=="sell"]
        pnls = [_parse_pnl(t.get("reason","")) for t in sells_sec]
        pnls = [p for p in pnls if p is not None]
        sector_pnl[sec] = {"total": sum(pnls), "wins": sum(1 for p in pnls if p>=0),
                           "losses": sum(1 for p in pnls if p<0), "trades": len(sector_trades[sec])}

    # ML stats de compras
    ml_probs = [_extract_ml(t.get("reason","")) for t in buys]
    ml_probs = [p for p in ml_probs if p is not None]
    avg_ml = sum(ml_probs)/len(ml_probs) if ml_probs else 0

    # Sell reasons breakdown
    sell_reasons = {}
    for t in sells:
        reason = t.get("reason","")
        if "Stop-loss" in reason:
            key = "Stop-loss"
        elif "RSI+BB superior" in reason:
            key = "RSI+BB superior (sobrecompra)"
        elif "ML venta fuerte" in reason:
            key = "ML venta fuerte"
        elif "MACD bajista" in reason:
            key = "MACD bajista"
        else:
            key = "Otra senal tecnica"
        sell_reasons[key] = sell_reasons.get(key, 0) + 1

    # Buy reasons breakdown
    buy_reasons = {}
    for t in buys:
        reason = t.get("reason","")
        tags = []
        if "Mercado: COMPRAR" in reason:
            tags.append("Senal mercado agresiva")
        if "RSI=" in reason and "bajo" in reason:
            tags.append("RSI bajo (sobreventa)")
        if "Rebote BB" in reason:
            tags.append("Rebote Bollinger Band")
        if "ML=" in reason:
            tags.append("Confianza ML")
        if "Score=" in reason:
            tags.append("Score tecnico")
        if "Caida+rebote" in reason:
            tags.append("Caida+rebote RSI")
        for tag in (tags or ["Senal combinada"]):
            buy_reasons[tag] = buy_reasons.get(tag, 0) + 1

    # Equity diario de logs
    daily_equity = _parse_daily_equity_from_logs(start, end)

    print(f"\n{'='*60}")
    print(f"  REPORTE DETALLADO -- {start} a {end}")
    print(f"{'='*60}")
    print(f"  Trades: {len(trades)} ({len(buys)}B / {len(sells)}S)")
    print(f"  PnL realizado: ${total_pnl:+,.2f} | Win rate: {win_rate:.1f}%")
    print(f"  Equity: ${ctx['equity']:,.2f} | Stop-losses: {len(stop_losses)}")
    print(f"{'='*60}\n")

    # --- Generar PDF ---
    if not PDF_OK:
        print("fpdf2 no instalado. No se puede generar PDF.")
        return
    _make_weekly_pdf_detailed(
        start, end, ctx, trades, buys, sells, wins, losses,
        stop_losses, total_pnl, win_rate, win_count, loss_count,
        avg_win, avg_loss, top_winners, top_losers,
        trades_by_day, sector_pnl, sector_trades,
        sell_reasons, buy_reasons, avg_ml, ml_probs,
        daily_equity, pnl_by_symbol
    )


def _make_weekly_pdf_detailed(
    start, end, ctx, trades, buys, sells, wins, losses,
    stop_losses, total_pnl, win_rate, win_count, loss_count,
    avg_win, avg_loss, top_winners, top_losers,
    trades_by_day, sector_pnl, sector_trades,
    sell_reasons, buy_reasons, avg_ml, ml_probs,
    daily_equity, pnl_by_symbol
):
    """Genera PDF semanal profesional y detallado."""

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(10, 10, 10)

    def titulo(texto, r=10, g=25, b=55):
        pdf.set_fill_color(r, g, b)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 9, f"   {_clean(texto)}", fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30, 30, 30)
        pdf.ln(3)

    def subtitulo(texto):
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(10, 55, 115)
        pdf.cell(0, 7, _clean(texto), new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(30, 30, 30)

    def cuerpo(texto, indent=5):
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(40, 40, 40)
        pdf.set_x(pdf.get_x() + indent)
        pdf.multi_cell(0, 5.5, _clean(texto))
        pdf.ln(1)

    def bullet(texto, color=(15, 100, 200)):
        pdf.set_x(12)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*color)
        pdf.cell(5, 6, chr(149))
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(0, 6, _clean(texto))

    def kv(etiqueta, valor, estado="info"):
        colores = {"ok":(0,145,55),"warning":(190,110,0),"error":(170,15,15),"info":(15,75,175)}
        c = colores.get(estado, (100,100,100))
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(242, 246, 255)
        pdf.set_draw_color(175, 200, 228)
        pdf.cell(65, 7, f"  {_clean(etiqueta)}", border=1, fill=True)
        pdf.set_fill_color(*[min(255, x+195) for x in c])
        pdf.set_text_color(*c)
        pdf.cell(0, 7, f"  {_clean(valor)}", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(40, 40, 40)

    def separador():
        pdf.set_draw_color(175, 200, 228)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(4)

    def alerta(texto, r=255, g=240, b=200, tr=140, tg=80, tb=0):
        pdf.set_fill_color(r, g, b)
        pdf.set_draw_color(tr, tg, tb)
        pdf.set_text_color(tr, tg, tb)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 7, f"  {_clean(texto)}", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(40, 40, 40)
        pdf.ln(1)

    # ══════════════════════════════════════════════════════════
    # PORTADA
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    pdf.set_fill_color(10, 25, 55)
    pdf.rect(0, 0, 210, 65, "F")
    pdf.set_xy(0, 8)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 13, "REPORTE DETALLADO DE TRADING", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(140, 195, 255)
    pdf.cell(0, 9, f"Periodo: {start}  al  {end}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(195, 218, 255)
    pdf.cell(0, 7, "Bot Algoritmico con ML  |  Paper Trading  |  Alpaca Markets", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(255, 220, 100)
    pdf.cell(0, 7, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(40, 40, 40)
    pdf.ln(20)

    # KPIs portada
    pnl_st = "ok" if total_pnl >= 0 else "error"
    pnl_total_st = "ok" if ctx['pnl_total'] >= 0 else "error"
    wr_st = "ok" if win_rate >= 50 else "warning" if win_rate >= 30 else "error"
    profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    kv("Capital inicial", "$100,000.00 USD", "info")
    kv("Equity actual", f"${ctx['equity']:,.2f} USD", pnl_total_st)
    kv("Retorno total", f"${ctx['pnl_total']:+,.2f} ({ctx['pnl_total']/1000:.2f}%)", pnl_total_st)
    kv("PnL realizado (periodo)", f"${total_pnl:+,.2f}", pnl_st)
    kv("Win Rate", f"{win_rate:.1f}%  ({win_count} wins / {loss_count} losses)", wr_st)
    kv("Promedio ganancia", f"${avg_win:+,.2f} por trade ganador", "ok")
    kv("Promedio perdida", f"${avg_loss:+,.2f} por trade perdedor", "error")
    kv("Profit Factor", f"{profit_factor:.2f}x  (avg_win / avg_loss)", "ok" if profit_factor > 1 else "error")
    kv("Trades totales", f"{len(trades)}  ({len(buys)} compras + {len(sells)} ventas)", "info")
    kv("Dias activos", f"{len(trades_by_day)} dias con operaciones", "info")
    kv("Stop-losses activados", f"{len(stop_losses)}", "error" if stop_losses else "ok")
    kv("ML promedio en compras", f"{avg_ml:.2f}  (rango: {min(ml_probs):.2f} - {max(ml_probs):.2f})" if ml_probs else "N/A", "info")
    kv("Cash disponible", f"${ctx['cash']:,.2f}", "info")
    kv("Modo", "PAPER TRADING -- simulacion con Alpaca", "info")

    # ══════════════════════════════════════════════════════════
    # 1. RESUMEN EJECUTIVO
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    titulo("1.  RESUMEN EJECUTIVO DEL PERIODO")

    subtitulo("1.1  Rendimiento general")
    cuerpo(
        f"Durante el periodo del {start} al {end}, el bot de trading opero "
        f"con un capital de $100,000 USD en modo Paper Trading. El equity crecio "
        f"de $100,000 a ${ctx['equity']:,.2f}, generando un retorno total de "
        f"${ctx['pnl_total']:+,.2f} (+{ctx['pnl_total']/1000:.2f}%). "
        f"Se ejecutaron {len(trades)} operaciones en total: {len(buys)} compras y "
        f"{len(sells)} ventas, distribuidas en {len(trades_by_day)} dias de mercado. "
        f"El PnL realizado (trades cerrados con ganancia/perdida confirmada) fue de "
        f"${total_pnl:+,.2f} con un win rate del {win_rate:.1f}%."
    )

    pdf.ln(2)
    subtitulo("1.2  Por que estos resultados?")
    cuerpo(
        "El rendimiento positivo se explica por tres factores principales: "
        "(1) El bot opero durante una transicion de mercado BEAR a BULL que ocurrio "
        "alrededor del 8-9 de abril, donde el VIX bajo de ~25 a ~17, lo cual favorecio "
        "las compras contrarian que el bot ejecuto en zona de Extreme Fear. "
        "(2) La senal RSI+BB superior funciono como mecanismo efectivo de toma de ganancias, "
        "capturando movimientos cortos de 1-3 dias en acciones de tech y finanzas. "
        "(3) El sector de energia fue la principal debilidad: los 3 stop-losses activados "
        "(XOM, USO, COP) sumaron -$1,098 en perdidas, opacando las ganancias de otros sectores."
    )

    # ══════════════════════════════════════════════════════════
    # 2. CONTEXTO DE MERCADO
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    titulo("2.  CONTEXTO DE MERCADO DURANTE EL PERIODO", 20, 100, 60)

    subtitulo("2.1  Evolucion del VIX y Fear & Greed")
    cuerpo(
        "El mercado mostro una evolucion clara de MIEDO a CALMA durante el periodo. "
        "El VIX cayo de 24.66 el 1 de abril a 17.12 el 17 de abril -- una compresion "
        "de volatilidad del 30% que es tipica de una recuperacion de mercado. El Fear & Greed "
        "Index se mantuvo en EXTREME FEAR (8-23) durante casi todo el periodo, mejorando "
        "apenas a FEAR (29) el 19 de abril. Esto creo condiciones ideales para estrategias "
        "contrarian de compra, que es exactamente lo que el bot hizo."
    )

    if daily_equity:
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_fill_color(15, 45, 110)
        pdf.set_text_color(255, 255, 255)
        for h, w in [("Fecha",25),("Equity",30),("VIX",18),("F&G",18),("Regimen",25),("Nota",74)]:
            pdf.cell(w, 6, h, border=1, fill=True, align="C")
        pdf.ln()
        pdf.set_font("Helvetica", "", 8)
        for i, d in enumerate(daily_equity):
            pdf.set_fill_color(245,248,255) if i%2==0 else pdf.set_fill_color(235,240,255)
            pdf.set_text_color(40, 40, 40)
            pdf.cell(25, 5.5, d["date"], border=1, fill=True, align="C")
            eq_str = f"${d['equity']:,.0f}" if d.get("equity") else "-"
            pdf.cell(30, 5.5, eq_str, border=1, fill=True, align="C")
            vix_str = f"{d['vix']:.1f}" if d.get("vix") else "-"
            regime_colors = {"BULL":(0,130,50),"BEAR":(170,15,15),"SIDEWAYS":(180,110,0),"PANIC":(200,0,0)}
            pdf.cell(18, 5.5, vix_str, border=1, fill=True, align="C")
            fg_str = str(d['fg']) if d.get("fg") else "-"
            pdf.cell(18, 5.5, fg_str, border=1, fill=True, align="C")
            reg = d.get("regime","?")
            rc = regime_colors.get(reg, (100,100,100))
            pdf.set_text_color(*rc)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(25, 5.5, reg, border=1, fill=True, align="C")
            pdf.set_text_color(60, 60, 60)
            pdf.set_font("Helvetica", "", 7)
            nota = ""
            if d.get("vix") and d["vix"] > 24: nota = "VIX elevado - mercado nervioso"
            elif d.get("regime") == "BULL": nota = "Tendencia alcista confirmada"
            elif d.get("regime") == "BEAR": nota = "Tendencia bajista - defensivo"
            pdf.cell(74, 5.5, nota, border=1, fill=True)
            pdf.ln()
        pdf.set_text_color(40, 40, 40)

    pdf.ln(3)
    subtitulo("2.2  Transicion de regimen: BEAR -> BULL")
    cuerpo(
        "El evento mas significativo del periodo fue la transicion del regimen BEAR al BULL "
        "alrededor del 8-9 de abril. Los indicadores clave de la transicion fueron: "
        "(1) SPY cruzo por encima de su SMA50, (2) el ADX (fuerza de tendencia) bajo de ~40 "
        "a ~27 indicando debilitamiento de la tendencia bajista, (3) la amplitud del mercado "
        "(breadth) subio de 34.9% a 60-63% indicando mas acciones subiendo que bajando. "
        "El bot detecto esta transicion y ajusto su comportamiento: en modo BEAR (1-6 abril) "
        "fue mas conservador con min_score alto, mientras que en modo BULL (9+ abril) la senal "
        "'Mercado: COMPRAR' se activo y el bot fue mas agresivo en sus compras."
    )

    pdf.ln(2)
    subtitulo("2.3  Impacto del Fear & Greed en las decisiones")
    cuerpo(
        "El Fear & Greed Index estuvo en EXTREME FEAR (valores 8-23) durante todo el periodo. "
        "Esto impacto al bot de dos formas: (1) la senal 'comprar_agresivo' se activo "
        "frecuentemente porque VIX bajo + F&G bajo es interpretado como oportunidad contrarian, "
        "y (2) el min_score de compra se redujo, permitiendo que compras con menos senales "
        "tecnicas fueran ejecutadas. Esto resulto en 29 compras durante el periodo, muchas "
        "con ML entre 0.47-0.67 que en condiciones normales no habrian pasado el filtro."
    )

    # ══════════════════════════════════════════════════════════
    # 3. HISTORIAL COMPLETO DE TRADES
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    titulo("3.  HISTORIAL COMPLETO DE OPERACIONES")

    subtitulo(f"3.1  {len(trades)} trades ejecutados ({len(buys)} compras, {len(sells)} ventas)")

    col_w = [22, 13, 14, 16, 17, 18, 90]
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_fill_color(10, 25, 55)
    pdf.set_text_color(255, 255, 255)
    for h, w in zip(["Fecha","Hora","Accion","Simbolo","Precio","Qty/PnL","Razon de la decision"], col_w):
        pdf.cell(w, 6, h, border=1, fill=True, align="C")
    pdf.ln()

    prev_day = ""
    for idx, t in enumerate(trades):
        ts = t.get("timestamp", "")
        fecha = ts[:10]
        hora = ts[11:16]
        action = t.get("action", "").upper()
        sym = t.get("symbol", "")
        price = float(t.get("price", 0))
        qty = t.get("qty", "")
        reason = t.get("reason", "")
        pnl = _parse_pnl(reason)
        is_sell = action == "SELL"
        is_stop = "Stop-loss" in reason

        # Separador visual entre dias
        if fecha != prev_day and prev_day != "":
            pdf.set_draw_color(100, 150, 200)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        prev_day = fecha

        if is_stop:
            pdf.set_fill_color(255, 230, 230)
        elif is_sell:
            pdf.set_fill_color(240, 240, 255)
        else:
            pdf.set_fill_color(240, 255, 240) if idx%2==0 else pdf.set_fill_color(232, 248, 232)

        pdf.set_text_color(40, 40, 40)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(col_w[0], 5.5, fecha, border=1, fill=True, align="C")
        pdf.cell(col_w[1], 5.5, hora, border=1, fill=True, align="C")

        pdf.set_text_color(160,15,15) if is_sell else pdf.set_text_color(0,130,50)
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(col_w[2], 5.5, action, border=1, fill=True, align="C")

        pdf.set_text_color(10, 55, 115)
        pdf.cell(col_w[3], 5.5, sym, border=1, fill=True, align="C")

        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(col_w[4], 5.5, f"${price:.2f}", border=1, fill=True, align="C")

        if pnl is not None:
            c = (0,130,50) if pnl >= 0 else (180,15,15)
            pdf.set_text_color(*c)
            pdf.set_font("Helvetica", "B", 7)
            pdf.cell(col_w[5], 5.5, f"${pnl:+.0f}", border=1, fill=True, align="C")
        else:
            pdf.cell(col_w[5], 5.5, str(qty), border=1, fill=True, align="C")

        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(50, 50, 50)
        r_short = reason.replace("[SCANNER] ", "")[:60]
        pdf.cell(col_w[6], 5.5, _clean(r_short), border=1, fill=True)
        pdf.ln()

    pdf.set_text_color(40, 40, 40)
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 7.5)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Verde=Compra | Azul=Venta con ganancia/tecnica | Rojo=Stop-loss | Linea=cambio de dia", new_x="LMARGIN", new_y="NEXT")

    # ══════════════════════════════════════════════════════════
    # 4. CRONOLOGIA DIA POR DIA
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    titulo("4.  CRONOLOGIA DIA POR DIA -- QUE PASO Y POR QUE")

    daily_narratives = {
        "2026-04-01": (
            "Sin trades -- Mercado en BEAR + VIX=24.66",
            "El bot detecto regimen BEAR con VIX elevado (24.66) y F&G=8 (Extreme Fear). "
            "Con todas las 12 posiciones ocupadas y la senal de mercado en modo defensivo "
            "(solo defensivos permitidos en BEAR+VIX>25), el bot decidio mantener las "
            "posiciones existentes sin nuevas compras. No se activaron senales de venta "
            "porque las posiciones no alcanzaron los umbrales de stop-loss ni take-profit."
        ),
        "2026-04-02": (
            "PnL +$131.92 -- Posiciones suben en mercado cauteloso",
            "VIX=25.22 (elevado), F&G=12. El bot se mantuvo en modo defensivo. "
            "No ejecuto nuevos trades pero las posiciones existentes subieron ligeramente, "
            "generando +$131.92 de PnL no realizado. El regimen siguio en BEAR."
        ),
        "2026-04-06": (
            "Rotacion activa: 4 ventas + 3 compras",
            "Primer dia con actividad significativa. El bot vendio GOOGL ($298.74, RSI+BB superior), "
            "ABT ($102.29, MACD bajista) y AAPL ($259.23, RSI+BB superior) porque alcanzaron "
            "la banda superior de Bollinger indicando sobrecompra a corto plazo. "
            "Compro QQQ a $586.07 (ML=0.39 bajo, pero score tecnico alcanzo minimo) y la vendio "
            "1 hora despues a $588.20 con ganancia rapida de +$21.30 (ML venta fuerte). "
            "Tambien compro PFE ($27.89, ML=0.69) y MRK ($120.85, ML=0.68) en sector salud."
        ),
        "2026-04-08": (
            "Venta exitosa de MRK: +$132.60",
            "MRK subio de $120.85 (compra 6/4) a $123.40 en 2 dias. La senal RSI+BB superior "
            "detecto que el precio habia llegado a la banda superior de Bollinger Band, indicando "
            "sobrecompra temporal. El bot vendio automaticamente asegurando +$132.60 de ganancia. "
            "Este es un ejemplo del patron que mejor funciono: compra en sobreventa, venta rapida "
            "en sobrecompra en 1-3 dias."
        ),
        "2026-04-09": (
            "Pivot a energia: XOM, CVX, USO compradas con ML=0.80-0.83",
            "DIA CRITICO: El regimen cambio de BEAR a BULL por primera vez (breadth=69.8%). "
            "El ML dio las probabilidades mas altas del periodo a sector energia: XOM=0.83, "
            "CVX=0.83, USO=0.80. VIX=19.88 (bajo). El bot vendio MCD ($310.61) y compro "
            "agresivamente energia. DECISION CONTROVERSAL: estas 3 compras de energia "
            "terminaron siendo las peores del periodo (2 de 3 activaron stop-loss)."
        ),
        "2026-04-10": (
            "PnL -$135.50 -- Peor dia del periodo",
            "Las posiciones bajaron generando -$135.50. Se vendio MS ($178.14, RSI+BB superior) "
            "y se compro MSFT ($371.16, ML=0.77). La compra de MSFT resulto ser la mejor decision: "
            "se vendio 3 dias despues a $380.94 con ganancia de +$166.35."
        ),
        "2026-04-13": (
            "Mejor dia: +$280.51 con 6 trades",
            "Vendio MSFT a $380.94 (+$166.35 en 3 dias), TQQQ y AXP por RSI+BB superior. "
            "Compro ABBV ($203.64, RSI=25 muy bajo), GLD ($435.12, rebote BB inferior, ML=0.80) "
            "y UNH ($311.53, ML=0.59). El patron RSI+BB superior como senal de venta volvio a "
            "demostrar su efectividad capturando ganancias rapidas."
        ),
        "2026-04-14": (
            "Reestructuracion masiva: 7 ventas + 8 compras",
            "El dia mas activo del periodo. Se vendieron 7 posiciones incluyendo el stop-loss "
            "de XOM (-$262.40, comprado el 9/4 a $155.06, salio a $148.66 = -4.1%). "
            "UNH genero +$125.00, GLD +$93.03. Se rebalanceo el portfolio comprando JPM, "
            "GOOGL, MSFT, BAC, C, MS, IWM y COP. DIA complejo con compra rapida de DIA "
            "a $485.27 y venta 1 hora despues a $484.67 (-$7.80, senal falsa)."
        ),
        "2026-04-15": (
            "Dia de ganancias: MS +$255.85, MSFT +$217.36",
            "Las compras del dia anterior dieron frutos. MS (compra $184.03) subio a $191.34 "
            "(+$255.85 en 35 acciones en 1 dia). MSFT (compra $394.44) subio a $408.02 "
            "(+$217.36 en 16 acciones en 1 dia). IWM genero un modesto +$16.08. "
            "Nuevas compras: UNH ($312.12), GLD ($441.24), MS de nuevo ($192.09)."
        ),
        "2026-04-16": (
            "Tranquilo: GOOGL +$84.84",
            "Solo 2 trades. GOOGL (compra $332.91 el 14/4) se vendio a $337.37 (+$84.84 "
            "en 2 dias por RSI+BB superior). Se recompro IWM ($269.27, ML=0.47 bajo). "
            "Dia de consolidacion sin volatilidad significativa."
        ),
        "2026-04-17": (
            "Stop-losses dolorosos: USO -$571.97, COP -$264.06",
            "El peor dia en stop-losses del periodo. USO (compra $124.99 el 9/4) colapso "
            "a $113.77 (-9.0%), la mayor perdida individual. COP (compra $118.62 el 14/4) "
            "salio a $113.73 (-4.1%). AMBAS eran energia/petroleo. En contraste, JPM genero "
            "+$47.20, C +$127.15, GLD +$80.57 y GOOGL +$29.83. El bot RE-COMPRO USO "
            "inmediatamente a $113.43 despues del stop-loss -- decision cuestionable porque "
            "volver a entrar al mismo precio que te saco el stop-loss ignora la senal de riesgo."
        ),
    }

    for day in sorted(trades_by_day.keys()):
        day_trades = trades_by_day[day]
        day_buys = [t for t in day_trades if t["action"] == "buy"]
        day_sells = [t for t in day_trades if t["action"] == "sell"]
        day_pnls = [_parse_pnl(t.get("reason","")) for t in day_sells if _parse_pnl(t.get("reason","")) is not None]
        day_pnl = sum(day_pnls) if day_pnls else 0

        if day in daily_narratives:
            ntitle, nbody = daily_narratives[day]
        else:
            ntitle = f"{len(day_buys)}B / {len(day_sells)}S"
            nbody = f"Se ejecutaron {len(day_trades)} trades."

        pnl_str = f"  |  PnL: ${day_pnl:+,.2f}" if day_pnls else ""
        pdf.set_fill_color(230, 240, 255)
        pdf.set_draw_color(15, 45, 110)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(10, 55, 115)
        pdf.cell(0, 7, f"  {day}  --  {_clean(ntitle)}{pnl_str}", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        cuerpo(nbody, indent=3)
        pdf.ln(1)

    # Agregar narrativas para dias sin trades (1-5 abril)
    no_trade_days = ["2026-04-01","2026-04-02"]
    for day in no_trade_days:
        if day not in trades_by_day and day in daily_narratives:
            ntitle, nbody = daily_narratives[day]
            pdf.set_fill_color(245, 245, 255)
            pdf.set_draw_color(100, 100, 150)
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.set_text_color(80, 80, 120)
            pdf.cell(0, 7, f"  {day}  --  {_clean(ntitle)}  (sin trades)", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
            cuerpo(nbody, indent=3)
            pdf.ln(1)

    # ══════════════════════════════════════════════════════════
    # 5. ANALISIS DE DECISIONES DEL BOT
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    titulo("5.  ANALISIS DE DECISIONES -- POR QUE COMPRO Y VENDIO")

    subtitulo("5.1  Razones de COMPRA (que senal activo cada compra)")
    cuerpo(
        "El bot usa un sistema de scoring con 8 senales tecnicas. Necesita un minimo "
        "de senales (score) que varia segun el VIX. Ademas, el modelo ML de Random Forest "
        "da una probabilidad de subida que puede overridear el score tecnico. "
        "Cuando el mercado da senal 'COMPRAR agresivo' (F&G bajo + VIX bajo), el bot "
        "reduce el umbral de compra."
    )

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(15, 45, 110)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(120, 6, "Senal de compra", border=1, fill=True)
    pdf.cell(25, 6, "Veces", border=1, fill=True, align="C")
    pdf.cell(45, 6, "% del total", border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 8.5)
    for i, (reason, count) in enumerate(sorted(buy_reasons.items(), key=lambda x: -x[1])):
        pdf.set_fill_color(240,248,240) if i%2==0 else pdf.set_fill_color(232,244,232)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(120, 5.5, _clean(reason), border=1, fill=True)
        pdf.set_text_color(0, 130, 50)
        pdf.cell(25, 5.5, str(count), border=1, fill=True, align="C")
        pct = count / len(buys) * 100 if buys else 0
        pdf.cell(45, 5.5, f"{pct:.0f}%", border=1, fill=True, align="C")
        pdf.ln()
    pdf.set_text_color(40, 40, 40)

    pdf.ln(4)
    subtitulo("5.2  Razones de VENTA (que senal activo cada venta)")
    cuerpo(
        "La mayoria de las ventas fueron por RSI+BB superior: cuando el RSI sube "
        "y el precio toca la banda superior de Bollinger, el bot interpreta sobrecompra "
        "temporal y toma ganancias. Los stop-losses se activan automaticamente al -4% "
        "desde el precio de entrada."
    )

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(15, 45, 110)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(120, 6, "Senal de venta", border=1, fill=True)
    pdf.cell(25, 6, "Veces", border=1, fill=True, align="C")
    pdf.cell(45, 6, "% del total", border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 8.5)
    for i, (reason, count) in enumerate(sorted(sell_reasons.items(), key=lambda x: -x[1])):
        is_stop = "Stop" in reason
        pdf.set_fill_color(255,240,240) if is_stop else (pdf.set_fill_color(240,240,255) if i%2==0 else pdf.set_fill_color(235,235,250))
        pdf.set_text_color(170,15,15) if is_stop else pdf.set_text_color(40,40,40)
        pdf.cell(120, 5.5, _clean(reason), border=1, fill=True)
        pdf.cell(25, 5.5, str(count), border=1, fill=True, align="C")
        pct = count / len(sells) * 100 if sells else 0
        pdf.cell(45, 5.5, f"{pct:.0f}%", border=1, fill=True, align="C")
        pdf.ln()
    pdf.set_text_color(40, 40, 40)

    pdf.ln(4)
    subtitulo("5.3  Evaluacion del modelo ML")
    cuerpo(
        f"El modelo Random Forest asigno probabilidades de compra con promedio de {avg_ml:.2f}. "
        f"Rango: {min(ml_probs):.2f} a {max(ml_probs):.2f}. "
        "Las compras con ML mas alto (0.80+) fueron las de energia el 9/4 (XOM=0.83, CVX=0.83, "
        "USO=0.80) que terminaron siendo las peores del periodo -- todas activaron stop-loss. "
        "En contraste, MSFT fue comprado con ML=0.56-0.77 y genero ganancias consistentes. "
        "Esto sugiere que el ML esta sobrevalorando el sector energia o que sus features "
        "no capturan bien los riesgos especificos del petroleo."
        if ml_probs else "No se detectaron probabilidades ML en las compras del periodo."
    )

    # ══════════════════════════════════════════════════════════
    # 6. RENDIMIENTO POR SECTOR
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    titulo("6.  RENDIMIENTO POR SECTOR", 70, 15, 90)

    subtitulo("6.1  PnL y actividad por sector")

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(15, 45, 110)
    pdf.set_text_color(255, 255, 255)
    for h, w in [("Sector",40),("Trades",18),("Wins",15),("Losses",18),("PnL Total",30),("Veredicto",69)]:
        pdf.cell(w, 6, h, border=1, fill=True, align="C")
    pdf.ln()
    pdf.set_font("Helvetica", "", 8.5)
    for i, (sec, data) in enumerate(sorted(sector_pnl.items(), key=lambda x: -x[1]["total"])):
        is_neg = data["total"] < 0
        pdf.set_fill_color(255,240,240) if is_neg else (pdf.set_fill_color(240,255,240) if i%2==0 else pdf.set_fill_color(232,248,232))
        pdf.set_text_color(40, 40, 40)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(40, 6, _clean(sec), border=1, fill=True)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.cell(18, 6, str(data["trades"]), border=1, fill=True, align="C")
        pdf.set_text_color(0, 130, 50)
        pdf.cell(15, 6, str(data["wins"]), border=1, fill=True, align="C")
        pdf.set_text_color(170, 15, 15)
        pdf.cell(18, 6, str(data["losses"]), border=1, fill=True, align="C")
        c = (0,130,50) if data["total"] >= 0 else (170,15,15)
        pdf.set_text_color(*c)
        pdf.set_font("Helvetica", "B", 8.5)
        pdf.cell(30, 6, f"${data['total']:+,.2f}", border=1, fill=True, align="C")
        pdf.set_text_color(40, 40, 40)
        pdf.set_font("Helvetica", "", 7.5)
        if data["total"] > 100: veredicto = "Rentable - mantener estrategia"
        elif data["total"] > 0: veredicto = "Modesto - revisar sizing"
        elif data["total"] > -100: veredicto = "Marginal - evaluar"
        else: veredicto = "Perdedor - revisar o excluir"
        pdf.cell(69, 6, veredicto, border=1, fill=True)
        pdf.ln()
    pdf.set_text_color(40, 40, 40)

    pdf.ln(3)
    subtitulo("6.2  Analisis detallado por sector")

    cuerpo(
        "TECNOLOGIA: El sector mas exitoso. MSFT fue operado 4 veces con ganancias en cada "
        "round-trip (+$166, +$217). GOOGL genero +$84 y +$29. El patron: comprar en dip "
        "con ML moderado (0.56-0.77), vender en RSI+BB superior en 1-3 dias. La alta liquidez "
        "de estas acciones permite entradas y salidas limpias."
    )
    cuerpo(
        "ENERGIA: El sector perdedor del periodo. Las 3 compras del 9/4 (XOM, CVX, USO) "
        "fueron hechas con las probabilidades ML mas altas (0.80-0.83) pero el sector "
        "sufrio por caida en precios del petroleo. XOM: stop-loss -$262, USO: stop-loss "
        "-$571, COP: stop-loss -$264. Total sector: -$1,098. El ML no tenia features "
        "especificas de commodities (precio crudo, inventarios) para evaluar el riesgo."
    )
    cuerpo(
        "FINANZAS: Rendimiento mixto positivo. MS genero +$255 (la mejor trade individual), "
        "JPM +$47, C +$127. Las acciones financieras se beneficiaron de la transicion BEAR->BULL "
        "y de la caida del VIX. DIA tuvo una trade fallida rapida (-$7.80 en 1 hora)."
    )
    cuerpo(
        "SALUD: MRK fue la estrella con +$132 en 2 dias. UNH +$125. El sector respondio bien "
        "a la estrategia de mean-reversion del bot."
    )
    cuerpo(
        "COMMODITIES/BONOS: GLD genero +$93 y +$80 en dos round-trips. El oro subio durante "
        "el periodo de Extreme Fear, validando la senal contrarian del bot."
    )

    # ══════════════════════════════════════════════════════════
    # 7. ANALISIS DE STOP-LOSSES
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    titulo("7.  ANALISIS DE STOP-LOSSES ACTIVADOS", 140, 25, 10)

    if stop_losses:
        subtitulo(f"7.1  {len(stop_losses)} stop-losses activados en el periodo")
        cuerpo(
            "Los stop-losses son un mecanismo de proteccion automatico que vende una posicion "
            "cuando pierde mas del 4% desde el precio de entrada. Funcionaron correctamente "
            "en los 3 casos, evitando perdidas mayores."
        )

        for i, t in enumerate(stop_losses, 1):
            sym = t.get("symbol","")
            price = float(t.get("price",0))
            reason = t.get("reason","")
            pnl = _parse_pnl(reason) or 0
            fecha = t.get("timestamp","")[:10]

            alerta(
                f"STOP-LOSS #{i}: {sym} vendido a ${price:.2f} el {fecha} | PnL: ${pnl:+,.2f}",
                r=255, g=230, b=230, tr=170, tg=15, tb=15
            )

        pdf.ln(2)
        total_sl = sum(_parse_pnl(t.get("reason","")) or 0 for t in stop_losses)

        subtitulo("7.2  Impacto total de stop-losses")
        kv("Perdida total por stop-losses", f"${total_sl:+,.2f}", "error")
        kv("% del capital afectado", f"{abs(total_sl)/ctx['equity']*100:.2f}%", "warning")
        kv("Sector afectado", "100% Energia (XOM, USO, COP)", "error")

        pdf.ln(2)
        subtitulo("7.3  Por que fallaron estas compras?")
        cuerpo(
            "Las 3 compras de energia fueron ejecutadas con las probabilidades ML mas altas "
            "del periodo (0.80-0.83). Sin embargo, el modelo ML no tiene features especificas "
            "de commodities como precio del crudo (WTI/Brent), inventarios de petroleo, "
            "decisiones OPEC, o correlacion dolar/petroleo. El ML evaluo estas acciones "
            "solo con indicadores tecnicos genericos (RSI, MACD, BB) que no capturan "
            "los drivers fundamentales del sector energia."
        )
        cuerpo(
            "LECCION CLAVE: ML alto no significa seguro. El modelo puede dar alta confianza "
            "basado en patrones historicos que no aplican en el contexto actual. Agregar "
            "features sectoriales y de commodities al modelo ML reduciria este tipo de error."
        )

        pdf.ln(2)
        subtitulo("7.4  Problema: re-compra inmediata de USO post stop-loss")
        alerta(
            "ALERTA: El bot re-compro USO a $113.43 inmediatamente despues del stop-loss a $113.77",
            r=255, g=240, b=200, tr=140, tg=80, tb=0
        )
        cuerpo(
            "Despues de vender USO por stop-loss a $113.77, el bot compro USO de nuevo "
            "a $113.43 en el mismo ciclo. Esto anula el proposito del stop-loss: si el "
            "precio bajo lo suficiente para activar la proteccion, volver a entrar al mismo "
            "precio ignora la senal de riesgo. Se recomienda agregar un 'cooldown' de 3-5 "
            "dias despues de un stop-loss antes de permitir recompra del mismo simbolo."
        )

    # ══════════════════════════════════════════════════════════
    # 8. TOP TRADES DETALLADOS
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    titulo("8.  MEJORES Y PEORES OPERACIONES EXPLICADAS", 15, 80, 50)

    subtitulo("8.1  Top 5 mejores trades (por PnL realizado)")
    sorted_wins = sorted(wins, key=lambda t: _parse_pnl(t.get("reason","")) or 0, reverse=True)[:5]
    for i, t in enumerate(sorted_wins, 1):
        pnl = _parse_pnl(t.get("reason","")) or 0
        sym = t.get("symbol","")
        price = float(t.get("price",0))
        fecha = t.get("timestamp","")[:10]
        reason = t.get("reason","").replace("[SCANNER] ","")

        pdf.set_fill_color(230, 255, 235)
        pdf.set_draw_color(0, 145, 55)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(0, 100, 35)
        pdf.cell(0, 7, f"  #{i}  {sym}  |  ${pnl:+,.2f}  |  Vendido a ${price:.2f} el {fecha}", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(40, 40, 40)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(14)
        pdf.multi_cell(0, 5.5, _clean(f"Senal de venta: {reason}"))
        pdf.ln(1)

    pdf.ln(3)
    subtitulo("8.2  Top 5 peores trades (por PnL realizado)")
    sorted_losses = sorted(losses, key=lambda t: _parse_pnl(t.get("reason","")) or 0)[:5]
    for i, t in enumerate(sorted_losses, 1):
        pnl = _parse_pnl(t.get("reason","")) or 0
        sym = t.get("symbol","")
        price = float(t.get("price",0))
        fecha = t.get("timestamp","")[:10]
        reason = t.get("reason","").replace("[SCANNER] ","")

        pdf.set_fill_color(255, 230, 230)
        pdf.set_draw_color(170, 15, 15)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_text_color(140, 0, 0)
        pdf.cell(0, 7, f"  #{i}  {sym}  |  ${pnl:+,.2f}  |  Vendido a ${price:.2f} el {fecha}", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(40, 40, 40)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_x(14)
        pdf.multi_cell(0, 5.5, _clean(f"Senal de venta: {reason}"))
        pdf.ln(1)

    # ══════════════════════════════════════════════════════════
    # 9. PnL POR SIMBOLO
    # ══════════════════════════════════════════════════════════
    if pnl_by_symbol:
        pdf.add_page()
        titulo("9.  PnL ACUMULADO POR SIMBOLO")

        subtitulo("9.1  Rendimiento de cada simbolo operado")

        pdf.set_font("Helvetica", "B", 8.5)
        pdf.set_fill_color(15, 45, 110)
        pdf.set_text_color(255, 255, 255)
        for h, w in [("Simbolo",22),("Trades cerrados",30),("PnL Total",30),("Promedio",25),("Status",83)]:
            pdf.cell(w, 6, h, border=1, fill=True, align="C")
        pdf.ln()
        pdf.set_font("Helvetica", "", 8.5)
        for i, (sym, total) in enumerate(sorted(pnl_by_symbol.items(), key=lambda x: sum(x[1]), reverse=True)):
            total_p = sum(total)
            avg_p = total_p / len(total)
            is_neg = total_p < 0
            pdf.set_fill_color(255,240,240) if is_neg else (pdf.set_fill_color(240,255,240) if i%2==0 else pdf.set_fill_color(232,248,232))
            pdf.set_text_color(40, 40, 40)
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.cell(22, 6, sym, border=1, fill=True, align="C")
            pdf.set_font("Helvetica", "", 8.5)
            pdf.cell(30, 6, str(len(total)), border=1, fill=True, align="C")
            c = (0,130,50) if total_p >= 0 else (170,15,15)
            pdf.set_text_color(*c)
            pdf.set_font("Helvetica", "B", 8.5)
            pdf.cell(30, 6, f"${total_p:+,.2f}", border=1, fill=True, align="C")
            pdf.cell(25, 6, f"${avg_p:+,.2f}", border=1, fill=True, align="C")
            pdf.set_text_color(60, 60, 60)
            pdf.set_font("Helvetica", "", 7.5)
            if total_p > 150: status = "Excelente - simbolo consistente"
            elif total_p > 50: status = "Bueno - mantener en watchlist"
            elif total_p > 0: status = "Marginal - monitorear"
            elif total_p > -100: status = "Negativo leve - evaluar sizing"
            else: status = "Perdedor significativo - revisar o excluir"
            pdf.cell(83, 6, status, border=1, fill=True)
            pdf.ln()
        pdf.set_text_color(40, 40, 40)

    # ══════════════════════════════════════════════════════════
    # 10. CONCLUSIONES Y RECOMENDACIONES
    # ══════════════════════════════════════════════════════════
    pdf.add_page()
    titulo("10.  CONCLUSIONES Y RECOMENDACIONES", 80, 20, 80)

    subtitulo("10.1  Lo que funciono bien")
    bullet("RSI+BB superior como senal de venta: capturo ganancias rapidas en 1-3 dias consistentemente.", (0,145,55))
    bullet("Compras contrarian en Extreme Fear: el bot compro cuando todos vendian y resulto rentable.", (0,145,55))
    bullet("Diversificacion sectorial: las perdidas en energia fueron compensadas por tech y finanzas.", (0,145,55))
    bullet("MSFT como trade repetible: 4 round-trips, todos rentables. El patron funciona.", (0,145,55))
    bullet("Stop-losses funcionando: protegieron de perdidas mayores en energia (sin ellos, la caida habria sido peor).", (0,145,55))

    pdf.ln(2)
    subtitulo("10.2  Lo que fallo")
    bullet("Sector energia con ML alto: el modelo dio 0.80-0.83 a XOM/CVX/USO y las 3 perdieron.", (180,30,30))
    bullet("Re-compra post stop-loss: comprar USO inmediatamente despues de stop-loss anula la proteccion.", (180,30,30))
    bullet("DIA trade rapida (-$7.80): comprar y vender en 1 hora con ML=0.50 es senal debil.", (180,30,30))
    bullet("ML no tiene features macro: el modelo no distingue entre sectores ni usa datos de commodities.", (180,30,30))

    pdf.ln(2)
    subtitulo("10.3  Recomendaciones para las proximas semanas")

    recs = [
        ("INMEDIATO", "Agregar cooldown de 3-5 dias post stop-loss",
         "Evita re-comprar un simbolo que acaba de activar stop-loss. "
         "Esto habria prevenido la re-compra de USO el 17/4.",
         230, 245, 255, 10, 60, 140),
        ("INMEDIATO", "Subir umbral ML minimo de 0.50 a 0.60",
         "Elimina compras con ML bajo como DIA (0.50) e IWM (0.47) que no generan "
         "retornos significativos.",
         230, 245, 255, 10, 60, 140),
        ("SEMANA 1", "Agregar features de commodities al ML",
         "Incluir precio del WTI/Brent, ratio dolar/petroleo, e inventarios como features "
         "para mejorar las predicciones en sector energia.",
         235, 255, 240, 0, 100, 40),
        ("SEMANA 1", "Limitar exposicion por sector a max 2 posiciones",
         "El 9/4 se compraron 3 posiciones de energia simultaneamente. Limitar a 2 por sector "
         "reduciria la correlacion y las perdidas en cascada por stop-losses.",
         235, 255, 240, 0, 100, 40),
        ("SEMANA 2", "Implementar trailing stop del 3%",
         "Las posiciones ganadoras como MS (+$255) podrian haber capturado mas si el stop "
         "se hubiera ajustado al alza. Un trailing stop del 3% protegeria ganancias.",
         255, 248, 235, 140, 80, 0),
        ("SEMANA 2", "Replicar patron MSFT en mas blue chips",
         "MSFT demostro que la estrategia de compra en dip + venta en RSI+BB funciona "
         "consistentemente. Priorizar AAPL, GOOGL, AMZN con la misma logica.",
         255, 248, 235, 140, 80, 0),
    ]

    for fase, titulo_rec, desc, bg_r, bg_g, bg_b, tc_r, tc_g, tc_b in recs:
        pdf.set_fill_color(bg_r, bg_g, bg_b)
        pdf.set_draw_color(tc_r, tc_g, tc_b)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(tc_r, tc_g, tc_b)
        pdf.cell(0, 7, f"  [{fase}]  {_clean(titulo_rec)}", border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(40, 40, 40)
        pdf.set_x(14)
        pdf.multi_cell(0, 5.5, _clean(desc))
        pdf.ln(1)

    # ── VEREDICTO FINAL ─────────────────────────────────────
    pdf.ln(3)
    separador()
    is_positive = ctx['pnl_total'] >= 0
    if is_positive:
        pdf.set_fill_color(220, 245, 225)
        pdf.set_draw_color(0, 145, 55)
        pdf.set_text_color(0, 100, 35)
    else:
        pdf.set_fill_color(255, 235, 235)
        pdf.set_draw_color(170, 15, 15)
        pdf.set_text_color(140, 0, 0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 9,
        f"  VEREDICTO: Retorno +{ctx['pnl_total']/1000:.2f}% en {len(trades_by_day)} dias  |  "
        f"Win rate {win_rate:.0f}%  |  Estrategia viable, optimizar energia y ML",
        border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(40, 40, 40)

    # ── PIE FINAL ───────────────────────────────────────────
    pdf.ln(5)
    separador()
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 5,
        f"Reporte generado el {datetime.now().strftime('%d/%m/%Y %H:%M')}. "
        f"Periodo analizado: {start} al {end}. "
        f"{len(trades)} operaciones documentadas con explicacion de cada decision. "
        "Paper Trading con Alpaca Markets. No constituye asesoramiento financiero.",
        align="C"
    )

    pdf_path = f"reports/weekly_{start}_to_{end}.pdf"
    pdf.output(pdf_path)
    print(f"\nPDF detallado guardado en: {pdf_path}")
    return pdf_path


# ══════════════════════════════════════════════════════════════
# REPORTE MENSUAL
# ══════════════════════════════════════════════════════════════
def monthly_report(executor: Executor = None):
    """Genera un reporte mensual resumido con análisis IA."""
    if executor is None:
        executor = Executor()

    ctx   = _portfolio_context(executor)
    plans = _load_plans()
    today = datetime.now(timezone.utc).date()
    month = today.strftime("%Y-%m")

    all_trades = _load_all_trades()
    sells = [t for t in all_trades if t.get("action") == "sell"]
    wins  = [t for t in sells if float(t.get("value", 0)) > 0]
    total_pnl = sum(float(t.get("value", 0)) - float(t.get("price", 0)) * float(t.get("qty", 0) or 0)
                    for t in sells)

    system = f"""
Eres el analista del trading bot. Genera el reporte mensual de {month}.

PORTFOLIO:
- Equity: ${ctx['equity']:,.2f} | PnL vs inicio: ${ctx['pnl_total']:+,.2f}
- Win rate: {ctx['win_rate']:.1f}% sobre {len(sells)} ventas cerradas
- Total operaciones históricas: {ctx['total_trades']}
- Posiciones abiertas: {ctx['positions'] if ctx['positions'] else 'ninguna'}

MISIÓN: {plans.get('mision_principal', 'Maximizar retorno con riesgo controlado')}
PLANES: {json.dumps(plans.get('planes', []), ensure_ascii=False)}

Genera el reporte mensual con:
## 1. RESUMEN DEL MES
## 2. RENDIMIENTO VS OBJETIVOS
## 3. LECCIONES APRENDIDAS
## 4. PLAN PARA EL PRÓXIMO MES

Responde en español con datos concretos.
"""

    print(f"\n{'═'*58}")
    print(f"  📅  REPORTE MENSUAL — {month}")
    print(f"{'═'*58}\n")
    print("⏳ Generando análisis mensual con IA...\n")

    analysis = _claude([{"role": "user", "content": "Genera el reporte mensual."}], system, max_tokens=2500)
    print(analysis)

    txt_path = f"reports/monthly_{month}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"REPORTE MENSUAL — {month}\n{'='*50}\n\n")
        f.write(f"Equity: ${ctx['equity']:,.2f} | PnL: ${ctx['pnl_total']:+,.2f}\n\n")
        f.write(analysis)
    print(f"\n✅ Reporte mensual guardado en: {txt_path}")

    if PDF_OK:
        pdf_path = f"reports/monthly_{month}.pdf"
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_fill_color(30, 60, 120)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 14, _clean(f"Reporte Mensual — {month}"), ln=True, fill=True, align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(4)
        pdf.set_font("Helvetica", "", 10)
        for line in analysis.split("\n"):
            line = line.strip()
            if not line:
                pdf.ln(2)
                continue
            if line.startswith("##"):
                pdf.ln(3)
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_fill_color(220, 230, 255)
                pdf.cell(0, 7, _clean(line.replace("##", "").strip()), ln=True, fill=True)
                pdf.set_font("Helvetica", "", 10)
            else:
                line = _clean(line)
                while len(line) > 110:
                    pdf.cell(0, 5, line[:110], ln=True)
                    line = line[110:]
                if line:
                    pdf.cell(0, 5, line, ln=True)
        pdf.output(pdf_path)
        print(f"✅ PDF mensual guardado en: {pdf_path}")

    return analysis


# ══════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--daily",   action="store_true", help="Reporte diario PDF")
    p.add_argument("--weekly",  action="store_true", help="Reporte semanal PDF")
    p.add_argument("--monthly", action="store_true", help="PDF mensual")
    p.add_argument("--from",    dest="start_date", type=str, help="Fecha inicio (YYYY-MM-DD)")
    p.add_argument("--to",      dest="end_date",   type=str, help="Fecha fin (YYYY-MM-DD)")
    p.add_argument("--advisor", action="store_true", help="Chat con asesor IA")
    p.add_argument("--planes",  action="store_true", help="Gestionar planes")
    p.add_argument("--plan",    type=str,            help="Analizar una idea")
    a = p.parse_args()

    ex = Executor()

    if a.daily:
        daily_report(ex)
    elif a.weekly:
        weekly_report(ex, start=a.start_date, end=a.end_date)
    elif a.monthly:
        monthly_report(ex)
    elif a.advisor:
        interactive_advisor(ex)
    elif a.planes:
        manage_plans(ex)
    elif a.plan:
        # Análisis rápido de una idea
        ctx  = _portfolio_context(ex)
        news = _get_market_news()
        sys_p = f"""
Asesor de trading. Portfolio: ${ctx['equity']:,.2f} | PnL: ${ctx['pnl_total']:+,.2f}
Estrategia: {config.SYMBOL} {config.TIMEFRAME} ML+RSI+BB
Noticias: {news}
Evalúa la idea: ÓPTIMA/VIABLE/NO RECOMENDADA + razones + riesgos + alternativa.
Responde en español.
"""
        resp = _claude([{"role":"user","content":a.plan}], sys_p)
        print(f"\n🧠 ANÁLISIS:\n{resp}\n")
        with open(f"reports/plan_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                  "w", encoding="utf-8") as f:
            f.write(f"IDEA: {a.plan}\n\nANÁLISIS IA:\n{resp}\n")
        print("✅ Guardado en reports/")
    else:
        # Menú principal
        print(f"\n{'═'*45}")
        print(f"  📊  SISTEMA DE INFORMES Y ASESOR IA")
        print(f"{'═'*45}")
        print("  1. Reporte diario completo (PDF)")
        print("  2. Reporte semanal (PDF)")
        print("  3. Chat con asesor IA")
        print("  4. Gestionar planes y misión")
        print("  5. Analizar una idea rápida")
        print(f"{'═'*45}")
        opt = input("Elige (1-5): ").strip()
        if opt == "1":   daily_report(ex)
        elif opt == "2":
            s = input("Fecha inicio (YYYY-MM-DD) [Enter=ultimas 2 semanas]: ").strip() or None
            e = input("Fecha fin (YYYY-MM-DD) [Enter=hoy]: ").strip() or None
            weekly_report(ex, start=s, end=e)
        elif opt == "3": interactive_advisor(ex)
        elif opt == "4": manage_plans(ex)
        elif opt == "5":
            idea = input("Tu idea o pregunta: ")
            ctx  = _portfolio_context(ex)
            sys_p = f"Asesor trading. Portfolio ${ctx['equity']:,.2f}. Evalúa en español: ÓPTIMA/VIABLE/NO RECOMENDADA + razones."
            print(f"\n🧠 {_claude([{'role':'user','content':idea}], sys_p)}\n")