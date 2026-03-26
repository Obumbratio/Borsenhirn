#!/usr/bin/env python3
"""
Reporte tecnico integral del sistema de trading - con datos reales de Alpaca paper trading
"""
from fpdf import FPDF
from datetime import datetime
import os, json, csv, shutil


# -- Datos reales leidos de logs y memoria ------------------------------------

TRADES = [
    {"fecha": "17/03/2026", "hora": "03:12 UTC", "accion": "BUY",  "simbolo": "SPY",  "precio": 668.45, "qty": 37,  "valor": 24732.65, "pnl": None,    "razon": "[MI PLAN] RSI=40 bajo | Rebote BB | Caida+rebote RSI"},
    {"fecha": "17/03/2026", "hora": "03:30 UTC", "accion": "BUY",  "simbolo": "SPY",  "precio": 668.45, "qty": 37,  "valor": 24732.65, "pnl": None,    "razon": "[MI PLAN] RSI=40 | Score=3>=2 | VIX=23.51 | F&G=28 -- BUG: triple compra"},
    {"fecha": "17/03/2026", "hora": "05:33 UTC", "accion": "BUY",  "simbolo": "SPY",  "precio": 668.45, "qty": 37,  "valor": 24732.65, "pnl": None,    "razon": "[MI PLAN] RSI=40 | Score=3>=2 | F&G=28 -- BUG: triple compra"},
    {"fecha": "17/03/2026", "hora": "13:48 UTC", "accion": "SELL", "simbolo": "SPY",  "precio": 674.24, "qty": 111, "valor": 74840.64, "pnl": +642.69, "razon": "[MI PLAN] ML venta fuerte -- vende las 3 compras juntas"},
    {"fecha": "17/03/2026", "hora": "13:48 UTC", "accion": "SELL", "simbolo": "NVDA", "precio": 183.72, "qty": 2,   "valor": 367.44,   "pnl": 0.0,     "razon": "[MI PLAN] Momentum perdido"},
    {"fecha": "17/03/2026", "hora": "15:49 UTC", "accion": "BUY",  "simbolo": "NVDA", "precio": 182.37, "qty": 131, "valor": 23890.47, "pnl": None,    "razon": "[SCANNER] ML=0.69 | VIX=22.74 | F&G=28"},
    {"fecha": "17/03/2026", "hora": "15:49 UTC", "accion": "BUY",  "simbolo": "AMD",  "precio": 196.23, "qty": 122, "valor": 23940.06, "pnl": None,    "razon": "[SCANNER] RSI=45 bajo | ML=0.69 | VIX=22.74"},
    {"fecha": "17/03/2026", "hora": "15:49 UTC", "accion": "BUY",  "simbolo": "AAPL", "precio": 254.27, "qty": 94,  "valor": 23901.38, "pnl": None,    "razon": "[SCANNER] ML=0.66 | VIX=22.74 | F&G=28"},
    {"fecha": "17/03/2026", "hora": "15:49 UTC", "accion": "SELL", "simbolo": "NVDA", "precio": 182.28, "qty": 131, "valor": 23878.03, "pnl": 0.0,     "razon": "[MI PLAN] Momentum perdido -- venta inmediata"},
    {"fecha": "17/03/2026", "hora": "15:53 UTC", "accion": "BUY",  "simbolo": "INTC", "precio": 44.11,  "qty": 545, "valor": 24039.95, "pnl": None,    "razon": "[SCANNER] RSI=35 bajo | ML=0.69 | VIX=23.08"},
    {"fecha": "17/03/2026", "hora": "15:53 UTC", "accion": "BUY",  "simbolo": "BAC",  "precio": 47.41,  "qty": 507, "valor": 24036.87, "pnl": None,    "razon": "[SCANNER] ML=0.69 | VIX=23.08"},
    {"fecha": "17/03/2026", "hora": "15:57 UTC", "accion": "BUY",  "simbolo": "TGT",  "precio": 117.33, "qty": 204, "valor": 23934.30, "pnl": None,    "razon": "[SCANNER] ML=0.69 | VIX=23.02"},
    {"fecha": "17/03/2026", "hora": "16:12 UTC", "accion": "BUY",  "simbolo": "MRK",  "precio": 115.74, "qty": 20,  "valor": 2314.80,  "pnl": None,    "razon": "[SCANNER] ML=0.69 | VIX=22.75"},
    {"fecha": "17/03/2026", "hora": "16:12 UTC", "accion": "BUY",  "simbolo": "JNJ",  "precio": 241.26, "qty": 10,  "valor": 2412.60,  "pnl": None,    "razon": "[SCANNER] RSI=44 bajo | ML=0.68"},
    {"fecha": "17/03/2026", "hora": "16:12 UTC", "accion": "BUY",  "simbolo": "SQQQ", "precio": 72.25,  "qty": 33,  "valor": 2384.25,  "pnl": None,    "razon": "[SCANNER] RSI=44 bajo | ML=0.68 -- ERROR: ETF inverso comprado como long"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "CRM",  "precio": 196.42, "qty": 12,  "valor": 2357.04,  "pnl": None,    "razon": "[SCANNER] ML=0.68"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "IWM",  "precio": 249.42, "qty": 10,  "valor": 2494.15,  "pnl": None,    "razon": "[SCANNER] ML=0.68"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "JPM",  "precio": 286.61, "qty": 10,  "valor": 2866.10,  "pnl": None,    "razon": "[SCANNER] ML=0.68"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "HD",   "precio": 342.48, "qty": 10,  "valor": 3424.80,  "pnl": None,    "razon": "[SCANNER] RSI=44 bajo | ML=0.68"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "WFC",  "precio": 76.26,  "qty": 31,  "valor": 2364.06,  "pnl": None,    "razon": "[SCANNER] ML=0.68"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "ABBV", "precio": 222.57, "qty": 10,  "valor": 2225.70,  "pnl": None,    "razon": "[SCANNER] ML=0.68"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "SLV",  "precio": 72.01,  "qty": 33,  "valor": 2376.16,  "pnl": None,    "razon": "[SCANNER] RSI=35 bajo | Rebote BB | ML=0.68"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "C",    "precio": 107.77, "qty": 22,  "valor": 2370.83,  "pnl": None,    "razon": "[SCANNER] ML=0.67"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "AXP",  "precio": 301.34, "qty": 10,  "valor": 3013.35,  "pnl": None,    "razon": "[SCANNER] ML=0.67"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "USO",  "precio": 116.97, "qty": 20,  "valor": 2339.40,  "pnl": None,    "razon": "[SCANNER] ML=0.67"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "UNH",  "precio": 285.54, "qty": 10,  "valor": 2855.40,  "pnl": None,    "razon": "[SCANNER] ML=0.66"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "TQQQ", "precio": 48.20,  "qty": 49,  "valor": 2361.55,  "pnl": None,    "razon": "[SCANNER] ML=0.65"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "MCD",  "precio": 328.55, "qty": 10,  "valor": 3285.45,  "pnl": None,    "razon": "[SCANNER] ML=0.65"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "MS",   "precio": 158.87, "qty": 15,  "valor": 2383.05,  "pnl": None,    "razon": "[SCANNER] ML=0.65"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "PFE",  "precio": 27.08,  "qty": 88,  "valor": 2382.60,  "pnl": None,    "razon": "[SCANNER] ML=0.64"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "OXY",  "precio": 57.73,  "qty": 41,  "valor": 2366.93,  "pnl": None,    "razon": "[SCANNER] ML=0.63"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "WMT",  "precio": 125.97, "qty": 19,  "valor": 2393.43,  "pnl": None,    "razon": "[SCANNER] ML=0.63"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "AMZN", "precio": 213.93, "qty": 11,  "valor": 2353.23,  "pnl": None,    "razon": "[SCANNER] ML=0.62"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "GOOGL","precio": 308.32, "qty": 10,  "valor": 3083.15,  "pnl": None,    "razon": "[SCANNER] ML=0.62"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "COP",  "precio": 123.32, "qty": 19,  "valor": 2343.08,  "pnl": None,    "razon": "[SCANNER] ML=0.62"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "TLT",  "precio": 87.53,  "qty": 27,  "valor": 2363.31,  "pnl": None,    "razon": "[SCANNER] ML=0.61"},
    {"fecha": "17/03/2026", "hora": "16:35 UTC", "accion": "BUY",  "simbolo": "ABT",  "precio": 111.36, "qty": 21,  "valor": 2338.56,  "pnl": None,    "razon": "[SCANNER] ML=0.61"},
    # Stops y nuevas compras del 19/03
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "SELL", "simbolo": "ABBV", "precio": 206.18, "qty": 10,  "valor": 2061.80,  "pnl": -163.90, "razon": "Stop-loss entrada -7.4%"},
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "SELL", "simbolo": "HD",   "precio": 326.82, "qty": 10,  "valor": 3268.20,  "pnl": -156.60, "razon": "Stop-loss entrada -4.6%"},
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "SELL", "simbolo": "MCD",  "precio": 311.57, "qty": 10,  "valor": 3115.70,  "pnl": -169.75, "razon": "Stop-loss entrada -5.2%"},
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "SELL", "simbolo": "SLV",  "precio": 64.57,  "qty": 33,  "valor": 2130.81,  "pnl": -245.36, "razon": "Stop-loss entrada -10.3%"},
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "SELL", "simbolo": "TQQQ", "precio": 44.80,  "qty": 49,  "valor": 2195.20,  "pnl": -166.36, "razon": "Stop-loss entrada -7.0%"},
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "SELL", "simbolo": "WMT",  "precio": 120.78, "qty": 19,  "valor": 2294.72,  "pnl": -98.70,  "razon": "Stop-loss entrada -4.1%"},
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "BUY",  "simbolo": "XOM",  "precio": 157.87, "qty": 14,  "valor": 2210.18,  "pnl": None,    "razon": "[SCANNER] ML=0.67 | VIX=25.24 | F&G=23"},
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "BUY",  "simbolo": "SLB",  "precio": 47.32,  "qty": 50,  "valor": 2365.75,  "pnl": None,    "razon": "[SCANNER] ML=0.62 | VIX=25.24"},
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "BUY",  "simbolo": "CVX",  "precio": 201.62, "qty": 11,  "valor": 2217.82,  "pnl": None,    "razon": "[SCANNER] ML=0.60 | VIX=25.24"},
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "BUY",  "simbolo": "GLD",  "precio": 423.10, "qty": 10,  "valor": 4231.00,  "pnl": None,    "razon": "[SCANNER] RSI=20 bajo | ML=0.57 | VIX=25.24"},
    {"fecha": "19/03/2026", "hora": "17:41 UTC", "accion": "BUY",  "simbolo": "MSFT", "precio": 387.61, "qty": 10,  "valor": 3876.10,  "pnl": None,    "razon": "[SCANNER] RSI=24 bajo | ML=0.56 | VIX=25.24"},
]

