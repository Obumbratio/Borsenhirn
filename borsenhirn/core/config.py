"""
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
