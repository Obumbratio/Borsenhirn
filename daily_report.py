"""
daily_report.py - Reporte diario del bot de trading.
Genera un PDF con movimientos, P&L, bugs y arreglos del dia.
"""
import os, json, csv
from datetime import datetime
from fpdf import FPDF

OUTPUT_PATH = "reports/reporte_diario_{}.pdf"
os.makedirs("reports", exist_ok=True)


def clean(text: str) -> str:
    replacements = {
        "\u2014": "-", "\u2013": "-", "\u2019": "'", "\u2018": "'",
        "\u201c": '"', "\u201d": '"', "\u2022": "*", "\u2026": "...",
        "\u2192": "->", "\u2191": "^", "\u2193": "v", "\u2713": "OK",
        "\u274c": "X", "\u2705": "OK", "\u26a0": "!", "\u2b50": "*",
        "\u2764": "[v]", "\u2757": "!", "\u00e9": "e", "\u00f3": "o",
        "\u00ed": "i", "\u00fa": "u", "\u00e1": "a", "\u00f1": "n",
        "\u00e0": "a", "\u00e8": "e", "\u00ec": "i", "\u00f2": "o",
        "\u00f9": "u", "\u00e2": "a", "\u00ea": "e", "\u00ee": "i",
        "\u00f4": "o", "\u00fb": "u", "\u00fc": "u", "\u00c9": "E",
        "\u00d3": "O", "\u00cd": "I", "\u00da": "U", "\u00c1": "A",
        "\u00d1": "N", "\u00bf": "?", "\u00a1": "!",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def load_trades(date_str):
    trades = []
    path = "logs/trades.csv"
    if not os.path.exists(path):
        return trades
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["timestamp"].startswith(date_str):
                trades.append(row)
    return trades


def load_memory():
    path = "reports/bot_memory.json"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}


class PDF(FPDF):
    def header(self):
        self.set_fill_color(10, 35, 80)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 8, "REPORTE DIARIO - TRADING BOT ALGORITMICO", ln=True, fill=True, align="C")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6,
            f"Pagina {self.page_no()} | Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            align="C")

    def section_title(self, title):
        self.ln(5)
        self.set_fill_color(10, 35, 80)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 9, f"  {clean(title)}", ln=True, fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def subsection(self, title):
        self.ln(3)
        self.set_fill_color(200, 215, 245)
        self.set_text_color(10, 35, 80)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, f"  {clean(title)}", ln=True, fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def body(self, text):
        self.set_font("Helvetica", "", 10)
        for line in text.strip().split("\n"):
            line = clean(line.rstrip())
            if not line:
                self.ln(2)
                continue
            while len(line) > 108:
                self.cell(0, 5, line[:108], ln=True)
                line = line[108:]
            if line:
                self.cell(0, 5, line, ln=True)

    def table(self, headers, rows, col_widths):
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(200, 215, 245)
        for h, w in zip(headers, col_widths):
            self.cell(w, 7, clean(str(h)), border=1, fill=True, align="C")
        self.ln()
        self.set_font("Helvetica", "", 9)
        for i, row in enumerate(rows):
            fill = i % 2 == 0
            self.set_fill_color(245, 248, 255) if fill else self.set_fill_color(255, 255, 255)
            for cell, w in zip(row, col_widths):
                self.cell(w, 6, clean(str(cell)), border=1, fill=fill)
            self.ln()
        self.ln(3)

    def callout(self, label, text, r=230, g=245, b=220):
        self.set_fill_color(r, g, b)
        self.set_font("Helvetica", "B", 10)
        self.cell(0, 7, f"  {clean(label)}", ln=True, fill=True)
        self.set_font("Helvetica", "", 10)
        for line in text.strip().split("\n"):
            line = clean(line.strip())
            if not line:
                self.ln(1)
                continue
            while len(line) > 105:
                self.cell(0, 5, "    " + line[:105], ln=True, fill=True)
                line = line[105:]
            self.cell(0, 5, "    " + line, ln=True, fill=True)
        self.ln(2)


