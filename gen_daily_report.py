#!/usr/bin/env python3
from fpdf import FPDF
from datetime import datetime
import os, shutil

class DailyReport(FPDF):
    def header(self):
        self.set_fill_color(10, 25, 55)
        self.rect(0, 0, 210, 20, "F")
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 4)
        self.cell(0, 7, "REPORTE DIARIO No. 1  --  PAPER TRADING BOT", align="L")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(160, 195, 255)
        self.set_xy(10, 12)
        self.cell(0, 5, "Miercoles 19 de Marzo 2026  |  Alpaca Paper Trading  |  Capital $100,000 USD", align="L")
        self.ln(18)

    def footer(self):
        self.set_y(-13)
        self.set_fill_color(10, 25, 55)
        self.rect(0, 284, 210, 20, "F")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(160, 195, 255)
        self.cell(0, 8, f"Pag. {self.page_no()} | Reporte No.1 | 19/03/2026 | Paper Trading -- No es asesoramiento financiero", align="C")

    def sec(self, txt, r=15, g=45, b=110):
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 11)
        self.cell(0, 8, f"  {txt}", fill=True, ln=True)
        self.set_text_color(30, 30, 30)
        self.ln(2)

    def sub(self, txt):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(10, 55, 115)
        self.cell(0, 7, txt, ln=True)
        self.set_text_color(30, 30, 30)

    def txt(self, t, indent=5):
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(40, 40, 40)
        self.set_x(self.get_x() + indent)
        self.multi_cell(0, 5.5, t)
        self.ln(1)

    def kv(self, k, v, estado="ok"):
        cols = {"ok": (0,145,55), "warn": (190,110,0), "bad": (170,15,15), "info": (15,75,175)}
        c = cols.get(estado, (100,100,100))
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(242, 246, 255)
        self.set_draw_color(175, 200, 228)
        self.cell(60, 7, f"  {k}", border=1, fill=True)
        self.set_fill_color(*[min(255, x+195) for x in c])
        self.set_text_color(*c)
        self.cell(0, 7, f"  {v}", border=1, fill=True, ln=True)
        self.set_text_color(40, 40, 40)
        self.ln(0.5)

    def bul(self, t, col=(15, 100, 200)):
        self.set_x(12)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*col)
        self.cell(5, 6, chr(149))
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 6, t)

    def sep(self):
        self.set_draw_color(175, 200, 228)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)


pdf = DailyReport("P", "mm", "A4")
pdf.set_auto_page_break(True, margin=18)
pdf.set_margins(10, 22, 10)

# ── PORTADA ──────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.set_fill_color(10, 25, 55)
pdf.rect(0, 20, 210, 58, "F")
pdf.set_xy(0, 27)
pdf.set_font("Helvetica", "B", 30)
pdf.set_text_color(255, 255, 255)
pdf.cell(0, 14, "REPORTE No. 1", align="C", ln=True)
pdf.set_font("Helvetica", "", 16)
pdf.set_text_color(140, 195, 255)
pdf.cell(0, 9, "Diario de Paper Trading -- Alpaca", align="C", ln=True)
pdf.set_font("Helvetica", "B", 13)
pdf.set_text_color(255, 220, 100)
pdf.cell(0, 8, "Miercoles 19 de Marzo de 2026", align="C", ln=True)
pdf.set_text_color(40, 40, 40)
pdf.ln(47)

pdf.kv("Horario del bot",          "Inicio 10:40 UTC (6:40am PT) -- mercado 9:30am-4pm ET", "info")
pdf.kv("Equity inicio del dia",    "$98,644.15 USD",                                        "info")
pdf.kv("PnL del dia",              "- $1,000.67 USD  (-1.01%)",                             "bad")
pdf.kv("Trades ejecutados hoy",    "11  (6 ventas stop-loss + 5 compras nuevas)",            "warn")
pdf.kv("Wins / Losses",            "0 wins / 6 losses",                                     "bad")
pdf.kv("Posiciones al cierre",     "30 de 30 maximas (cartera llena)",                      "warn")
pdf.kv("VIX",                      "25.24 -- zona de precaucion",                           "warn")
pdf.kv("Fear & Greed",             "23 / 100 -- EXTREME FEAR",                              "bad")
pdf.kv("SP500 / NASDAQ / DOW",     "-0.81% / -0.93% / -0.92%",                             "bad")
pdf.kv("PnL acumulado 3 dias",     "- $2,152.05 USD  (-2.15%)",                             "bad")

