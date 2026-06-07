"""
setup_borsenhirn.py — Crea toda la estructura de carpetas y archivos de Börsenhirn.
Corre este script UNA vez desde la raíz de tu proyecto (proyecto_trading/).

Uso:
    python setup_borsenhirn.py
"""

import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))

# ── Estructura de carpetas ────────────────────────────────────
FOLDERS = [
    "borsenhirn",
    "borsenhirn/core",
    "borsenhirn/m1_research",
    "borsenhirn/m2_analyst",
    "borsenhirn/m3_risk",
    "borsenhirn/m4_whale",
    "borsenhirn/m5_assistant",
    "borsenhirn/dashboard",
    "borsenhirn/reports",
    "borsenhirn/api",
    "borsenhirn/tests",
]

# ── Archivos __init__.py vacíos ───────────────────────────────
INIT_FILES = [
    "borsenhirn/__init__.py",
    "borsenhirn/core/__init__.py",
    "borsenhirn/m1_research/__init__.py",
    "borsenhirn/m2_analyst/__init__.py",
    "borsenhirn/m3_risk/__init__.py",
    "borsenhirn/m4_whale/__init__.py",
    "borsenhirn/m5_assistant/__init__.py",
    "borsenhirn/dashboard/__init__.py",
    "borsenhirn/reports/__init__.py",
    "borsenhirn/api/__init__.py",
    "borsenhirn/tests/__init__.py",
]