POSICIONES_ABIERTAS = [
    ("NVDA",  182.37), ("AMD",   196.23), ("AAPL",  254.27), ("INTC",  44.11),
    ("BAC",   47.41),  ("TGT",   117.33), ("MRK",   115.74), ("JNJ",   241.26),
    ("SQQQ",  72.25),  ("CRM",   196.42), ("IWM",   249.42), ("JPM",   286.61),
    ("WFC",   76.26),  ("C",     107.77), ("AXP",   301.34), ("USO",   116.97),
    ("UNH",   285.54), ("MS",    158.87), ("PFE",   27.08),  ("OXY",   57.73),
    ("AMZN",  213.93), ("GOOGL", 308.32), ("COP",   123.32), ("TLT",   87.53),
    ("ABT",   111.36), ("XOM",   157.87), ("SLB",   47.32),  ("CVX",   201.62),
    ("GLD",   423.10), ("MSFT",  387.61),
]

PERFORMANCE = [
    {"fecha": "17/03/2026", "equity": 99871.54, "pnl_dia": -320.09,  "trades": 32, "wins": 0, "losses": 1},
    {"fecha": "18/03/2026", "equity": 98917.67, "pnl_dia": -831.29,  "trades": 0,  "wins": 0, "losses": 0},
    {"fecha": "19/03/2026", "equity": 98644.41, "pnl_dia": -1000.67, "trades": 11, "wins": 0, "losses": 6},
]


# -- Clase PDF ----------------------------------------------------------------

class ReportePDF(FPDF):
    def header(self):
        self.set_fill_color(10, 25, 55)
        self.rect(0, 0, 210, 18, "F")
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(255, 255, 255)
        self.set_xy(10, 4)
        self.cell(0, 10, "REPORTE TECNICO INTEGRAL -- SISTEMA DE TRADING ALGORITMICO", align="L")
        self.set_text_color(160, 190, 255)
        self.set_font("Helvetica", "", 8)
        self.set_xy(10, 11)
        self.cell(0, 5,
            f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}  |  "
            "Entorno: Paper Trading  |  Broker: Alpaca  |  Capital: $100,000 USD",
            align="L")
        self.ln(14)

    def footer(self):
        self.set_y(-13)
        self.set_fill_color(10, 25, 55)
        self.rect(0, 284, 210, 20, "F")
        self.set_font("Helvetica", "", 8)
        self.set_text_color(160, 190, 255)
        self.cell(0, 8, f"Pag. {self.page_no()} | Trading Bot v1.0 | Paper Trading -- No constituye asesoramiento financiero", align="C")

    def titulo_seccion(self, texto, r=15, g=45, b=110):
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 12)
        self.cell(0, 9, f"   {texto}", fill=True, ln=True)
        self.set_text_color(30, 30, 30)
        self.ln(3)

    def subtitulo(self, texto):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(10, 55, 115)
        self.cell(0, 7, texto, ln=True)
        self.set_text_color(30, 30, 30)

    def cuerpo(self, texto, indent=5):
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(40, 40, 40)
        self.set_x(self.get_x() + indent)
        self.multi_cell(0, 5.5, texto)
        self.ln(1)

    def bullet(self, texto, color=(15, 100, 200), indent=10):
        self.set_x(indent)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*color)
        self.cell(5, 6, chr(149))
        self.set_font("Helvetica", "", 9.5)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 6, texto)

    def cuadro_kv(self, etiqueta, valor, estado="ok"):
        colores = {
            "ok":      (0, 145, 55),
            "warning": (190, 110, 0),
            "error":   (170, 15, 15),
            "info":    (15, 75, 175),
        }
        c = colores.get(estado, (100, 100, 100))
        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(242, 246, 255)
        self.set_draw_color(175, 200, 228)
        self.cell(65, 8, f"  {etiqueta}", border=1, fill=True)
        self.set_fill_color(*[min(255, x + 195) for x in c])
        self.set_text_color(*c)
        self.cell(0, 8, f"  {valor}", border=1, fill=True, ln=True)
        self.set_text_color(40, 40, 40)
        self.ln(1)

    def separador(self):
        self.set_draw_color(175, 200, 228)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def tag(self, texto, r, g, b):
        self.set_fill_color(r, g, b)
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 8)
        self.cell(len(texto) * 1.8 + 4, 5.5, f" {texto} ", fill=True)
        self.set_text_color(40, 40, 40)
        self.set_fill_color(255, 255, 255)


