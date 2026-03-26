import os
from dotenv import load_dotenv
load_dotenv()

# Paper trading (simulado)
ALPACA_API_KEY    = os.getenv("ALPACA_API_KEY", "")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY", "")
ALPACA_BASE_URL   = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

# Cuenta real Individual Brokerage #192324566
LIVE_ALPACA_API_KEY    = os.getenv("LIVE_ALPACA_API_KEY", "")
LIVE_ALPACA_SECRET_KEY = os.getenv("LIVE_ALPACA_SECRET_KEY", "")

SYMBOL     = "SPY"   # simbolo de referencia (VIX, mercado context, retrain)
TIMEFRAME  = "1Hour" # horario: 6-7 ciclos por dia durante mercado
CAPITAL    = 100_000

# ── Watchlist multi-simbolo ───────────────────────────────────
WATCHLIST = [
    # ── ETFs Mercado Amplio (5) ──────────────────
    "SPY",   # S&P 500
    "QQQ",   # NASDAQ 100
    "IWM",   # Small Caps Russell 2000
    "DIA",   # Dow Jones
    "TQQQ",  # NASDAQ 3x apalancado

    # ── Tecnologia (8) ──────────────────────────
    "AAPL",  # Apple
    "MSFT",  # Microsoft
    "GOOGL", # Alphabet / Google
    "META",  # Meta (Facebook)
    "TSLA",  # Tesla
    "AMD",   # Advanced Micro Devices
    "INTC",  # Intel
    "CRM",   # Salesforce

    # ── Salud / Medicina (7) ────────────────────
    "JNJ",   # Johnson & Johnson
    "PFE",   # Pfizer
    "UNH",   # UnitedHealth Group
    "ABBV",  # AbbVie
    "MRK",   # Merck
    "LLY",   # Eli Lilly
    "ABT",   # Abbott Laboratories

    # ── Energia / Petroleo (6) ──────────────────
    "XOM",   # ExxonMobil
    "CVX",   # Chevron
    "OXY",   # Occidental Petroleum
    "SLB",   # Schlumberger
    "COP",   # ConocoPhillips
    "EOG",   # EOG Resources

    # ── Finanzas / Bancos (7) ───────────────────
    "JPM",   # JPMorgan Chase
    "BAC",   # Bank of America
    "GS",    # Goldman Sachs
    "MS",    # Morgan Stanley
    "WFC",   # Wells Fargo
    "C",     # Citigroup
    "AXP",   # American Express

    # ── Consumo / Retail (6) ────────────────────
    "AMZN",  # Amazon
    "WMT",   # Walmart
    "COST",  # Costco
    "HD",    # Home Depot
    "TGT",   # Target
    "MCD",   # McDonald's

    # ── Commodities / Bonos (ETFs) (5) ──────────
    "GLD",   # Oro
    "SLV",   # Plata
    "TLT",   # Bonos largo plazo
    "USO",   # Petroleo crudo
]

MAX_OPEN_POSITIONS = 12  # max posiciones simultaneas en cartera
MIN_SHARES_PER_BUY = 10  # minimo de acciones por orden de compra

# Simbolos permitidos en régimen BEAR (defensivos/refugio)
BEAR_SAFE_SYMBOLS = [
    "GLD",  # Oro — refugio clasico
    "TLT",  # Bonos largo plazo — refugio
    "USO",  # Petroleo crudo — commodity
    "XOM", "CVX", "COP", "OXY", "SLB", "EOG",  # Energia — resistente en BEAR
    "WMT", "COST",                               # Consumo basico — defensivo
    "JNJ", "PFE", "MRK", "ABBV", "LLY",         # Salud — defensivo
]

MA_SHORT_WINDOW        = 20   # ← Más reactivo (era 50)
MA_LONG_WINDOW         = 100  # ← Más reactivo (era 200)
ATR_PERIOD             = 14
STOP_LOSS_ATR_MULT     = 1.5  # ← Stop menos agresivo (era 2.0)
STOP_LOSS_LOOKBACK     = 20   # Barras para calcular el máximo del Chandelier Exit
BB_TOUCH_PCT           = 0.01 # % de tolerancia para considerar precio "cerca" de las bandas
RSI_PERIOD             = 14
RSI_OVERSOLD           = 35   # compra cuando RSI baja de 35 (mas selectivo)
RSI_OVERBOUGHT         = 65   # vende cuando RSI sube de 65 (zona de sobrecompra real)
BB_WINDOW              = 20
BB_STD                 = 2

ML_HORIZON             = 5
ML_THRESHOLD           = 0.005 # AGRESIVO: solo necesita subir 0.5% en 5 dias
ML_SELL_PROB_THRESHOLD = 0.62  # ML necesita >62% probabilidad de caida para vender
ML_BUY_PROB_THRESHOLD  = 0.62  # ML necesita >62% probabilidad de subida para comprar
RF_N_ESTIMATORS        = 200
RF_MAX_DEPTH           = 8
RF_RANDOM_STATE        = 42

MAX_DAILY_LOSS_PCT     = 0.05  # AGRESIVO: aguanta hasta 5% de perdida diaria
MAX_TRADES_PER_DAY     = 30    # suficiente para llenar 12 posiciones + rotaciones
MAX_POSITION_PCT       = 0.06  # Tamano de posicion (6% por trade — para 12 posiciones)
TAKE_PROFIT_PCT          = 0.08  # Vende automaticamente al ganar 8% desde entrada
STOP_LOSS_FROM_ENTRY_PCT = 0.04  # Vende automaticamente al perder 4% desde entrada
TRAILING_STOP_PCT        = 0.03  # Trailing stop: vende si cae 3% desde el maximo alcanzado

# ── Detector de régimen ───────────────────────────────────────────────────────
REGIME_HYSTERESIS_CYCLES = 2    # ciclos consecutivos para confirmar cambio de régimen
REGIME_BREADTH_CACHE_MIN = 30   # minutos entre cálculos de breadth (44 llamadas API)

MODEL_PATH  = "models/random_forest.pkl"
SCALER_PATH = "models/scaler.pkl"
LOG_DIR     = "logs/"
TRADES_LOG  = "logs/trades.csv"

LOG_LEVEL  = "INFO"
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Fuentes de datos adicionales (todas opcionales) ───────
FINNHUB_API_KEY      = os.getenv("FINNHUB_API_KEY", "")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
NEWSAPI_KEY          = os.getenv("NEWSAPI_KEY", "")
FRED_API_KEY         = os.getenv("FRED_API_KEY", "")
POLYGON_API_KEY      = os.getenv("POLYGON_API_KEY", "")