# ── Contenido de archivos core ────────────────────────────────
FILES = {

"borsenhirn/core/database.py": '''"""
database.py — Conexión central de Börsenhirn a PostgreSQL.
Todas las tablas del proyecto se crean aquí automáticamente.
"""

import os
import logging
from datetime import datetime
from sqlalchemy import (
    create_engine, Column, String, Float, Integer,
    DateTime, Boolean, Text, JSON, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "borsenhirn")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASS = os.getenv("DB_PASS", "borsenhirn2024")

DATABASE_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine       = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base         = declarative_base()


class Trade(Base):
    __tablename__ = "trades"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    timestamp   = Column(DateTime, default=datetime.utcnow, index=True)
    symbol      = Column(String(10), index=True)
    action      = Column(String(10))
    price       = Column(Float)
    qty         = Column(Integer)
    value       = Column(Float)
    pnl         = Column(Float, nullable=True)
    reason      = Column(Text, nullable=True)
    regime      = Column(String(20), nullable=True)
    vix         = Column(Float, nullable=True)
    ml_prob     = Column(Float, nullable=True)
    rsi         = Column(Float, nullable=True)
    ma_trend    = Column(String(20), nullable=True)


class BotState(Base):
    __tablename__ = "bot_state"
    id               = Column(Integer, primary_key=True, autoincrement=True)
    date             = Column(String(10), unique=True, index=True)
    trades_today     = Column(Integer, default=0)
    wins_today       = Column(Integer, default=0)
    losses_today     = Column(Integer, default=0)
    day_start_equity = Column(Float, default=0.0)
    updated_at       = Column(DateTime, default=datetime.utcnow)


class SymbolMemory(Base):
    __tablename__ = "symbol_memory"
    symbol       = Column(String(10), primary_key=True)
    score        = Column(Float, default=0.5)
    total_trades = Column(Integer, default=0)
    wins         = Column(Integer, default=0)
    losses       = Column(Integer, default=0)
    total_pnl    = Column(Float, default=0.0)
    updated_at   = Column(DateTime, default=datetime.utcnow)


class EntryContext(Base):
    __tablename__ = "entry_context"
    symbol        = Column(String(10), primary_key=True)
    entry_price   = Column(Float)
    highest_price = Column(Float, nullable=True)
    rsi           = Column(Float, nullable=True)
    regime        = Column(String(20), nullable=True)
    vix           = Column(Float, nullable=True)
    ma_trend      = Column(String(20), nullable=True)
    ml_prob       = Column(Float, nullable=True)
    saved_at      = Column(DateTime, default=datetime.utcnow)


class RegimeStat(Base):
    __tablename__ = "regime_stats"
    regime     = Column(String(20), primary_key=True)
    wins       = Column(Integer, default=0)
    losses     = Column(Integer, default=0)
    total_pnl  = Column(Float, default=0.0)
    updated_at = Column(DateTime, default=datetime.utcnow)


class DailyReport(Base):
    __tablename__ = "daily_reports"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    date        = Column(String(10), index=True)
    report_type = Column(String(20), default="daily")
    content     = Column(Text)
    metrics     = Column(JSON, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)


class Signal(Base):
    __tablename__ = "signals"
    id          = Column(Integer, primary_key=True, autoincrement=True)
    timestamp   = Column(DateTime, default=datetime.utcnow, index=True)
    symbol      = Column(String(10), index=True)
    source      = Column(String(20))
    signal_type = Column(String(20))
    score       = Column(Float, default=0.5)
    metadata    = Column(JSON, nullable=True)
    consumed    = Column(Boolean, default=False)


def init_db():
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("[DB] Tablas creadas/verificadas OK.")
        return True
    except Exception as e:
        logger.error(f"[DB] Error creando tablas: {e}")
        return False


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("[DB] Conexión a PostgreSQL OK.")
        return True
    except Exception as e:
        logger.error(f"[DB] Error de conexión: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if test_connection():
        init_db()
        print("✅  Tablas creadas. Verifica en pgAdmin → borsenhirn → Schemas → Tables.")
    else:
        print("❌  No se pudo conectar. Verifica que PostgreSQL está corriendo.")
''',

"borsenhirn/core/cache.py": '''"""
cache.py — Conexión central de Börsenhirn a Redis.
Memoria de corto plazo: precios, señales del día, estado en tiempo real.
"""

import os
import json
import logging
from datetime import timedelta
import redis
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB   = int(os.getenv("REDIS_DB", "0"))

try:
    _client = redis.Redis(
        host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB,
        decode_responses=True, socket_connect_timeout=3
    )
    _client.ping()
    logger.info("[CACHE] Conexión a Redis OK.")
except Exception as e:
    logger.warning(f"[CACHE] Redis no disponible: {e}")
    _client = None


def set_value(key: str, value, ttl_seconds: int = 3600) -> bool:
    if not _client:
        return False
    try:
        if isinstance(value, (dict, list)):
            value = json.dumps(value)
        _client.setex(key, timedelta(seconds=ttl_seconds), str(value))
        return True
    except Exception as e:
        logger.error(f"[CACHE] set_value: {e}")
        return False


def get_value(key: str, default=None):
    if not _client:
        return default
    try:
        val = _client.get(key)
        if val is None:
            return default
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    except Exception as e:
        logger.error(f"[CACHE] get_value: {e}")
        return default


def delete_key(key: str) -> bool:
    if not _client:
        return False
    try:
        _client.delete(key)
        return True
    except Exception as e:
        logger.error(f"[CACHE] delete_key: {e}")
        return False


def cache_price(symbol: str, price: float, ttl: int = 60):
    set_value(f"price:{symbol}", price, ttl_seconds=ttl)


def get_cached_price(symbol: str):
    val = get_value(f"price:{symbol}")
    return float(val) if val is not None else None


def cache_signal(symbol: str, source: str, signal: dict, ttl: int = 3600):
    set_value(f"signal:{source}:{symbol}", signal, ttl_seconds=ttl)


def get_cached_signal(symbol: str, source: str):
    return get_value(f"signal:{source}:{symbol}")


def set_bot_status(status: dict, ttl: int = 300):
    set_value("bot:status", status, ttl_seconds=ttl)


def get_bot_status() -> dict:
    return get_value("bot:status", default={})


def is_available() -> bool:
    if not _client:
        return False
    try:
        _client.ping()
        return True
    except Exception:
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if is_available():
        set_value("test:ok", {"borsenhirn": "online"}, ttl_seconds=60)
        print(f"✅  Redis OK. Test: {get_value('test:ok')}")
    else:
        print("❌  Redis no disponible.")
''',

"borsenhirn/core/config.py": '''"""
config.py — Configuración global de Börsenhirn.
"""
import os
from dotenv import load_dotenv
load_dotenv()

# Base de datos
DB_URL = f"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{os.getenv('DB_PASS','borsenhirn2024')}@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','borsenhirn')}"

# Redis
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# API
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Claude API (para M5 Assistant)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Módulos activos
M1_RESEARCH_ENABLED  = os.getenv("M1_ENABLED", "false").lower() == "true"
M3_RISK_ENABLED      = os.getenv("M3_ENABLED", "false").lower() == "true"
M4_WHALE_ENABLED     = os.getenv("M4_ENABLED", "false").lower() == "true"
M5_ASSISTANT_ENABLED = os.getenv("M5_ENABLED", "false").lower() == "true"
''',

"borsenhirn/api/main.py": '''"""
api/main.py — FastAPI wrapper del trading bot.
3 endpoints básicos: status, cycle, signal.
"""
import logging
from datetime import datetime, timezone
from fastapi import FastAPI
from pydantic import BaseModel
from borsenhirn.core.cache import get_bot_status, set_bot_status, is_available
from borsenhirn.core.database import test_connection

logger = logging.getLogger(__name__)
app = FastAPI(title="Börsenhirn API", version="1.0.0")


class ExternalSignal(BaseModel):
    symbol: str
    source: str        # m1_research / m3_risk / m4_whale
    signal_type: str   # bullish / bearish / risk_high / whale_buy
    score: float = 0.5
    metadata: dict = {}


@app.get("/")
def root():
    return {"name": "Börsenhirn", "version": "1.0.0", "status": "online"}


@app.get("/status")
def get_status():
    """Estado actual del bot y la plataforma."""
    return {
        "timestamp":  datetime.now(timezone.utc).isoformat(),
        "postgres":   test_connection(),
        "redis":      is_available(),
        "bot_status": get_bot_status(),
    }


@app.post("/signal")
def receive_signal(signal: ExternalSignal):
    """Recibe señal externa de M1, M3 o M4 y la cachea para el bot."""
    from borsenhirn.core.cache import cache_signal
    cache_signal(signal.symbol, signal.source, signal.dict())
    logger.info(f"[API] Señal recibida: {signal.source} → {signal.symbol} ({signal.signal_type})")
    return {"status": "ok", "message": f"Señal guardada para {signal.symbol}"}


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(timezone.utc).isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("borsenhirn.api.main:app", host="0.0.0.0", port=8000, reload=True)
''',

"borsenhirn/m1_research/__init__.py": "",
"borsenhirn/m2_analyst/__init__.py":  "",
"borsenhirn/m3_risk/__init__.py":     "",
"borsenhirn/m4_whale/__init__.py":    "",
"borsenhirn/m5_assistant/__init__.py":"",
"borsenhirn/dashboard/__init__.py":   "",
"borsenhirn/reports/__init__.py":     "",
"borsenhirn/api/__init__.py":         "",
"borsenhirn/tests/__init__.py":       "",
"borsenhirn/__init__.py":             "",
"borsenhirn/core/__init__.py":        "",
}

