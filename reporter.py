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
    p.add_argument("--monthly", action="store_true", help="PDF mensual")
    p.add_argument("--advisor", action="store_true", help="Chat con asesor IA")
    p.add_argument("--planes",  action="store_true", help="Gestionar planes")
    p.add_argument("--plan",    type=str,            help="Analizar una idea")
    a = p.parse_args()

    ex = Executor()

    if a.daily:
        daily_report(ex)
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
        print("  2. Chat con asesor IA")
        print("  3. Gestionar planes y misión")
        print("  4. Analizar una idea rápida")
        print(f"{'═'*45}")
        opt = input("Elige (1-4): ").strip()
        if opt == "1":   daily_report(ex)
        elif opt == "2": interactive_advisor(ex)
        elif opt == "3": manage_plans(ex)
        elif opt == "4":
            idea = input("Tu idea o pregunta: ")
            ctx  = _portfolio_context(ex)
            sys_p = f"Asesor trading. Portfolio ${ctx['equity']:,.2f}. Evalúa en español: ÓPTIMA/VIABLE/NO RECOMENDADA + razones."
            print(f"\n🧠 {_claude([{'role':'user','content':idea}], sys_p)}\n")