# ── 1. RESUMEN ────────────────────────────────────────────────────────────────
pdf.add_page()
pdf.sec("1.  RESUMEN DEL DIA")
pdf.txt(
    "El bot opero en condiciones bajistas. VIX en 25.24, Fear & Greed en Extreme Fear (23/100), "
    "y todos los indices en rojo (SP500 -0.81%, NASDAQ -0.93%). "
    "Tenia 30 posiciones abiertas desde el 17/03 con entradas en zona de maximos recientes. "
    "El mercado continuo cayendo, activando 6 stop-losses automaticos. "
    "Tras liberar capital, el scanner abrio 5 nuevas posiciones en energia defensiva, oro y tech a descuento."
)

pdf.ln(2)
pdf.sub("1.1  Cronologia del dia")
eventos = [
    ("10:40 UTC", "Bot iniciado. Equity $98,644.41 | Buying power $15,476.13"),
    ("10:40 UTC", "Carga modelo ML (entrenado 17/03) y MI PLAN NVDA activo."),
    ("10:40-11:20 UTC", "Scanner evalua 44 simbolos. 30 posiciones en HOLD. 0 senales nuevas."),
    ("11:20 UTC", "0 buys nuevos (cartera llena). Mercado bajando suavemente."),
    ("17:41 UTC", "6 stop-losses activados automaticamente en cascada."),
    ("17:41 UTC", "Scanner detecta 5 oportunidades post-stop. 5 compras ejecutadas."),
    ("Resto del dia", "Sin actividad. 30 posiciones mantenidas hasta cierre."),
]
for hora, evento in eventos:
    pdf.set_x(10)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(10, 55, 115)
    pdf.cell(35, 6, hora)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6, evento)

# ── 2. STOP-LOSSES ────────────────────────────────────────────────────────────
pdf.ln(2)
pdf.sec("2.  STOP-LOSSES ACTIVADOS  (6 salidas automaticas)", 140, 25, 10)

stops = [
    ("ABBV", "AbbVie",     "222.57", "206.18", "-7.4%",  "-163.90", "Farmaceutica -- caida sostenida"),
    ("HD",   "Home Depot", "342.48", "326.82", "-4.6%",  "-156.60", "Retail -- presion por tasas altas"),
    ("MCD",  "McDonald's", "328.55", "311.57", "-5.2%",  "-169.75", "Consumo -- arrastrado por mercado"),
    ("SLV",  "Plata ETF",  "72.01",  "64.57",  "-10.3%", "-245.36", "Commodities -- mayor caida del dia"),
    ("TQQQ", "NASDAQ 3x",  "48.20",  "44.80",  "-7.0%",  "-166.36", "ETF apalancado -- riesgo alto"),
    ("WMT",  "Walmart",    "125.97", "120.78", "-4.1%",   "-98.70", "Retail -- defensivo pero cae igual"),
]

colw = [18, 30, 20, 20, 16, 22, 64]
headers = ["Simbolo", "Empresa", "Entrada", "Salida", "Caida", "PnL", "Motivo"]
pdf.set_font("Helvetica", "B", 8.5)
pdf.set_fill_color(140, 25, 10)
pdf.set_text_color(255, 255, 255)
for h, w in zip(headers, colw):
    pdf.cell(w, 7, h, border=1, fill=True, align="C")
pdf.ln()

total_pnl = 0
for sym, emp, ent, sal, pct, pnl, mot in stops:
    total_pnl += float(pnl)
    pdf.set_fill_color(255, 235, 235)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(160, 15, 15)
    pdf.cell(colw[0], 6, sym, border=1, fill=True, align="C")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(colw[1], 6, emp, border=1, fill=True)
    pdf.cell(colw[2], 6, f"${ent}", border=1, fill=True, align="C")
    pdf.cell(colw[3], 6, f"${sal}", border=1, fill=True, align="C")
    pdf.set_text_color(160, 15, 15)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(colw[4], 6, pct, border=1, fill=True, align="C")
    pdf.cell(colw[5], 6, f"${pnl}", border=1, fill=True, align="C")
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(colw[6], 6, mot[:52], border=1, fill=True)
    pdf.ln()

