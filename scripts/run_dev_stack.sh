#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# run_dev_stack.sh — levanta TODO el stack de dev de un tirón.
#   Postgres + (Redis si está instalado) + API backend (:8000) + Front Next (:3000)
#
# Pensado para WSL2 (browser en Windows):
#   - La API se bindea a 0.0.0.0 (NO 127.0.0.1) para que el browser de Windows la
#     alcance vía el reenvío de localhost de WSL. Atarla a 127.0.0.1 = "Failed to fetch".
#   - La API ya trae CORSMiddleware (ver borsenhirn/api/main.py) para el fetch
#     client-side cross-origin :3000 -> :8000.
#   - Sourcea .env → carga BORSENHIRN_MASTER_KEY (vault), Clerk y CORS_ALLOW_ORIGINS.
#
# Uso:   bash scripts/run_dev_stack.sh
# Frenar: pkill -f 'uvicorn borsenhirn.api.main' ; pkill -f 'next dev'
# (Postgres/Redis arrancan con sudo service — puede pedir tu contraseña.)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

up() { curl -sf -o /dev/null "$1"; }

echo "▶ 1/4 Postgres…"
if pg_isready -q 2>/dev/null; then
  echo "  ✓ ya está arriba"
else
  sudo service postgresql start && echo "  ✓ iniciado"
fi

echo "▶ 2/4 Redis (opcional)…"
if command -v redis-server >/dev/null 2>&1; then
  if redis-cli ping >/dev/null 2>&1; then
    echo "  ✓ ya está arriba"
  else
    sudo service redis-server start 2>/dev/null || redis-server --daemonize yes
    echo "  ✓ iniciado"
  fi
else
  echo "  ⚠ redis-server NO instalado — se omite (broker/tarjetas no lo necesitan;"
  echo "    solo /status y señales externas lo usan)."
fi

echo "▶ 3/4 API backend (:8000, host 0.0.0.0)…"
if up http://127.0.0.1:8000/health; then
  echo "  ✓ ya responde"
else
  set -a; . ./.env 2>/dev/null; set +a
  nohup venv/bin/python -m uvicorn borsenhirn.api.main:app \
      --host 0.0.0.0 --port 8000 --log-level info > /tmp/borsenhirn_api.log 2>&1 &
  echo "  … lanzada (log: /tmp/borsenhirn_api.log)"
fi

echo "▶ 4/4 Frontend Next (:3000)…"
if up http://127.0.0.1:3000/; then
  echo "  ✓ ya responde"
else
  export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" >/dev/null 2>&1
  ( cd frontend && nohup npm run dev > /tmp/borsenhirn_front.log 2>&1 & )
  echo "  … lanzado (log: /tmp/borsenhirn_front.log)"
fi

echo "⏳ esperando healthchecks…"
for _ in $(seq 1 60); do up http://127.0.0.1:8000/health && break; sleep 1; done
for _ in $(seq 1 90); do up http://127.0.0.1:3000/        && break; sleep 1; done

echo
echo "================ ESTADO ================"
printf "  Postgres   : %s\n" "$(pg_isready -q 2>/dev/null && echo OK || echo CAÍDO)"
printf "  API  :8000 : %s\n" "$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health 2>/dev/null || echo CAÍDA)"
printf "  Front:3000 : %s\n" "$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/ 2>/dev/null || echo CAÍDO)"
echo "========================================"
echo "  Browser → http://localhost:3000/dashboard"
echo "  Frenar  → pkill -f 'uvicorn borsenhirn.api.main' ; pkill -f 'next dev'"
