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

# ── Alertas (Discord + Email + Dashboard) ─────────────────────────
# IMPORTANTE: DISCORD_WEBHOOK_URL es una credencial. Pégala SOLO en .env.
# Si alguna vez la compartiste, rotá el webhook desde Discord.
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

SMTP_HOST        = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT        = int(os.getenv("SMTP_PORT", 587))
SMTP_USER        = os.getenv("SMTP_USER", "")
SMTP_PASSWORD    = os.getenv("SMTP_PASSWORD", "")
SMTP_USE_TLS     = os.getenv("SMTP_USE_TLS", "true").lower() == "true"
ALERT_EMAIL_TO   = [e.strip() for e in os.getenv("ALERT_EMAIL_TO", "").split(",") if e.strip()]

ALERT_DEDUPE_WINDOW_SEC = int(os.getenv("ALERT_DEDUPE_WINDOW_SEC", 300))

# ── Kill switch ───────────────────────────────────────────────────
KS_MAX_DAILY_LOSS_PCT       = float(os.getenv("KS_MAX_DAILY_LOSS_PCT",
                                              MAX_DAILY_LOSS_PCT))
KS_MAX_DRAWDOWN_7D_PCT      = float(os.getenv("KS_MAX_DRAWDOWN_7D_PCT", 0.15))
KS_MAX_CONSECUTIVE_FAILURES = int(os.getenv("KS_MAX_CONSECUTIVE_FAILURES", 5))

# ── Sanity checks ─────────────────────────────────────────────────
SANITY_MIN_PRICE          = float(os.getenv("SANITY_MIN_PRICE", 0.5))
SANITY_MAX_PRICE          = float(os.getenv("SANITY_MAX_PRICE", 100_000))
SANITY_MAX_QTY_PER_ORDER  = int(os.getenv("SANITY_MAX_QTY_PER_ORDER", 10_000))
SANITY_WASH_GAP_SEC       = int(os.getenv("SANITY_WASH_GAP_SEC", 300))

# ── Secrets vault (Gap 3 + B2) ────────────────────────────────────
# Master key Fernet para encriptar credenciales de usuarios SaaS.
# Generar con: python -c "from borsenhirn.security import generate_master_key; print(generate_master_key())"
# NUNCA commitear el valor real.
# B2: se resuelve vía secret provider (archivo montado {VAR}_FILE -> comando
# {VAR}_CMD del secrets manager -> env var {VAR} en dev). Así la master key
# sale de .env en producción. Fallback defensivo a os.getenv si el módulo
# de seguridad no estuviera disponible.
try:
    from borsenhirn.security.secret_provider import resolve_secret as _resolve_secret
    BORSENHIRN_MASTER_KEY = _resolve_secret("BORSENHIRN_MASTER_KEY", default="") or ""
except Exception:  # pragma: no cover - fallback ante import roto
    BORSENHIRN_MASTER_KEY = os.getenv("BORSENHIRN_MASTER_KEY", "")
# Para rotación: temporalmente ambos están seteados.
BORSENHIRN_NEW_MASTER_KEY = os.getenv("BORSENHIRN_NEW_MASTER_KEY", "")

# ── Fuentes de datos adicionales (todas opcionales) ───────
FINNHUB_API_KEY      = os.getenv("FINNHUB_API_KEY", "")
ALPHAVANTAGE_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY", "")
NEWSAPI_KEY          = os.getenv("NEWSAPI_KEY", "")
FRED_API_KEY         = os.getenv("FRED_API_KEY", "")
POLYGON_API_KEY      = os.getenv("POLYGON_API_KEY", "")

DB_HOST     = os.getenv("DB_HOST", "localhost")
DB_PORT     = int(os.getenv("DB_PORT", 5432))
DB_NAME     = os.getenv("DB_NAME", "borsenhirn")

# Admin / migration credentials (Postgres superuser).
# Used ONLY by scripts/ migrations and TenantManager (admin lifecycle).
# RUNTIME code must NOT use these — it routes through APP_DB_USER below.
DB_USER     = os.getenv("DB_USER", "postgres")
# Acepta DB_PASS como alias de DB_PASSWORD: varios .env (incl. .env.dev) y
# borsenhirn/core/* usan DB_PASS. Sin esto, el pool admin y los scripts admin
# (ks_admin, rotate_master_key, check_rls_coverage, etc.) tomaban el fallback.
DB_PASSWORD = os.getenv("DB_PASSWORD") or os.getenv("DB_PASS") or "uriel"

# Application credentials (B1 Sprint - Block 5).
# Role borsenhirn_app is NOSUPERUSER + NOBYPASSRLS + LOGIN.
# RLS policies in DB enforce per-tenant isolation against this role.
# Defaults fall back to admin credentials so single-user dev keeps working
# without setup; production SaaS deploys MUST set both env vars.
APP_DB_USER     = os.getenv("APP_DB_USER", DB_USER)
APP_DB_PASSWORD = os.getenv("APP_DB_PASSWORD", DB_PASSWORD)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")