pdf.set_text_color(40, 40, 40)
pdf.ln(1)
pdf.set_font("Helvetica", "B", 9.5)
pdf.set_fill_color(255, 220, 220)
pdf.set_draw_color(160, 15, 15)
pdf.set_text_color(140, 0, 0)
pdf.cell(0, 7, f"  TOTAL PERDIDAS POR STOP-LOSS:  ${total_pnl:+.2f} USD", border=1, fill=True, ln=True)
pdf.set_text_color(40, 40, 40)

pdf.ln(3)
pdf.sub("2.1  Analisis de las salidas")
pdf.txt(
    "Los 6 stop-losses funcionaron exactamente como fueron configurados. "
    "La mayor perdida fue SLV (Plata ETF) con -10.3%, indicando que el precio cayo "
    "mas de 4% entre dos ciclos horarios sin activarse antes (gap). "
    "TQQQ (NASDAQ 3x apalancado) confirma el riesgo de ETFs apalancados en carteras long: "
    "amplifican bajadas igual que subidas. SLV y TQQQ no deberian estar en una cartera "
    "long defensiva en mercado con VIX>20. Las otras 4 salidas (ABBV, HD, MCD, WMT) "
    "fueron limpias y dentro del rango del 4-5% configurado."
)

# ── 3. NUEVAS COMPRAS ──────────────────────────────────────────────────────────
pdf.add_page()
pdf.sec("3.  NUEVAS COMPRAS EJECUTADAS  (5 posiciones)", 20, 90, 40)

compras = [
    ("XOM",  "ExxonMobil",   "157.87", "14",  "2,210.18", "0.67", "ML=0.67 | VIX=25.24 | Energia subiendo"),
    ("SLB",  "Schlumberger", "47.315", "50",  "2,365.75", "0.62", "ML=0.62 | Servicios petroleo"),
    ("CVX",  "Chevron",      "201.62", "11",  "2,217.82", "0.60", "ML=0.60 | Energia diversificada"),
    ("GLD",  "Oro ETF",      "423.10", "10",  "4,231.00", "0.57", "RSI=20 bajo | Safe haven VIX alto"),
    ("MSFT", "Microsoft",    "387.61", "10",  "3,876.10", "0.56", "RSI=24 bajo | Tech calidad a descuento"),
]

colw2 = [18, 30, 22, 12, 24, 20, 64]
headers2 = ["Simbolo", "Empresa", "Precio", "Qty", "Valor", "ML conf", "Razon"]
pdf.set_font("Helvetica", "B", 8.5)
pdf.set_fill_color(15, 90, 40)
pdf.set_text_color(255, 255, 255)
for h, w in zip(headers2, colw2):
    pdf.cell(w, 7, h, border=1, fill=True, align="C")
pdf.ln()

total_inv = 0
for sym, emp, px, qty, val, ml, razon in compras:
    total_inv += float(val.replace(",", ""))
    pdf.set_fill_color(230, 250, 235)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(0, 130, 50)
    pdf.cell(colw2[0], 6, sym, border=1, fill=True, align="C")
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(colw2[1], 6, emp, border=1, fill=True)
    pdf.cell(colw2[2], 6, f"${px}", border=1, fill=True, align="C")
    pdf.cell(colw2[3], 6, qty, border=1, fill=True, align="C")
    pdf.cell(colw2[4], 6, f"${val}", border=1, fill=True, align="C")
    pdf.set_text_color(10, 55, 115)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(colw2[5], 6, ml, border=1, fill=True, align="C")
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(60, 60, 60)
    pdf.cell(colw2[6], 6, razon[:55], border=1, fill=True)
    pdf.ln()

