"""
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
    extra_data  = Column(JSON, nullable=True)
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