# ── ENV additions ─────────────────────────────────────────────
ENV_ADDITIONS = """
# ── Börsenhirn ────────────────────────────────────────────────
DB_HOST=localhost
DB_PORT=5432
DB_NAME=borsenhirn
DB_USER=postgres
DB_PASS=borsenhirn2024
REDIS_HOST=localhost
REDIS_PORT=6379
API_HOST=0.0.0.0
API_PORT=8000
M1_ENABLED=false
M3_ENABLED=false
M4_ENABLED=false
M5_ENABLED=false
"""


def run():
    print("\n" + "="*55)
    print("  Börsenhirn — Setup de estructura del proyecto")
    print("="*55)

    # 1. Crear carpetas
    print("\n📁  Creando carpetas...")
    for folder in FOLDERS:
        path = os.path.join(BASE, folder)
        os.makedirs(path, exist_ok=True)
        print(f"   ✅  {folder}/")

    # 2. Crear archivos
    print("\n📄  Creando archivos...")
    for filepath, content in FILES.items():
        full_path = os.path.join(BASE, filepath)
        if not os.path.exists(full_path):
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"   ✅  {filepath}")
        else:
            print(f"   ⏭️   {filepath} (ya existe, no se sobreescribe)")

    # 3. Actualizar .env
    print("\n⚙️   Actualizando .env...")
    env_path = os.path.join(BASE, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            existing = f.read()
        if "DB_HOST" not in existing:
            with open(env_path, "a", encoding="utf-8") as f:
                f.write(ENV_ADDITIONS)
            print("   ✅  Variables de Börsenhirn agregadas al .env")
        else:
            print("   ⏭️   .env ya tiene las variables de Börsenhirn")
    else:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(ENV_ADDITIONS.strip())
        print("   ✅  .env creado con variables de Börsenhirn")

    # 4. Resultado final
    print("\n" + "="*55)
    print("  ✅  Estructura creada exitosamente")
    print("="*55)
    print("\n  Siguiente paso — verifica la conexión a Postgres:")
    print("  python borsenhirn/core/database.py")
    print("\n  Si ves 'Tablas creadas', estás listo para el Sprint 1.\n")


if __name__ == "__main__":
    run()