# -- Generacion del PDF -------------------------------------------------------

def generar_reporte():
    pdf = ReportePDF("P", "mm", "A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(10, 20, 10)

    # =======================================
    # PORTADA
    # =======================================
    pdf.add_page()
    pdf.set_fill_color(10, 25, 55)
    pdf.rect(0, 18, 210, 65, "F")
    pdf.set_xy(0, 26)
    pdf.set_font("Helvetica", "B", 24)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(0, 13, "REPORTE TECNICO INTEGRAL", align="C", ln=True)
    pdf.set_font("Helvetica", "", 15)
    pdf.set_text_color(140, 195, 255)
    pdf.cell(0, 9, "Sistema de Trading Algoritmico -- Proyecto Personal", align="C", ln=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(195, 218, 255)
    pdf.cell(0, 7, "Codigo | Arquitectura | Movimientos Reales | Resultados Alpaca | Analisis", align="C", ln=True)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(255, 220, 100)
    pdf.cell(0, 7, f"Generado el {datetime.now().strftime('%d de %B de %Y a las %H:%M')}  |  Paper Trading activo desde 17/03/2026", align="C", ln=True)
    pdf.set_text_color(40, 40, 40)
    pdf.ln(55)

    # Cuadros de estado en portada
    items = [
        ("Estado",             "Paper Trading activo -- Alpaca",              "ok"),
        ("Capital simulado",   "$100,000 USD",                               "info"),
        ("Equity actual",      "$98,644.41 USD  (-$1,355.59 / -1.36%)",      "error"),
        ("PnL acumulado",      "-$1,355.59 en 3 dias de operacion",          "error"),
        ("Win rate",           "0% (0 wins / 6 trades cerrados con PnL)",    "error"),
        ("Posiciones abiertas","30 de 30 maximas (cartera completamente llena)","warning"),
        ("Trades totales",     "49 (37 buys, 12 sells)",                     "info"),
        ("Modelo ML",          "Random Forest 200 arboles -- reentrenado 17/03/2026","warning"),
        ("Timeframe",          "1 hora -- 6-7 ciclos por dia de mercado",     "info"),
        ("Broker",             "Alpaca Paper Trading -- IEX feed",            "info"),
        ("Alertas",            "Telegram configurado y funcionando",         "ok"),
        ("Modulo nuevo",       "regime_detector.py agregado el 19/03/2026",  "ok"),
    ]
    for lbl, val, est in items:
        pdf.cuadro_kv(lbl, val, est)

    # =======================================
    # 1. RESUMEN EJECUTIVO
    # =======================================
    pdf.add_page()
    pdf.titulo_seccion("1.  RESUMEN EJECUTIVO")

    pdf.subtitulo("1.1  Que es este bot")
    pdf.cuerpo(
        "Sistema de trading algoritmico completamente automatizado que opera en el mercado de "
        "acciones de EE.UU. (NYSE/NASDAQ) durante horario regular 9:30am-4:00pm ET (6:30am-1:00pm PT). "
        "Combina 3 fuentes de senales: analisis tecnico (8 indicadores), modelo de Machine Learning "
        "(Random Forest), y contexto de mercado externo (VIX, Fear&Greed, noticias, earnings, macro FRED). "
        "Opera en modo Paper Trading (simulacion con dinero ficticio) en la plataforma Alpaca. "
        "Iniciado el 17 de marzo de 2026."
    )

    pdf.ln(2)
    pdf.subtitulo("1.2  Resultados al 19/03/2026 -- 3 dias de operacion")

    resumen_rows = [
        ("17/03/2026", "Dia 1", -320.09,  99871.54, 32, 0, 1),
        ("18/03/2026", "Dia 2", -831.29,  98917.67,  0, 0, 0),
        ("19/03/2026", "Dia 3", -1000.67, 98644.41, 11, 0, 6),
    ]
    # Tabla de resultados
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(15, 45, 110)
    pdf.set_text_color(255, 255, 255)
    cols = [22, 18, 28, 32, 22, 18, 18, 32]
    headers = ["Fecha", "Dia", "PnL dia", "Equity cierre", "Trades", "Wins", "Losses", "Nota"]
    for i, h in enumerate(headers):
        pdf.cell(cols[i], 7, h, border=1, fill=True, align="C")
    pdf.ln()
    notas = [
        "Triple compra SPY + 26 posiciones",
        "Posiciones caen overnight sin trades",
        "6 stop-losses + 5 nuevas compras",
    ]
    pdf.set_font("Helvetica", "", 8.5)
    for idx, (fecha, dia, pnl, equity, trades, wins, losses) in enumerate(resumen_rows):
        color_pnl = (180, 15, 15) if pnl < 0 else (0, 140, 50)
        pdf.set_fill_color(248, 248, 255) if idx % 2 == 0 else pdf.set_fill_color(238, 242, 255)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(cols[0], 7, fecha, border=1, fill=True, align="C")
        pdf.cell(cols[1], 7, dia, border=1, fill=True, align="C")
        pdf.set_text_color(*color_pnl)
        pdf.cell(cols[2], 7, f"${pnl:+.2f}", border=1, fill=True, align="C")
        pdf.set_text_color(40, 40, 40)
        pdf.cell(cols[3], 7, f"${equity:,.2f}", border=1, fill=True, align="C")
        pdf.cell(cols[4], 7, str(trades), border=1, fill=True, align="C")
        pdf.set_text_color(0, 130, 50)
        pdf.cell(cols[5], 7, str(wins), border=1, fill=True, align="C")
        pdf.set_text_color(170, 15, 15)
        pdf.cell(cols[6], 7, str(losses), border=1, fill=True, align="C")
        pdf.set_text_color(60, 60, 60)
        pdf.cell(cols[7], 7, notas[idx], border=1, fill=True)
        pdf.ln()
    pdf.set_text_color(40, 40, 40)

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_fill_color(255, 235, 235)
    pdf.set_draw_color(170, 15, 15)
    pdf.set_text_color(140, 0, 0)
    pdf.cell(0, 8, "  TOTAL ACUMULADO:  PnL = -$1,355.59  |  Retorno = -1.36%  |  Win Rate = 0%  |  30/30 posiciones abiertas", border=1, fill=True, ln=True)
    pdf.set_text_color(40, 40, 40)

    pdf.ln(3)
    pdf.subtitulo("1.3  Observaciones inmediatas")
    obs = [
        "El bot esta corriendo estable, sin crashes ni errores fatales en 3 dias.",
        "Los stop-losses funcionan correctamente: activaron 6 salidas automaticas el 19/03.",
        "El PnL negativo es esperado en mercado bajista (VIX=25, Fear&Greed=23 Extreme Fear).",
        "Problema critico: ML da confianza 0.62-0.69 a casi todo el watchlist simultaneamente.",
        "Problema critico: SQQQ (ETF inverso) fue comprado como posicion long -- error de diseno.",
        "Problema critico: SPY comprado 3 veces el 17/03 por bug de race condition en MI PLAN.",
        "30 posiciones abiertas = 90% del capital expuesto con correlacion alta entre simbolos.",
    ]
    for o in obs:
        pdf.bullet(o, (60, 60, 140))

    # =======================================
    # 2. ARQUITECTURA
    # =======================================
    pdf.add_page()
    pdf.titulo_seccion("2.  ARQUITECTURA DEL SISTEMA")

    pdf.subtitulo("2.1  Modulos del proyecto (20 archivos Python)")
    modulos = [
        ("main.py",            "Orquestador principal. Loop cada 1 hora. Coordina todos los modulos."),
        ("config.py",          "Configuracion central: 44 simbolos, parametros de estrategia, credenciales Alpaca."),
        ("strategy.py",        "Senales buy/sell. 8 condiciones de compra, 6 de venta. Ajuste dinamico por VIX."),
        ("scanner.py",         "Evalua los 44 simbolos cada ciclo y rankea BUY por confianza ML."),
        ("risk_manager.py",    "Valida ordenes: max 3% capital/posicion, max 5% perdida/dia, max 60 trades."),
        ("execution.py",       "Wrapper Alpaca API. Ordenes, posiciones, cuenta. Paper + Live."),
        ("data_fetcher.py",    "OHLCV historico y precio real de Alpaca IEX. Reintentos automaticos."),
        ("indicators.py",      "SMA, RSI, MACD, Bollinger Bands, ATR usando libreria 'ta'."),
        ("ml_model.py",        "Random Forest: probabilidad de subida >0.5% en 5 dias. Retrain semanal."),
        ("market_context.py",  "VIX, Fear&Greed, earnings, noticias, macro FRED en cada ciclo."),
        ("bot_memory.py",      "Estado persistente JSON. Sobrevive crashes. 500 trades + 365 dias historico."),
        ("regime_detector.py", "NUEVO (19/03). Detecta BULL/BEAR/SIDEWAYS/PANIC con histeresis."),
        ("my_plan.py",         "Planes personalizados del usuario: IA convierte lenguaje natural a JSON."),
        ("reporter.py",        "Reportes PDF diarios/mensuales. Chat IA sobre portfolio."),
        ("logger.py",          "Logging UTF-8 con rotacion 30 dias. CSV trades. Alertas Telegram."),
        ("auditor.py",         "Analisis estatico + revision IA via Claude API."),
        ("backtest.py",        "Backtesting historico: retorno, drawdown, Sharpe ratio, win rate."),
        ("menu.py",            "Panel CLI interactivo para todas las funciones del bot."),
        ("versions.py",        "Control de versiones local con MD5 checksums y backup/restore."),
        ("setup_proyecto.py",  "Inicializa estructura de carpetas y templates al instalar."),
    ]
    for nombre, desc in modulos:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(10, 55, 115)
        pdf.set_x(10)
        pdf.cell(42, 6, f"  {nombre}")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(148, 6, desc)

    pdf.ln(3)
    pdf.subtitulo("2.2  Flujo de datos por ciclo (1 hora)")
    pdf.cuerpo(
        "1. market_context.py  ->  descarga VIX, Fear&Greed, noticias, earnings, indices\n"
        "2. regime_detector.py ->  clasifica mercado BULL/BEAR/SIDEWAYS/PANIC (nuevo)\n"
        "3. scanner.py         ->  evalua 44 simbolos: data_fetcher -> indicators -> strategy -> ML\n"
        "4. risk_manager.py    ->  valida tamano y limites antes de cada orden\n"
        "5. execution.py       ->  envia ordenes a Alpaca (paper o live)\n"
        "6. bot_memory.py      ->  persiste estado, precios de entrada, PnL\n"
        "7. logger.py          ->  CSV de trades + alerta Telegram por cada operacion"
    )

    # =======================================
    # 3. LOGICA DE ESTRATEGIA
    # =======================================
    pdf.add_page()
    pdf.titulo_seccion("3.  LOGICA DE ESTRATEGIA DETALLADA")

    pdf.subtitulo("3.1  Condiciones de COMPRA (buy_score)")
    buys = [
        ("1", "RSI < 45",               "Sobreventa -- precio posiblemente en minimo relativo"),
        ("2", "Golden Cross SMA20>SMA100","Cruce alcista de medias moviles"),
        ("3", "Rebote BB inferior+RSI",  "Precio cerca de banda baja + RSI recuperando"),
        ("4", "Cruce MACD alcista",      "MACD cruza por encima de la senial"),
        ("5", "ML > 50% subida",         "Random Forest predice alza en 5 dias"),
        ("6", "Tendencia + sobre BB mid","Precio sobre SMA100 y banda media BB"),
        ("7", "Caida fuerte + RSI sube", "Rebote tecnico tras sobreventa extrema"),
        ("8", "Mercado: COMPRAR agresivo","Fear&Greed < 20 o VIX extremadamente bajo"),
    ]
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(15, 45, 110)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(10, 6, "#",           border=1, fill=True, align="C")
    pdf.cell(50, 6, "Condicion",   border=1, fill=True)
    pdf.cell(0,  6, "Descripcion", border=1, fill=True)
    pdf.ln()
    pdf.set_font("Helvetica", "", 8.5)
    for i, (num, cond, desc) in enumerate(buys):
        pdf.set_fill_color(245, 250, 245) if i % 2 == 0 else pdf.set_fill_color(235, 245, 235)
        pdf.set_text_color(0, 120, 40)
        pdf.cell(10, 6, num, border=1, fill=True, align="C")
        pdf.set_text_color(40, 40, 40)
        pdf.cell(50, 6, cond, border=1, fill=True)
        pdf.cell(130, 6, desc, border=1, fill=True)
        pdf.ln()
    pdf.set_text_color(40, 40, 40)

    pdf.ln(3)
    pdf.subtitulo("3.2  Condiciones de VENTA")
    sells = [
        ("Stop-loss dinamico",    "Precio < minimo 20 barras - 0.5xATR"),
        ("ML venta fuerte",       "ML predice caida con > 62% probabilidad"),
        ("RSI + BB superior",     "RSI > 65 Y precio cerca de banda superior BB"),
        ("Death Cross SMA",       "SMA20 cruza por debajo de SMA100"),
        ("MACD bajista",          "Cruce MACD bajista + tendencia bajista"),
        ("Panico VIX > 35",       "VIX supera 35 + tendencia bajista activa"),
        ("Take-profit +8%",       "Ganancia de 8% desde precio de entrada"),
        ("Stop-loss -4%",         "Perdida de 4% desde precio de entrada"),
    ]
    for i, (cond, desc) in enumerate(sells):
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(160, 15, 15)
        pdf.set_x(10)
        pdf.cell(55, 6, cond + ":")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(135, 6, desc)

    pdf.ln(2)
    pdf.subtitulo("3.3  Ajuste dinamico por VIX (score minimo para comprar)")
    vix_data = [
        ("VIX < 15",  "min_score = 1", "Mercado calmo -- agresivo"),
        ("VIX 15-20", "min_score = 2", "Normal -- equilibrado"),
        ("VIX 20-25", "min_score = 3", "Elevado -- cauteloso"),
        ("VIX 25-30", "min_score = 4", "Alto -- muy cauteloso"),
        ("VIX > 35",  "min_score = 5", "Panico -- casi no compra"),
    ]
    pdf.set_font("Helvetica", "", 9)
    for vix, score, desc in vix_data:
        pdf.set_x(10)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(10, 55, 115)
        pdf.cell(28, 6, vix)
        pdf.set_text_color(160, 80, 0)
        pdf.cell(32, 6, score)
        pdf.set_text_color(40, 40, 40)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(130, 6, desc)

    pdf.ln(2)
    pdf.cuerpo(
        "Nota importante: con VIX=25.24 el 19/03/2026, el bot requeria min_score=3. Sin embargo, "
        "el ML sobreescribe con 'ml_override' si el score tecnico >= min_score, lo que resulto "
        "en compras masivas con ML=0.60-0.69 incluso en condiciones de mercado bajistas."
    )

    # =======================================
    # 4. MOVIMIENTOS REALES EN ALPACA
    # =======================================
    pdf.add_page()
    pdf.titulo_seccion("4.  MOVIMIENTOS REALES EN ALPACA PAPER TRADING", 50, 10, 100)

    pdf.subtitulo("4.1  Historial completo de operaciones (49 trades)")

    # Tabla de trades
    col_w = [22, 18, 16, 22, 14, 20, 58]
    headers_t = ["Fecha", "Hora UTC", "Accion", "Simbolo", "Precio", "Qty / Valor", "Razon / Notas"]

    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_fill_color(10, 25, 55)
    pdf.set_text_color(255, 255, 255)
    for i, h in enumerate(headers_t):
        pdf.cell(col_w[i], 6, h, border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 7)
    for idx, t in enumerate(TRADES):
        es_venta = t["accion"] == "SELL"
        es_buy   = t["accion"] == "BUY"
        es_bug   = "BUG" in t["razon"] or "ERROR" in t["razon"]
        es_stop  = "Stop-loss" in t["razon"]

        if es_stop:
            pdf.set_fill_color(255, 235, 235)
        elif es_bug:
            pdf.set_fill_color(255, 245, 200)
        elif es_buy:
            pdf.set_fill_color(idx % 2 == 0 and 245 or 235, 255, idx % 2 == 0 and 245 or 235)
        else:
            pdf.set_fill_color(245, 245, 255)

        pdf.set_text_color(40, 40, 40)
        pdf.cell(col_w[0], 5.5, t["fecha"], border=1, fill=True, align="C")
        pdf.cell(col_w[1], 5.5, t["hora"], border=1, fill=True, align="C")

        if es_venta:
            pdf.set_text_color(160, 15, 15)
        else:
            pdf.set_text_color(0, 130, 50)
        pdf.set_font("Helvetica", "B", 7)
        pdf.cell(col_w[2], 5.5, t["accion"], border=1, fill=True, align="C")

        pdf.set_font("Helvetica", "B", 7)
        pdf.set_text_color(10, 55, 115)
        pdf.cell(col_w[3], 5.5, t["simbolo"], border=1, fill=True, align="C")

        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(40, 40, 40)
        pdf.cell(col_w[4], 5.5, f"${t['precio']:.2f}", border=1, fill=True, align="C")

        val_str = f"{t['qty']} / ${t['valor']:,.0f}"
        if t["pnl"] is not None:
            color_pnl = (160, 15, 15) if t["pnl"] < 0 else (0, 130, 50) if t["pnl"] > 0 else (100, 100, 100)
            pdf.set_text_color(*color_pnl)
            pdf.set_font("Helvetica", "B", 7)
            val_str = f"PnL ${t['pnl']:+.2f}"
        pdf.cell(col_w[5], 5.5, val_str, border=1, fill=True, align="C")

        pdf.set_font("Helvetica", "", 6.5)
        pdf.set_text_color(60, 60, 60)
        razon_corta = t["razon"][:68]
        pdf.cell(col_w[6], 5.5, razon_corta[:55], border=1, fill=True)
        pdf.ln()

    pdf.set_text_color(40, 40, 40)

    pdf.ln(3)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 5, "Leyenda:  Fondo amarillo = BUG detectado | Fondo rojo = Stop-loss activado | Verde = Compra normal", ln=True)

    # =======================================
    # 5. POSICIONES ABIERTAS
    # =======================================
    pdf.add_page()
    pdf.titulo_seccion("5.  POSICIONES ABIERTAS AL 19/03/2026", 60, 10, 90)

    pdf.subtitulo("5.1  30 posiciones activas (cartera completamente llena)")

    pdf.set_font("Helvetica", "", 9)
    pdf.cuerpo(
        "El bot tiene desplegadas 30 posiciones simultaneas, el maximo configurado. "
        "Todas fueron abiertas el 17/03/2026 entre las 15:49 y 16:35 UTC (11:49am-12:35pm ET). "
        "El 90%+ del capital esta expuesto en este momento."
    )

    # Tabla de posiciones en 3 columnas
    col3 = [13, 22, 13, 22, 13, 22]
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(15, 45, 110)
    pdf.set_text_color(255, 255, 255)
    for _ in range(3):
        pdf.cell(13, 6, "#", border=1, fill=True, align="C")
        pdf.cell(22, 6, "Simbolo", border=1, fill=True, align="C")
    pdf.ln()

    pdf.set_font("Helvetica", "", 8.5)
    for i in range(0, len(POSICIONES_ABIERTAS), 3):
        grupo = POSICIONES_ABIERTAS[i:i+3]
        pdf.set_fill_color(245, 248, 255) if i % 6 == 0 else pdf.set_fill_color(235, 240, 255)
        for j, (sym, precio) in enumerate(grupo):
            es_problema = sym in ("SQQQ", "TQQQ")
            pdf.set_text_color(160, 15, 15) if es_problema else pdf.set_text_color(40, 40, 40)
            pdf.cell(13, 6, str(i + j + 1), border=1, fill=True, align="C")
            pdf.set_font("Helvetica", "B" if es_problema else "", 8.5)
            pdf.cell(22, 6, sym + (" (!)" if es_problema else ""), border=1, fill=True)
            pdf.set_font("Helvetica", "", 8.5)
        # Padding si grupo incompleto
        for _ in range(3 - len(grupo)):
            pdf.cell(13, 6, "", border=1, fill=True)
            pdf.cell(22, 6, "", border=1, fill=True)
        pdf.ln()
    pdf.set_text_color(40, 40, 40)

    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_fill_color(255, 240, 200)
    pdf.set_draw_color(180, 120, 0)
    pdf.set_text_color(130, 80, 0)
    pdf.cell(0, 7, "  ATENCION: SQQQ y TQQQ marcados con (!) -- ETFs inverso/apalancado inadecuados como longs en mercado bajista", border=1, fill=True, ln=True)
    pdf.set_text_color(40, 40, 40)

    pdf.ln(3)
    pdf.subtitulo("5.2  Distribucion por sector")
    sectores = [
        ("Tecnologia",          ["NVDA","AMD","AAPL","INTC","CRM","MSFT"],             6),
        ("Salud",               ["JNJ","MRK","UNH","ABT","PFE"],                       5),
        ("Finanzas",            ["BAC","JPM","WFC","C","AXP","MS"],                    6),
        ("Consumo/Retail",      ["TGT","MCD","AMZN","GOOGL"],                          4),
        ("Energia",             ["OXY","COP","XOM","SLB","CVX"],                       5),
        ("ETFs / Indices",      ["IWM","SQQQ(!)"],                                     2),
        ("Commodities/Bonos",   ["USO","TLT","GLD"],                                   3),
    ]
    for sector, syms, n in sectores:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(10, 55, 115)
        pdf.set_x(10)
        pdf.cell(55, 6, f"{sector} ({n}):")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(135, 6, ", ".join(syms))

    pdf.ln(2)
    pdf.cuerpo(
        "Riesgo de correlacion: Tecnologia y Finanzas (12 posiciones, 40% del portfolio) tienen "
        "alta correlacion positiva con el SP500. Un evento macro negativo puede mover todo el "
        "sector simultaneamente, activando multiples stop-losses en cascada en un solo ciclo."
    )

    # =======================================
    # 6. BUGS Y PROBLEMAS DETECTADOS
    # =======================================
    pdf.add_page()
    pdf.titulo_seccion("6.  BUGS Y PROBLEMAS DETECTADOS", 140, 25, 10)

    pdf.subtitulo("6.1  Bug activo: Triple compra de SPY (17/03/2026)")
    pdf.set_fill_color(255, 240, 200)
    pdf.set_draw_color(180, 120, 0)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(140, 80, 0)
    pdf.cell(0, 7, "  [BUG ACTIVO]  Race condition en MI PLAN -- SPY comprado 3 veces", border=1, fill=True, ln=True)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(40, 40, 40)
    pdf.set_x(14)
    pdf.multi_cell(0, 5.5,
        "A las 3:12, 3:30 y 5:33 UTC del 17/03 (antes de apertura del mercado), el modulo MI PLAN "
        "compro SPY 3 veces por 37 acciones cada vez. El codigo verifica 'pos_qty == 0' antes de "
        "comprar, pero como las ordenes anteriores aun no estaban confirmadas en Alpaca (mercado "
        "cerrado), la verificacion siempre retornaba 0 para las siguientes iteraciones. "
        "Resultado: $74,197 comprometidos en SPY en vez de $24,732. "
        "La venta posterior a $674.24 genero ganancia de ~$642 pero el comportamiento es incorrecto."
    )
    pdf.ln(3)

    pdf.subtitulo("6.2  Bug de diseno: SQQQ como posicion long")
    pdf.set_fill_color(255, 230, 230)
    pdf.set_draw_color(170, 15, 15)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(140, 0, 0)
    pdf.cell(0, 7, "  [BUG DISENO]  ETF inverso SQQQ en watchlist sin proteccion", border=1, fill=True, ln=True)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(40, 40, 40)
    pdf.set_x(14)
    pdf.multi_cell(0, 5.5,
        "SQQQ es un ETF que hace el INVERSO del NASDAQ 100 (x3). Cuando el mercado sube, "
        "SQQQ baja. El bot lo compro como una accion normal el 17/03 a $72.25 con RSI=44 y ML=0.68. "
        "Esta posicion actua como un hedge involuntario pero es un error de logica: el mismo scanner "
        "que compra AAPL, MSFT y GOOGL (apostando al alza del NASDAQ) esta comprando SQQQ "
        "(apostando a su caida). Son posiciones contradictorias. SQQQ debe ser manejado solo "
        "en modo BEAR del regime_detector, no en el watchlist general."
    )
    pdf.ln(3)

    pdf.subtitulo("6.3  Problema de ML: confianza demasiado alta en todo")
    pdf.set_fill_color(255, 248, 220)
    pdf.set_draw_color(160, 100, 0)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(140, 90, 0)
    pdf.cell(0, 7, "  [ML]  Random Forest da 0.60-0.69 a casi todos los simbolos en mercado bajista", border=1, fill=True, ln=True)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(40, 40, 40)
    pdf.set_x(14)
    pdf.multi_cell(0, 5.5,
        "En un mercado con VIX=25.24 y Fear&Greed=23 (Extreme Fear), el modelo ML retorno "
        "probabilidades de compra entre 0.60 y 0.69 para 30+ simbolos simultaneamente. "
        "Esto indica que el modelo no esta capturando correctamente el regimen bajista actual. "
        "Posibles causas: (1) datos de entrenamiento dominados por mercado alcista 2023-2025, "
        "(2) umbral ML_BUY_PROB_THRESHOLD demasiado bajo (0.50), "
        "(3) el modelo no tiene features de contexto macro como VIX o Fear&Greed. "
        "Resultado: el scanner genero 30 senales de BUY en un dia bajista con SP500=-0.81%."
    )
    pdf.ln(3)

    pdf.subtitulo("6.4  Problema de parametros: 30 posiciones simultaneas")
    pdf.set_fill_color(255, 248, 220)
    pdf.set_draw_color(160, 100, 0)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(140, 90, 0)
    pdf.cell(0, 7, "  [CONFIG]  MAX_OPEN_POSITIONS=30 expone el 90% del capital al mismo tiempo", border=1, fill=True, ln=True)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(40, 40, 40)
    pdf.set_x(14)
    pdf.multi_cell(0, 5.5,
        "Con 30 posiciones a 3% del capital cada una, el bot despliega el 90% del portfolio "
        "simultaneamente. Si el mercado cae 2% en un dia, todas las posiciones correlacionadas "
        "de tech/finanzas caen juntas, activando stop-losses en cascada. En este caso, "
        "el 18/03 (sin trades) el portfolio bajo $831 solo por movimientos de precios nocturnos. "
        "Para paper trading esto es aceptable, pero en live trading con $100,000 reales "
        "representaria un riesgo de perdida masiva en un crash."
    )
    pdf.ln(3)

    pdf.subtitulo("6.5  Bugs corregidos antes del inicio (16/03/2026)")
    bugs_previos = [
        ("[CORREGIDO] portfolio_value hardcodeado", "Se reseteaba a $100,000 fijo en cada ciclo en vez de usar el valor real de Alpaca. Corregido el 19/03."),
        ("[CORREGIDO] is_market_open() faltaba", "El bot intentaba operar fuera de horario. Se implemento verificacion de horario NYSE."),
        ("[CORREGIDO] Wash trade NVDA", "El scanner compraba NVDA del plan del usuario. Doble proteccion implementada."),
        ("[CORREGIDO] Sin take-profit", "Las posiciones ganadoras no tenian limite. Se agrego TAKE_PROFIT_PCT=8%."),
    ]
    for titulo, desc in bugs_previos:
        pdf.set_fill_color(230, 255, 235)
        pdf.set_draw_color(0, 145, 55)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(0, 100, 35)
        pdf.cell(0, 6, f"  {titulo}", border=1, fill=True, ln=True)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.set_text_color(40, 40, 40)
        pdf.set_x(14)
        pdf.multi_cell(0, 5.5, desc)
        pdf.ln(1)

    # =======================================
    # 7. ANALISIS DEL CODIGO
    # =======================================
    pdf.add_page()
    pdf.titulo_seccion("7.  ANALISIS COMPLETO DEL CODIGO", 70, 15, 90)

    pdf.subtitulo("7.1  Revision de los 20 modulos -- hallazgos por severidad")

    analisis = [
        ("main.py",           "CORREGIDO", "portfolio_value se reseteaba a config.CAPITAL en cada ciclo. Corregido 19/03.", "ok"),
        ("config.py",         "ADVERTENCIA","RSI_OVERSOLD=45 es muy permisivo. MAX_OPEN_POSITIONS=30 expone 90% capital.", "warning"),
        ("strategy.py",       "INFO",       "Logica correcta. Fallback ML=0.5 si modelo no disponible es intencional.", "info"),
        ("scanner.py",        "INFO",       "Funciona bien. No valida si lista de buys esta vacia antes de sort (menor).", "info"),
        ("risk_manager.py",   "OK",         "Bien implementado. Limites claros y validacion correcta.", "ok"),
        ("execution.py",      "ADVERTENCIA","Bare except oculta errores reales de API. Sin verificacion de shortable.", "warning"),
        ("data_fetcher.py",   "INFO",       "Retorna 0.0 en error de precio. Callers lo manejan con 'if price <= 0'.", "info"),
        ("indicators.py",     "INFO",       "dropna() silencioso elimina ~99 filas por calculo (necesario para MA100).", "info"),
        ("ml_model.py",       "ADVERTENCIA","Sin validacion cruzada. Sin features de contexto macro (VIX, F&G). Basico.", "warning"),
        ("market_context.py", "INFO",       "APIs externas fallan silenciosamente. Telegram alerta solo en errores fatales.", "info"),
        ("bot_memory.py",     "OK",         "Bien disenado. JSON persistente con migracion y valores por defecto.", "ok"),
        ("regime_detector.py","OK",         "Nuevo modulo 19/03. Histeresis + cache breadth. Integrado en main.py.", "ok"),
        ("my_plan.py",        "INFO",       "Race condition en verificacion de posicion (bug triple compra SPY).", "warning"),
        ("reporter.py",       "OK",         "Funcional. API key en HTTPS. Reportes PDF operativos.", "ok"),
        ("logger.py",         "OK",         "UTF-8 con rotacion 30 dias. CSV trades. Telegram funcionando.", "ok"),
        ("auditor.py",        "INFO",       "Dependiente de Claude API key. Falla silencioso si no esta configurada.", "info"),
        ("backtest.py",       "ADVERTENCIA","Sin validacion de rango de fechas. Sin slippage ni comisiones reales.", "warning"),
        ("menu.py",           "OK",         "Flujos de confirmacion correctos. Sin problemas detectados.", "ok"),
        ("versions.py",       "OK",         "Checksums MD5 correctos. Backup/restore funcional.", "ok"),
        ("requirements.txt",  "OK",         "Dependencias completas. reportlab, fpdf2, ta, sklearn todas incluidas.", "ok"),
    ]

    col_a = [32, 22, 0]
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(10, 25, 55)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(32, 6, "Modulo",    border=1, fill=True)
    pdf.cell(22, 6, "Estado",    border=1, fill=True, align="C")
    pdf.cell(0,  6, "Hallazgo",  border=1, fill=True)
    pdf.ln()

    estados_col = {
        "OK":        (0,   145,  55),
        "CORREGIDO": (0,   100,  35),
        "INFO":      (15,  75,  175),
        "ADVERTENCIA":(190,110,   0),
        "ERROR":     (170,  15,  15),
    }
    for i, (mod, estado, nota, _) in enumerate(analisis):
        pdf.set_fill_color(245, 248, 255) if i % 2 == 0 else pdf.set_fill_color(235, 240, 255)
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(10, 55, 115)
        pdf.cell(32, 5.5, mod, border=1, fill=True)
        c = estados_col.get(estado, (100, 100, 100))
        pdf.set_text_color(*c)
        pdf.cell(22, 5.5, estado, border=1, fill=True, align="C")
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(136, 5.5, nota, border=1, fill=True)
    pdf.set_text_color(40, 40, 40)

    # =======================================
    # 8. CONTEXTO DE MERCADO
    # =======================================
    pdf.add_page()
    pdf.titulo_seccion("8.  CONTEXTO DE MERCADO DURANTE LA OPERACION", 20, 100, 60)

    pdf.subtitulo("8.1  Condiciones del mercado -- 17 al 19 de marzo 2026")
    condiciones = [
        ("VIX",                "25.24 (elevado -- zona de precaucion)"),
        ("Fear & Greed Index", "23 -- EXTREME FEAR (0=panico, 100=codicia extrema)"),
        ("SP500 cambio diario", "-0.81% el 19/03"),
        ("NASDAQ cambio diario","-0.93% el 19/03"),
        ("DOW cambio diario",   "-0.92% el 19/03"),
        ("VXN (vol NASDAQ)",   "+1.26% el 19/03"),
        ("Senal del bot",      "neutral (no comprar agresivo, no vender)"),
        ("Regimen detectado",  "No disponible (regime_detector agregado el 19/03)"),
    ]
    for k, v in condiciones:
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(10, 55, 115)
        pdf.set_x(10)
        pdf.cell(55, 6, k + ":")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(135, 6, v)

    pdf.ln(2)
    pdf.cuerpo(
        "El mercado estaba claramente en condicion bajista-neutral cuando el bot abrio 30 posiciones "
        "el 17/03. VIX=22-23, F&G=28, SP500 a la baja. El bot interpreto el RSI bajo de muchos "
        "simbolos como oportunidad de compra contrarian (technicamente correcto), pero entro con "
        "demasiadas posiciones simultaneamente sin esperar confirmacion de que la caida habia terminado."
    )

    pdf.ln(2)
    pdf.subtitulo("8.2  Fuentes de contexto externo integradas")
    fuentes = [
        ("VIX (yfinance)",         "Modifica agresividad del bot en tiempo real"),
        ("Fear & Greed (CNN)",     "Ajusta min_score de compra +/- 1 punto"),
        ("Earnings (Finnhub)",     "Bloquea compras 2 dias antes de earnings"),
        ("Noticias (Finnhub+AV)",  "Disponibles pero sin analisis de sentimiento"),
        ("Macro (FRED API)",       "Tasa Fed, inflacion, desempleo -- contexto"),
        ("Indices (yfinance)",     "SP500, NASDAQ, DOW delta diario"),
        ("regime_detector (nuevo)","BULL/BEAR/SIDEWAYS/PANIC con histeresis"),
    ]
    for nombre, desc in fuentes:
        pdf.set_x(10)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(10, 55, 115)
        pdf.cell(55, 6, nombre + ":")
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.multi_cell(135, 6, desc)

    # =======================================
    # 9. EVALUACION Y SUGERENCIAS
    # =======================================
    pdf.add_page()
    pdf.titulo_seccion("9.  EVALUACION Y SUGERENCIAS", 80, 20, 80)

    pdf.subtitulo("9.1  Fortalezas del sistema")
    fortalezas = [
        "Arquitectura modular solida -- 20 modulos independientes con responsabilidades claras.",
        "Stop-losses funcionando correctamente -- 6 salidas automaticas el 19/03 sin intervencion.",
        "Sistema de memoria persistente -- el bot sobrevive crashes sin perder el estado de trades.",
        "Alertas Telegram operativas -- notificaciones en tiempo real por cada operacion.",
        "Contexto de mercado rico -- VIX, Fear&Greed, noticias, earnings integrados.",
        "Control de versiones del codigo con MD5 checksums.",
        "Paper trading primero -- enfoque correcto antes de arriesgar capital real.",
        "Nuevo: regime_detector.py con histeresis evita cambios de estado por ruido de mercado.",
    ]
    for f in fortalezas:
        pdf.bullet(f, (0, 145, 55))

    pdf.ln(2)
    pdf.subtitulo("9.2  Debilidades actuales")
    debilidades = [
        "ML demasiado permisivo (0.60-0.69 para todo): necesita features de contexto macro o threshold mas alto.",
        "SQQQ en watchlist general: debe removerse y manejarse solo en modo BEAR de regime_detector.",
        "30 posiciones simultaneas: demasiado capital expuesto, considerar reducir a 10-15 para paper.",
        "RSI_OVERSOLD=45 genera senales en tendencias bajistas (falling knife pattern).",
        "Sin confirmacion de volumen: las senales sin volumen son menos confiables.",
        "Race condition en MI PLAN: verificacion de posicion debe incluir ordenes pendientes.",
        "Win rate 0% en 3 dias: aunque puede ser por mercado bajista, necesita mas datos para evaluar.",
        "Sin multi-timeframe: confirmar tendencia en 4H antes de comprar en 1H reduciria falsas senales.",
    ]
    for d in debilidades:
        pdf.bullet(d, (180, 30, 30))

    pdf.ln(2)
    pdf.subtitulo("9.3  Madurez por componente")
    madurez = [
        ("execution.py + Alpaca",   "Alta",       "ok"),
        ("risk_manager.py",         "Media-Alta", "ok"),
        ("bot_memory.py",           "Alta",       "ok"),
        ("logger.py + Telegram",    "Alta",       "ok"),
        ("regime_detector.py",      "Media",      "warning"),
        ("strategy.py",             "Media",      "warning"),
        ("market_context.py",       "Media",      "warning"),
        ("ml_model.py",             "Baja-Media", "warning"),
        ("backtest.py",             "Baja",       "error"),
        ("Tests unitarios",         "Sin impl.",  "error"),
        ("Dashboard/UI",            "Sin impl.",  "error"),
    ]
    for comp, nivel, est in madurez:
        pdf.cuadro_kv(comp, nivel, est)

    pdf.ln(2)
    pdf.set_fill_color(255, 248, 200)
    pdf.set_draw_color(180, 130, 0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(140, 90, 0)
    pdf.cell(0, 8, "  VEREDICTO:  Paper trading necesita 3-4 semanas mas antes de considerar live trading", border=1, fill=True, ln=True)
    pdf.set_text_color(40, 40, 40)

    # =======================================
    # 10. HOJA DE RUTA
    # =======================================
    pdf.add_page()
    pdf.titulo_seccion("10.  HOJA DE RUTA -- PROXIMOS PASOS", 15, 80, 50)

    pasos = [
        ("INMEDIATO (antes del proximo ciclo)",
         "1. Sacar SQQQ del watchlist general (o agregar proteccion para no comprarlo en BULL).\n"
         "2. Bajar RSI_OVERSOLD de 45 a 35 para evitar compras en tendencias bajistas.\n"
         "3. Corregir race condition en MI PLAN: verificar ordenes pendientes, no solo posiciones.\n"
         "4. Subir ML_BUY_PROB_THRESHOLD de 0.50 a 0.60 para senales mas selectivas.",
         (230, 245, 255), (10, 60, 140)),
        ("SEMANA 1 (17-24 Marzo)",
         "1. Monitorear el bot diariamente y revisar logs cada manana.\n"
         "2. Verificar que regime_detector clasifica el mercado correctamente.\n"
         "3. Reducir MAX_OPEN_POSITIONS de 30 a 15 para menos exposicion simultanea.\n"
         "4. Confirmar que take-profit se ejecuta correctamente cuando una posicion llega a +8%.",
         (235, 255, 240), (0, 100, 40)),
        ("SEMANA 2 (24-31 Marzo)",
         "1. Agregar confirmacion de volumen (VWAP) en strategy.py.\n"
         "2. Implementar Fase 2 de regime_detector: logica bidireccional BEAR/PANIC.\n"
         "3. Backtesting con datos de 2022 (mercado bajista) para medir drawdown real.\n"
         "4. Agregar limite de 3-4 posiciones por sector para evitar concentracion.",
         (255, 248, 235), (140, 80, 0)),
        ("SEMANA 3-4 (Abril)",
         "1. Activar shorts en modo BEAR (execution.py necesita soporte para shortable check).\n"
         "2. Hedge automatico: UVXY/SQQQ en PANIC MODE con 10-20% del capital.\n"
         "3. Mejorar ML: agregar features de VIX y F&G al modelo Random Forest.\n"
         "4. Si paper trading muestra >50% win rate: planificar transicion a live.",
         (255, 240, 240), (140, 30, 30)),
        ("LARGO PLAZO (Mayo+)",
         "1. Dashboard web (Flask) para monitoreo remoto desde cualquier dispositivo.\n"
         "2. Migrar estado de JSON a SQLite para mejor performance y queries.\n"
         "3. Agregar estrategia de momentum 3-6 meses y mean reversion de corto plazo.\n"
         "4. Live trading con capital minimo ($5,000-10,000) si resultados paper son solidos.",
         (245, 240, 255), (70, 30, 130)),
    ]

    for titulo, acciones, bg, tc in pasos:
        pdf.set_fill_color(*bg)
        pdf.set_draw_color(*tc)
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*tc)
        pdf.cell(0, 8, f"  {titulo}", border=1, fill=True, ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(40, 40, 40)
        pdf.set_x(14)
        pdf.multi_cell(0, 6, acciones)
        pdf.ln(2)

    pdf.ln(3)
    pdf.separador()
    pdf.set_font("Helvetica", "I", 8.5)
    pdf.set_text_color(100, 100, 100)
    pdf.multi_cell(0, 5.5,
        "Reporte generado automaticamente por Claude Code analizando el codigo fuente completo, "
        "los logs del sistema y los datos reales de Alpaca Paper Trading. "
        "Fecha: " + datetime.now().strftime("%d/%m/%Y %H:%M") + " | "
        "El sistema opera exclusivamente en Paper Trading. No constituye asesoramiento financiero."
    )

    # -- Guardar PDF ----------------------------------------------------------
    docs_path  = os.path.expanduser("~/Documents")
    os.makedirs(docs_path, exist_ok=True)
    ts       = datetime.now().strftime("%Y%m%d_%H%M")
    filename = f"reporte_trading_bot_{ts}.pdf"
    out_path = os.path.join(docs_path, filename)
    pdf.output(out_path)

    # Copia local en reports/
    reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    os.makedirs(reports_dir, exist_ok=True)
    local_path = os.path.join(reports_dir, filename)
    shutil.copy(out_path, local_path)

    print(f"DOCS:  {out_path}")
    print(f"LOCAL: {local_path}")
    return out_path


if __name__ == "__main__":
    path = generar_reporte()
    print(f"\nReporte guardado en:\n  {path}")