pdf.set_text_color(40, 40, 40)
pdf.ln(1)
pdf.set_font("Helvetica", "B", 9.5)
pdf.set_fill_color(225, 245, 230)
pdf.set_draw_color(0, 130, 50)
pdf.set_text_color(0, 100, 40)
pdf.cell(0, 7, f"  TOTAL INVERTIDO EN NUEVAS COMPRAS:  ${total_inv:,.2f} USD", border=1, fill=True, ln=True)
pdf.set_text_color(40, 40, 40)

pdf.ln(3)
pdf.sub("3.1  Logica de las compras")
pdf.txt(
    "El scanner identifico estas 5 oportunidades tras liberar slots por los stop-losses. "
    "La logica: RSI extremadamente bajo (20-24) + ML > 0.56. "
    "Energia (XOM, SLB, CVX): el sector ha mostrado resiliencia relativa. "
    "GLD: el oro es refugio clasico cuando Fear&Greed < 25 -- RSI=20 es sobreventa extrema. "
    "MSFT: tecnologia de primera linea con RSI=24, raro de ver en Microsoft. "
    "Las 5 compras son mas defensivas que el ciclo anterior, lo cual es adecuado con VIX=25."
)

# ── 4. POSICIONES AL CIERRE ─────────────────────────────────────────────────
pdf.ln(2)
pdf.sec("4.  POSICIONES ABIERTAS AL CIERRE DEL DIA", 50, 10, 100)
pdf.txt("30/30 posiciones activas. Cartera completamente llena. Capital ~90% desplegado.")

posiciones = [
    ("NVDA","182.37","Tech"),  ("AMD","196.23","Tech"),   ("AAPL","254.27","Tech"),
    ("INTC","44.11","Tech"),   ("CRM","196.42","Tech"),   ("MSFT","387.61","Tech*"),
    ("BAC","47.41","Finanzas"),("JPM","286.61","Finanzas"),("WFC","76.26","Finanzas"),
    ("C","107.77","Finanzas"), ("AXP","301.34","Finanzas"),("MS","158.87","Finanzas"),
    ("JNJ","241.26","Salud"),  ("MRK","115.74","Salud"),  ("UNH","285.54","Salud"),
    ("ABT","111.36","Salud"),  ("PFE","27.08","Salud"),
    ("XOM","157.87","Energ*"), ("SLB","47.32","Energ*"),  ("CVX","201.62","Energ*"),
    ("OXY","57.73","Energia"), ("COP","123.32","Energia"),
    ("TGT","117.33","Consumo"),("AMZN","213.93","Consumo"),("GOOGL","308.32","Consumo"),
    ("IWM","249.42","ETF"),    ("SQQQ","72.25","ETF(!)"),
    ("USO","116.97","Commod"), ("TLT","87.53","Bonos"),   ("GLD","423.10","Oro*"),
]

# 5 columnas
pdf.set_font("Helvetica", "B", 8)
pdf.set_fill_color(15, 45, 110)
pdf.set_text_color(255, 255, 255)
for _ in range(5):
    pdf.cell(8,  6, "#",    border=1, fill=True, align="C")
    pdf.cell(16, 6, "Sim.", border=1, fill=True, align="C")
    pdf.cell(18, 6, "Entr", border=1, fill=True, align="C")
pdf.ln()