def build(date_str=None):
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")

    trades   = load_trades(date_str)
    memory   = load_memory()
    perf_hist = memory.get("performance_history", [])
    today_perf = next((r for r in perf_hist if r.get("date") == date_str), {})
    entry_prices = memory.get("daily_state", {}).get("entry_prices", {})

    buys  = [t for t in trades if t["action"] == "buy"]
    sells = [t for t in trades if t["action"] == "sell"]

    # PnL de trades cerrados
    spy_buy_total  = sum(float(t["value"]) for t in trades
                         if t["action"]=="buy" and t["symbol"]=="SPY")
    spy_sell_total = sum(float(t["value"]) for t in trades
                         if t["action"]=="sell" and t["symbol"]=="SPY")
    spy_pnl = spy_sell_total - spy_buy_total if spy_buy_total > 0 else 0.0

    nvda_sells = [t for t in trades if t["action"]=="sell" and t["symbol"]=="NVDA"]
    nvda_buys  = [t for t in trades if t["action"]=="buy"  and t["symbol"]=="NVDA"]
    nvda_pnl   = -12.45  # calculado manualmente (131*182.275 - 131*182.37)

    total_closed_pnl = spy_pnl + nvda_pnl
    day_pnl          = today_perf.get("pnl", -156.32)
    start_equity     = memory.get("daily_state", {}).get("day_start_equity", 100027.86)
    end_equity       = today_perf.get("equity", start_equity + day_pnl)

    scanner_capital  = sum(float(t["value"]) for t in buys
                           if "[SCANNER]" in t.get("reason","") and t["symbol"]!="NVDA")
    open_positions   = len(entry_prices)

    out_path = OUTPUT_PATH.format(date_str)

    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=18)

    # ── PORTADA ─────────────────────────────────────────────────
    pdf.add_page()
    pdf.ln(15)
    pdf.set_fill_color(10, 35, 80)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 14, "REPORTE DIARIO DE OPERACIONES", ln=True, fill=True, align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, f"Trading Bot Algoritmico con IA  |  {date_str}", ln=True, fill=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    # KPIs en portada
    pdf.set_font("Helvetica", "B", 11)
    kpis = [
        ("Equity inicio del dia",  f"${start_equity:,.2f}"),
        ("Equity al cierre",       f"${end_equity:,.2f}"),
        ("PnL neto del dia",       f"${day_pnl:+,.2f}  ({day_pnl/start_equity*100:+.2f}%)"),
        ("Total de trades",        str(len(trades))),
        ("Posiciones cerradas",    str(len(sells))),
        ("Posiciones abiertas",    str(open_positions)),
        ("Capital desplegado",     f"${scanner_capital:,.0f}"),
        ("Contexto de mercado",    "Fear & Greed = 28 (Miedo)  |  VIX = 22.7 - 23.5"),
    ]
    for k, v in kpis:
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(65, 8, f"  {clean(k)}:", border="B")
        color = (180, 0, 0) if "PnL" in k and day_pnl < 0 else (0, 100, 0) if "PnL" in k else (0, 0, 0)
        pdf.set_text_color(*color)
        pdf.set_font("Helvetica", "", 11)
        pdf.cell(0, 8, f"  {clean(v)}", border="B", ln=True)
        pdf.set_text_color(0, 0, 0)

    # ── SECCION 1: CRONOLOGIA ────────────────────────────────────
    pdf.add_page()
    pdf.section_title("1. CRONOLOGIA DE OPERACIONES")

    pdf.subsection("Fase 1 — Madrugada (7pm–11pm PT domingo)  [BUG]")
    pdf.callout(
        "BUG DETECTADO: Triple compra de SPY fuera de horario",
        "El bot estaba corriendo con la version antigua del codigo (modo SEGURO).\n"
        "Compro SPY 3 veces a las 7:12pm, 7:30pm y 9:33pm PT del domingo porque\n"
        "no verificaba si ya tenia la posicion abierta, ni si el mercado estaba cerrado.\n"
        "Total bloqueado: $74,198 que no pudieron usarse en la apertura del lunes.",
        r=255, g=235, b=200
    )
    pdf.table(
        ["Hora (PT)", "Accion", "Simbolo", "Precio", "Cantidad", "Valor", "Razon"],
        [
            ["7:12pm dom", "BUY", "SPY", "$668.45", "37", "$24,733", "SEGURO - RSI bajo + Rebote BB"],
            ["7:30pm dom", "BUY", "SPY", "$668.45", "37", "$24,733", "SEGURO - DUPLICADO"],
            ["9:33pm dom", "BUY", "SPY", "$668.45", "37", "$24,733", "SEGURO - DUPLICADO"],
        ],
        [22, 15, 20, 20, 20, 22, 71]
    )

    pdf.subsection("Fase 2 — Manana (5:48am PT)  — Cierre de SPY y NVDA")
    pdf.table(
        ["Hora (PT)", "Accion", "Simbolo", "Precio", "Cantidad", "Valor", "PnL"],
        [
            ["5:48am", "SELL", "SPY",  "$674.24", "111", "$74,841", f"${spy_pnl:+,.2f}"],
            ["5:48am", "SELL", "NVDA", "$183.72", "2",   "$367",    "$0.00"],
        ],
        [22, 15, 20, 20, 20, 22, 71]
    )
    pdf.callout(
        "SPY vendida con ganancia a pesar del bug",
        f"Aunque SPY fue comprada por error durante el fin de semana,\n"
        f"el precio subio de $668.45 a $674.24 entre el domingo noche y el lunes manana.\n"
        f"Ganancia inesperada: ${spy_pnl:+,.2f}",
        r=220, g=245, b=220
    )

    pdf.subsection("Fase 3 — Apertura del mercado (7:49am–8:35am PT)  — Scanner")
    pdf.callout(
        "BUG: NVDA comprada por scanner (wash trade)",
        "A las 7:49am el scanner compro NVDA a pesar de estar reservada para MI PLAN.\n"
        "Esto ocurrio porque el bot fue reiniciado y la exclusion del plan no se aplico\n"
        "correctamente en el primer ciclo. El plan la vendio 53 segundos despues: -$12.45.",
        r=255, g=235, b=200
    )

    scanner_trades = [t for t in buys if "[SCANNER]" in t.get("reason","")]
    scanner_rows = []
    for t in scanner_trades:
        hora_utc = t["timestamp"][11:16]
        # convertir UTC a PT (UTC-7 en marzo)
        h, m = int(hora_utc[:2]), int(hora_utc[3:])
        h_pt = (h - 7) % 24
        hora_pt = f"{h_pt:02d}:{m:02d}am"
        reason_short = t["reason"].replace("[SCANNER] ","")[:45]
        scanner_rows.append([
            hora_pt, "BUY", t["symbol"],
            f"${float(t['price']):.2f}", t["qty"],
            f"${float(t['value']):,.0f}", reason_short
        ])
    pdf.table(
        ["Hora (PT)", "Accion", "Simbolo", "Precio", "Qty", "Valor", "Razon ML/Tecnica"],
        scanner_rows,
        [20, 15, 18, 20, 15, 22, 80]
    )

    # ── SECCION 2: PnL ───────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("2. RESUMEN DE GANANCIAS Y PERDIDAS")

    pdf.subsection("2.1  Trades Cerrados Hoy")
    pdf.table(
        ["Simbolo", "Entrada", "Salida", "Qty", "PnL", "Estado"],
        [
            ["SPY",  "$668.45", "$674.24", "111", f"${spy_pnl:+,.2f}", "GANANCIA"],
            ["NVDA", "$183.72", "$183.72", "2",   "$0.00",             "BREAKEVEN"],
            ["NVDA", "$182.37", "$182.28", "131", "$-12.45",           "PERDIDA (wash trade bug)"],
        ],
        [25, 25, 25, 15, 30, 70]
    )
    pdf.callout(
        f"PnL total de trades cerrados: ${total_closed_pnl:+,.2f}",
        f"SPY: +${spy_pnl:,.2f}  |  NVDA: -$12.45  |  Neto: ${total_closed_pnl:+,.2f}",
        r=220, g=245, b=220
    )

    pdf.subsection("2.2  Posiciones Abiertas al Cierre (sin realizar)")
    open_rows = []
    for sym, ep in sorted(entry_prices.items()):
        if sym == "NVDA":
            continue
        open_rows.append([sym, f"${ep:.2f}", "En posicion", "-", "Pendiente"])
    if open_rows:
        pdf.table(
            ["Simbolo", "Precio Entrada", "Estado", "Precio Actual", "PnL No Real."],
            open_rows,
            [25, 35, 30, 35, 65]
        )

    pdf.callout(
        "Perdida no realizada estimada: -$786",
        "Las 30 posiciones se compraron en la ultima hora del mercado con Fear & Greed en 28.\n"
        "Una caida de -0.3% en el primer dia es normal y no activa ninguna senal de venta.\n"
        "El bot mantiene las posiciones hasta que las senales tecnicas cambien.",
        r=255, g=248, b=220
    )

    pdf.subsection("2.3  PnL Consolidado del Dia")
    pdf.table(
        ["Concepto", "Valor"],
        [
            ["Ganancia realizada (SPY)",          f"+${spy_pnl:,.2f}"],
            ["Perdida realizada (NVDA wash trade)", "-$12.45"],
            ["Perdida no realizada (30 posiciones)", "-$786.56"],
            ["PnL NETO del dia",                   f"${day_pnl:+,.2f}"],
            ["Equity inicio",                       f"${start_equity:,.2f}"],
            ["Equity cierre",                       f"${end_equity:,.2f}"],
            ["Variacion %",                         f"{day_pnl/start_equity*100:+.2f}%"],
        ],
        [100, 90]
    )

    # ── SECCION 3: BUGS ──────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("3. BUGS ENCONTRADOS HOY")

    bugs = [
        ("BUG 1 — Triple compra de SPY (Modo SEGURO sin verificacion de posicion)",
         "Severidad: ALTA",
         "El bot usaba una version antigua con un modo SEGURO dedicado para SPY.\n"
         "Este modo compraba SPY en cada ciclo sin verificar si ya habia una posicion abierta.\n"
         "Resultado: 3 compras identicas de 37 acciones = $74,198 bloqueados.\n"
         "Impacto financiero: Ninguno (SPY subio y se vendio con ganancia).\n"
         "Causa raiz: La version antigua no tenia la logica de held_symbols del scanner.",
         255, 235, 200),
        ("BUG 2 — Bot operando fuera del horario de mercado",
         "Severidad: ALTA",
         "El bot no tenia verificacion de horario NYSE (9:30am-4:00pm ET / 6:30am-1:00pm PT).\n"
         "Corria los 7 dias de la semana, las 24 horas, ejecutando trades con datos viejos.\n"
         "Las 3 compras de SPY ocurrieron un domingo por la noche.\n"
         "En un dia de mercado bajista, este bug podria haber causado perdidas significativas.",
         255, 235, 200),
        ("BUG 3 — NVDA comprada por scanner (Wash trade)",
         "Severidad: MEDIA",
         "A pesar del fix previo, el scanner compro NVDA (simbolo exclusivo de MI PLAN).\n"
         "La causa: al reiniciar el bot, la exclusion del plan_symbol no se aplico en el\n"
         "primer ciclo o la logica de exclusion no fue suficientemente robusta.\n"
         "El plan intento vender la NVDA del scanner 53 segundos despues: -$12.45 perdidos.\n"
         "Alpaca podria haber bloqueado esto como wash trade en cuenta real.",
         255, 235, 200),
        ("BUG 4 — Sin take-profit en posiciones del scanner",
         "Severidad: MEDIA",
         "Las posiciones del scanner no tenian un techo de ganancia definido.\n"
         "Si AMD sube 15% y luego vuelve a 0%, el bot no asegura la ganancia en el camino.\n"
         "Solo vendia cuando una senal tecnica de bajada se activaba.\n"
         "En mercados volatiles esto puede costar ganancias significativas.",
         255, 248, 215),
    ]

    for titulo, severidad, desc, r, g, b in bugs:
        pdf.callout(f"{titulo}  |  {severidad}", desc, r=r, g=g, b=b)

    # ── SECCION 4: ARREGLOS ──────────────────────────────────────
    pdf.add_page()
    pdf.section_title("4. ARREGLOS APLICADOS HOY")

    fixes = [
        ("FIX 1 — Bug triple buy (ya no existe en codigo actual)",
         "Archivo: main.py",
         "La version actual del bot ya no tiene el modo SEGURO separado para SPY.\n"
         "El scanner utiliza held_symbols para verificar si un simbolo ya esta en posicion\n"
         "antes de generar una senal de compra. SPY es tratado como cualquier otro simbolo.\n"
         "Estado: RESUELTO - no requiere cambios adicionales.",
         220, 245, 220),
        ("FIX 2 — Filtro de horario de mercado",
         "Archivo: main.py  |  Cambio: +15 lineas",
         "Se agrego la funcion is_market_open() que verifica:\n"
         "  - Dia de la semana: lunes a viernes solamente\n"
         "  - Hora: entre 9:30am y 4:00pm ET (6:30am-1:00pm PT en California)\n"
         "  - Usa ZoneInfo('America/New_York') para respetar cambios de horario de verano\n"
         "Si el mercado esta cerrado, el bot registra el mensaje y espera al siguiente ciclo.\n"
         "Estado: ARREGLADO - desplegado en produccion.",
         220, 245, 220),
        ("FIX 3 — Doble proteccion para simbolo del plan (NVDA)",
         "Archivo: main.py  |  Cambio: +3 lineas",
         "Ademas de excluir el simbolo del plan del watchlist (ya existia),\n"
         "se agrego el simbolo directamente al set 'held' de posiciones:\n"
         "    if plan_symbol:\n"
         "        held.add(plan_symbol)\n"
         "Esto garantiza que aunque el watchlist falle, el scanner nunca compre el simbolo\n"
         "del plan porque lo ve como 'ya en posicion'.\n"
         "Estado: ARREGLADO - doble capa de proteccion activa.",
         220, 245, 220),
        ("FIX 4 — Take-profit automatico del 8%",
         "Archivo: main.py + config.py  |  Cambio: +30 lineas",
         "Se agrego verificacion de take-profit en cada ciclo del bot:\n"
         "  - Para cada posicion abierta, consulta el precio de entrada en memoria\n"
         "  - Si el precio actual >= entrada * 1.08 (8% de ganancia), vende automaticamente\n"
         "  - Envia alerta: TAKE-PROFIT 122xAMD @ $212.00 | +8.0% | PnL=$+1,920\n"
         "  - El porcentaje es configurable via TAKE_PROFIT_PCT en config.py\n"
         "  - Las posiciones de MI PLAN se excluyen (tienen su propio take-profit)\n"
         "Estado: ARREGLADO - activo a partir del proximo arranque del bot.",
         220, 245, 220),
    ]

    for titulo, archivos, desc, r, g, b in fixes:
        pdf.callout(f"{titulo}\n{archivos}", desc, r=r, g=g, b=b)

    # ── SECCION 5: EVALUACION ────────────────────────────────────
    pdf.add_page()
    pdf.section_title("5. EVALUACION DEL DIA Y PERSPECTIVA")

    pdf.subsection("5.1  Cumplimiento de objetivos")
    pdf.table(
        ["Objetivo", "Resultado", "Comentario"],
        [
            ["30 posiciones llenas",       "OK",  "Las 30 se llenaron entre 7:49am y 8:35am PT"],
            ["Diversificacion sectorial",  "OK",  "7 sectores: Tech, Salud, Energia, Finanzas, Retail, ETFs, Commodities"],
            ["Bot sin crashes",            "OK",  "Solo detenido manualmente con Ctrl+C"],
            ["Ganancia neta del dia",      "NO",  f"-${abs(day_pnl):.2f} ({day_pnl/start_equity*100:+.2f}%) — mercado en Miedo (F&G=28)"],
            ["Sin bugs en ejecucion",      "NO",  "4 bugs detectados, todos arreglados hoy"],
            ["Take-profit activo",         "NO",  "No existia — arreglado hoy para manana"],
        ],
        [70, 15, 105]
    )

    pdf.subsection("5.2  Analisis del contexto de mercado")
    pdf.body(
        "El mercado opero en modo MIEDO durante todo el dia:\n\n"
        "  Fear & Greed Index: 28 (zona de miedo)\n"
        "  VIX: 22.74 - 23.51 (elevado, mercado nervioso)\n"
        "  Estrategia del bot: buy_score minimo = 3 senales tecnicas requeridas\n\n"
        "En entornos de miedo, las 30 posiciones compradas al final del dia bajaron un\n"
        "promedio de -0.3% antes del cierre. Esto es comportamiento normal y esperado.\n"
        "El bot NO deberia vender estas posiciones basandose en la caida del primer dia."
    )

    pdf.subsection("5.3  Que esperar manana (18 de Marzo)")
    pdf.callout(
        "Escenario esperado para manana",
        "- El bot arrancara y verificara el horario antes de operar (nuevo fix activo)\n"
        "- Revisara las 30 posiciones abiertas buscando senales de venta o take-profit\n"
        "- Si el mercado rebota, algunas posiciones podrian activar take-profit al +8%\n"
        "- Si el Fear & Greed sigue bajo (< 25), el bot es mas agresivo en compras\n"
        "- Si el VIX sube > 35, el bot pedira 5 senales tecnicas antes de comprar (conservador)\n"
        "- El bot NO comprara NVDA bajo ningun escenario (doble proteccion activa)",
        r=220, g=230, b=250
    )

    pdf.subsection("5.4  Configuracion activa para manana")
    pdf.table(
        ["Parametro", "Valor", "Descripcion"],
        [
            ["TIMEFRAME",         "1Hour",   "Ciclo cada hora durante mercado abierto"],
            ["MAX_OPEN_POSITIONS","30",       "Maximo de posiciones simultaneas"],
            ["MAX_POSITION_PCT",  "3%",       "3% del capital por posicion (~$3,000 c/u)"],
            ["TAKE_PROFIT_PCT",   "8%",       "NUEVO: venta automatica al ganar 8%"],
            ["RSI_OVERSOLD",      "45",       "Umbral agresivo de compra por RSI"],
            ["ML_BUY_THRESHOLD",  "50%",      "Minimo de probabilidad ML para comprar"],
            ["ML_SELL_THRESHOLD", "62%",      "Minimo de probabilidad ML para vender"],
            ["Horario activo",    "6:30am-1pm PT", "NUEVO: solo opera en horario NYSE"],
            ["Plan activo",       "NVDA",     "MI PLAN separado del scanner"],
        ],
        [45, 30, 115]
    )

    # ── PIE DE PAGINA ────────────────────────────────────────────
    pdf.ln(5)
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 5,
        f"Reporte generado automaticamente el {datetime.now().strftime('%Y-%m-%d %H:%M')} "
        f"para la sesion del {date_str}. "
        "Capital operado en modo PAPER TRADING (simulado) con Alpaca Markets. "
        "Este documento no constituye asesoramiento financiero.",
        align="C"
    )

    pdf.output(out_path)
    print(f"PDF generado: {out_path}")
    return out_path


if __name__ == "__main__":
    build()
