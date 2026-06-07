#!/usr/bin/env bash
# scripts/b1_env_check.sh
# Versión bash del check de entorno (para correr en WSL).
# Corré:
#   bash scripts/b1_env_check.sh
# Pegale el output entero a Claude.

set +e

section() {
    echo
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
}

# ── 1. psql ──────────────────────────────────────────────
section "[1] psql client (WSL)"
if command -v psql >/dev/null 2>&1; then
    psql --version
else
    echo "psql NOT in PATH. Instalar con: sudo apt-get update && sudo apt-get install -y postgresql-client-16"
fi

# ── 2. Postgres en WSL ───────────────────────────────────
section "[2] PostgreSQL service en WSL"
if command -v service >/dev/null 2>&1; then
    service postgresql status 2>&1 | head -5
else
    echo "(service no disponible — Postgres puede estar en Windows)"
fi

# ── 3. Conexión ──────────────────────────────────────────
section "[3] Conexión a DB borsenhirn"
if [ -f .env ]; then
    DB_HOST=$(grep -E "^DB_HOST=" .env | cut -d= -f2- | tr -d '\r')
    DB_PORT=$(grep -E "^DB_PORT=" .env | cut -d= -f2- | tr -d '\r')
    DB_NAME=$(grep -E "^DB_NAME=" .env | cut -d= -f2- | tr -d '\r')
    DB_USER=$(grep -E "^DB_USER=" .env | cut -d= -f2- | tr -d '\r')
    : "${DB_HOST:=localhost}"
    : "${DB_PORT:=5432}"
    : "${DB_NAME:=borsenhirn}"
    : "${DB_USER:=postgres}"
    echo "From .env: host=$DB_HOST port=$DB_PORT db=$DB_NAME user=$DB_USER"
    echo
    echo "Si Postgres está en Windows desde WSL2, host típicamente es:"
    if command -v ip >/dev/null 2>&1; then
        WIN_HOST=$(ip route show default | awk '{print $3}' | head -1)
        echo "  Windows host detectado: $WIN_HOST"
    fi
    echo
    echo "Corré este comando y pegá el output:"
    echo "  psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c \"SELECT version();\""
else
    echo "FAIL: no encontré .env en la raíz."
fi

# ── 4. Procesos Python ───────────────────────────────────
section "[4] Procesos Python corriendo"
ps aux | grep -E "python.*main\.py|python.*bot|streamlit" | grep -v grep || echo "Sin procesos relevantes."

# ── 5. Procesos Windows ──────────────────────────────────
section "[5] Procesos Python en Windows (visto desde WSL)"
if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -Command "Get-Process python,python3,pythonw,streamlit -ErrorAction SilentlyContinue | Format-Table Id,ProcessName,WorkingSet -AutoSize" 2>/dev/null
else
    echo "(powershell.exe no accesible desde esta WSL)"
fi

# ── 6. Carpeta backups/ ──────────────────────────────────
section "[6] Carpeta backups/"
if [ -d backups ]; then
    echo "OK: backups/ existe."
    ls -la backups/ 2>/dev/null
else
    echo "FAIL: backups/ no existe. Creala con: mkdir backups"
fi

# ── 7. Git ───────────────────────────────────────────────
section "[7] git status"
git rev-parse --abbrev-ref HEAD 2>/dev/null
git status --short 2>/dev/null

# ── 8. Resumen ───────────────────────────────────────────
section "[8] RESUMEN PARA CLAUDE"
echo "Pegá este output a Claude. Si algo falla:"
echo "  - psql no en PATH → sudo apt install postgresql-client-16"
echo "  - servicio detenido → sudo service postgresql start"
echo "  - conexión rechazada → revisar pg_hba.conf y listen_addresses"
echo "  - procesos corriendo → detenelos manualmente antes de seguir"