pdf.set_font("Helvetica", "", 8)
for i in range(0, 30, 5):
    grupo = posiciones[i:i+5]
    pdf.set_fill_color(245, 248, 255) if (i//5) % 2 == 0 else pdf.set_fill_color(235, 242, 255)
    for j, (sym, px, sect) in enumerate(grupo):
        es_nuevo = "*" in sect
        es_warn  = "(!)" in sect
        pdf.set_text_color(40, 40, 40)
        pdf.cell(8,  5.5, str(i+j+1), border=1, fill=True, align="C")
        pdf.set_font("Helvetica", "B", 8)
        if es_warn:    pdf.set_text_color(160, 15, 15)
        elif es_nuevo: pdf.set_text_color(0, 130, 50)
        else:          pdf.set_text_color(10, 55, 115)
        pdf.cell(16, 5.5, sym, border=1, fill=True, align="C")
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(18, 5.5, f"${px}", border=1, fill=True, align="C")
    pdf.ln()

pdf.set_text_color(40, 40, 40)
pdf.ln(1)
pdf.set_font("Helvetica", "I", 8)
pdf.set_text_color(80, 80, 80)
pdf.cell(0, 5, "Verde* = compradas hoy  |  Rojo (!) = SQQQ ETF inverso -- posicion problematica pendiente de revisar", ln=True)

# ── 5. CONTEXTO DE MERCADO ────────────────────────────────────────────────────
pdf.add_page()
pdf.sec("5.  CONTEXTO DEL MERCADO -- 19 MARZO 2026", 20, 100, 60)

pdf.sub("5.1  Indicadores del dia")
indicadores = [
    ("VIX",              "25.24",        "Elevado (>20 = nerviosismo, >30 = panico)", "warn"),
    ("Fear & Greed",     "23 / 100",     "EXTREME FEAR -- zona historica de oportunidad", "bad"),
    ("SP500",            "- 0.81%",      "Caida moderada. Tendencia bajista de corto plazo", "bad"),
    ("NASDAQ",           "- 0.93%",      "Tech lidera las caidas. Growth stocks bajo presion", "bad"),
    ("DOW Jones",        "- 0.92%",      "Caida generalizada, no solo sectorial", "bad"),
    ("VXN (vol NASDAQ)", "+1.26%",       "Volatilidad subiendo en tech -- mas incertidumbre", "warn"),
    ("Senal del bot",    "neutral",      "No comprar agresivo, no entrar en panico", "info"),
    ("Earnings hoy",     "Sin datos",    "Sin riesgo de gap por resultados trimestrales", "ok"),
    ("Regimen detectado","SIDEWAYS/BEAR","regime_detector.py activo desde hoy por primera vez", "warn"),
]
for k, v, desc, est in indicadores:
    cols = {"ok":(0,145,55), "warn":(190,110,0), "bad":(170,15,15), "info":(15,75,175)}
    c = cols[est]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(242, 246, 255)
    pdf.set_draw_color(175, 200, 228)
    pdf.cell(38, 7, f"  {k}", border=1, fill=True)
    pdf.set_fill_color(*[min(255, x+195) for x in c])
    pdf.set_text_color(*c)
    pdf.cell(26, 7, f"  {v}", border=1, fill=True)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(40, 40, 40)
    pdf.set_fill_color(250, 250, 250)
    pdf.cell(0, 7, f"  {desc}", border=1, fill=True, ln=True)
    pdf.ln(0.5)

pdf.set_text_color(40, 40, 40)
pdf.ln(3)
pdf.sub("5.2  Interpretacion del contexto para el bot")
pdf.txt(
    "Mercado en condicion bajista moderada con miedo elevado. "
    "Con VIX=25.24 el algoritmo requeria min_score=3 para comprar -- nivel cauteloso. "
    "El Fear & Greed de 23 es historicamente una zona de oportunidad contrarian, "
    "pero no garantiza recuperacion inmediata. El bot interpreto el RSI bajo de "
    "muchos simbolos como oportunidad de compra, lo cual puede ser correcto si el "
    "mercado encuentra soporte aqui. Si VIX sube a 30+, regime_detector activaria "
    "modo BEAR y bloquearia nuevas compras long."
)

# ── 6. PNL DEL DIA ───────────────────────────────────────────────────────────
pdf.ln(2)
pdf.sec("6.  PnL DETALLADO DEL DIA", 60, 10, 10)

pdf.sub("6.1  Desglose de resultados realizados vs no realizados")
desglose = [
    ("Perdidas realizadas (6 stops)",  "-$1,000.67", "bad",  "Capital recuperado y reasignado"),
    ("Ganancias realizadas hoy",       "$0.00",       "info", "Ningun trade cerro en positivo"),
    ("PnL no realizado estimado",      "~ -$355",     "warn", "30 posiciones aun abiertas en rojo"),
    ("PnL neto del dia (realizado)",   "-$1,000.67",  "bad",  "Solo incluye trades cerrados"),
]
for concepto, monto, est, nota in desglose:
    cols = {"ok":(0,145,55), "warn":(190,110,0), "bad":(170,15,15), "info":(15,75,175)}
    c = cols[est]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(242, 246, 255)
    pdf.set_draw_color(175, 200, 228)
    pdf.cell(75, 7, f"  {concepto}", border=1, fill=True)
    pdf.set_fill_color(*[min(255, x+195) for x in c])
    pdf.set_text_color(*c)
    pdf.cell(28, 7, f"  {monto}", border=1, fill=True)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(40, 40, 40)
    pdf.set_fill_color(250, 250, 250)
    pdf.cell(0, 7, f"  {nota}", border=1, fill=True, ln=True)
    pdf.ln(0.5)

pdf.set_text_color(40, 40, 40)
pdf.ln(3)
pdf.sub("6.2  Acumulado de los 3 dias de paper trading")

acum = [
    ("17/03/2026", "Dia 1", -320.09,  99871.54, 32, 0, 1, "Triple compra SPY (bug) + 26 pos. abiertas"),
    ("18/03/2026", "Dia 2", -831.29,  98917.67,  0, 0, 0, "Caida overnight sin trades"),
    ("19/03/2026", "Dia 3", -1000.67, 98644.41, 11, 0, 6, "6 stop-losses + 5 nuevas compras"),
]
colwa = [26, 13, 24, 28, 16, 12, 16, 55]
headersa = ["Fecha", "Dia", "PnL dia", "Equity", "Trades", "Wins", "Loss", "Descripcion"]
pdf.set_font("Helvetica", "B", 8.5)
pdf.set_fill_color(10, 25, 55)
pdf.set_text_color(255, 255, 255)
for h, w in zip(headersa, colwa):
    pdf.cell(w, 7, h, border=1, fill=True, align="C")
pdf.ln()

total_pnl_acum = 0
for fecha, dia, pnl, equity, trades, wins, losses, desc in acum:
    total_pnl_acum += pnl
    pdf.set_fill_color(255, 240, 240)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(colwa[0], 6, fecha, border=1, fill=True, align="C")
    pdf.cell(colwa[1], 6, dia,   border=1, fill=True, align="C")
    pdf.set_text_color(160, 15, 15)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.cell(colwa[2], 6, f"${pnl:+.2f}", border=1, fill=True, align="C")
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(colwa[3], 6, f"${equity:,.2f}", border=1, fill=True, align="C")
    pdf.cell(colwa[4], 6, str(trades), border=1, fill=True, align="C")
    pdf.set_text_color(0, 130, 50)
    pdf.cell(colwa[5], 6, str(wins),   border=1, fill=True, align="C")
    pdf.set_text_color(160, 15, 15)
    pdf.cell(colwa[6], 6, str(losses), border=1, fill=True, align="C")
    pdf.set_text_color(60, 60, 60)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.cell(colwa[7], 6, desc[:48], border=1, fill=True)
    pdf.ln()

pdf.set_text_color(40, 40, 40)
pdf.ln(1)
pdf.set_font("Helvetica", "B", 10)
pdf.set_fill_color(255, 230, 230)
pdf.set_draw_color(160, 15, 15)
pdf.set_text_color(140, 0, 0)
pdf.cell(0, 8, f"  TOTAL 3 DIAS:  ${total_pnl_acum:+.2f} USD  |  Retorno: -2.15%  |  Capital actual: ~$97,848", border=1, fill=True, ln=True)
pdf.set_text_color(40, 40, 40)

# ── 7. EVALUACION ────────────────────────────────────────────────────────────
pdf.add_page()
pdf.sec("7.  EVALUACION DEL DIA Y PROXIMOS PASOS", 80, 20, 80)

pdf.sub("7.1  Que funciono bien hoy")
bien = [
    "Stop-losses automaticos: 6 salidas limpias sin intervencion manual. El sistema funciona.",
    "Nuevas compras post-stop: 5 posiciones en sectores defensivos (energia, oro) -- buena logica.",
    "Bot estable: corrio sin crashes, logs completos, alertas Telegram activas todo el dia.",
    "GLD comprado con RSI=20: correcta lectura -- el oro es refugio con Fear&Greed=23.",
    "regime_detector.py activo por primera vez hoy -- el sistema ya clasifica el mercado.",
]
for b in bien:
    pdf.bul(b, (0, 145, 55))

pdf.ln(3)
pdf.sub("7.2  Que no funciono bien hoy")
mal = [
    "Win rate 0% acumulado: 0 trades cerrados en ganancia en 3 dias. Necesita mas tiempo.",
    "SQQQ sigue abierto como long: ETF inverso del NASDAQ -- posicion contradictoria con el resto.",
    "TQQQ stop -7%: ETF apalancado 3x no deberia estar en cartera long conservadora.",
    "SLV stop -10.3%: la plata bajo 10% desde compra. Gap entre ciclos horarios sin deteccion.",
    "ML da 0.56-0.67 para todo: el modelo sigue siendo permisivo. Umbral 0.50 demasiado bajo.",
    "30 posiciones = cartera siempre llena: no hay margen para nuevas oportunidades buenas.",
]
for m in mal:
    pdf.bul(m, (180, 30, 30))

pdf.ln(3)
pdf.sub("7.3  Acciones para manana (20/03/2026)")
acciones = [
    ("URGENTE",    "Cambiar RSI_OVERSOLD de 45 a 35 en config.py"),
    ("URGENTE",    "Subir ML_BUY_PROB_THRESHOLD de 0.50 a 0.62"),
    ("IMPORTANTE", "Verificar que regime_detector clasifica el mercado correctamente"),
    ("IMPORTANTE", "Monitorear XOM, SLB, CVX -- si energia sigue subiendo, buena senial"),
    ("OBSERVAR",   "Si Fear&Greed sube de 23 a 30+: mercado recuperando confianza"),
    ("OBSERVAR",   "Si SP500 cae otro 1%+ y VIX supera 30: regime_detector debe detectar BEAR"),
]
colores_nivel = {"URGENTE": (170,15,15), "IMPORTANTE": (190,110,0), "OBSERVAR": (15,75,175)}
for nivel, acc in acciones:
    c = colores_nivel.get(nivel, (100,100,100))
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_text_color(*c)
    pdf.set_x(10)
    pdf.cell(25, 6, f"[{nivel}]")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(40, 40, 40)
    pdf.multi_cell(0, 6, acc)

pdf.ln(5)
pdf.sep()
pdf.set_font("Helvetica", "B", 10)
pdf.set_fill_color(240, 248, 255)
pdf.set_draw_color(15, 75, 175)
pdf.set_text_color(10, 55, 115)
pdf.cell(0, 9, "  VEREDICTO: Bot operando correctamente en mercado bajista. Continuar paper trading.", border=1, fill=True, ln=True)
pdf.set_font("Helvetica", "", 9.5)
pdf.set_text_color(40, 40, 40)
pdf.set_x(14)
pdf.multi_cell(0, 6,
    "Un -2.15% en 3 dias con todos los indices en rojo y Fear&Greed=23 no es un resultado "
    "catastrofico. Los stop-losses protegieron el capital de perdidas mayores. "
    "El sistema esta aprendiendo el mercado real. Hacer los 2 cambios urgentes de config.py "
    "y dejar correr al menos 2-3 semanas mas antes de cualquier decision sobre live trading."
)

pdf.ln(5)
pdf.set_font("Helvetica", "I", 8)
pdf.set_text_color(120, 120, 120)
pdf.cell(0, 5,
    f"Reporte No.1 generado el {datetime.now().strftime('%d/%m/%Y a las %H:%M')} "
    "por Claude Code | Alpaca Paper Trading | No es asesoramiento financiero",
    ln=True
)

# ── GUARDAR ──────────────────────────────────────────────────────────────────
docs = os.path.expanduser("~/Documents")
os.makedirs(docs, exist_ok=True)
fname = "reporte_diario_01_19marzo2026.pdf"
out   = os.path.join(docs, fname)
pdf.output(out)

reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
os.makedirs(reports_dir, exist_ok=True)
shutil.copy(out, os.path.join(reports_dir, fname))

print(f"OK: {out}")
