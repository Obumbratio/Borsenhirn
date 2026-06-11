#!/usr/bin/env bash
# scripts/run_bot_prod.sh
# Corre el bot contra PROD LOCAL (DB `borsenhirn`), single-user, PAPER.
#
# Local-first: prod vive en el MISMO Postgres local que dev, en la base
# `borsenhirn` (esquema clonado de `borsenhirn_dev`, limpio). El bot apunta ahí
# vía `.env.prod` (DB_NAME=borsenhirn). Como `config.load_dotenv()` NO pisa
# variables ya exportadas, sourcear `.env.prod` ANTES de python hace que prod
# gane sobre el `.env` (dev). Sin .env.prod -> el default sigue siendo dev (seguro).
#
# Uso:
#   bash scripts/run_bot_prod.sh
#   nohup bash scripts/run_bot_prod.sh >/dev/null 2>&1 &   # background
#   pkill -f "python main.py"                              # parar
set -uo pipefail
cd "$(dirname "$0")/.."

[ -f .env.prod ] || { echo "ERROR: falta .env.prod (DB_NAME=borsenhirn). Es local y NO va a git."; exit 2; }
set -a; # shellcheck disable=SC1090
source .env.prod; set +a

# Guard: asegurarse de que apunta a prod, no a dev por accidente.
[ "${DB_NAME:-}" = "borsenhirn" ] || { echo "ERROR: .env.prod no apunta a borsenhirn (DB_NAME=${DB_NAME:-vacío})."; exit 2; }

mkdir -p logs
LOG="logs/bot_prod_$(date +%Y%m%d_%H%M%S).log"
echo "================================================================"
echo "  Börsenhirn — bot (PROD LOCAL: borsenhirn, PAPER) | log: $LOG"
echo "  Self-gates por horario de mercado. Parar: Ctrl-C o pkill -f 'python main.py'"
echo "================================================================"
exec venv/bin/python main.py 2>&1 | tee "$LOG"
