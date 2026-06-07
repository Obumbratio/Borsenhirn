#!/usr/bin/env bash
# scripts/b1_test_postgres.sh
#
# Prueba conexión a Postgres usando las credenciales de .env.
# Si DB_HOST=localhost y la conexión falla, prueba automáticamente con
# la IP del Windows host (típicamente 172.25.144.1 desde WSL2).
#
# Pide la password con prompt seguro (sin echo). Usa PGCONNECT_TIMEOUT=5
# para que un host inalcanzable no cuelgue 30+ segundos.
#
# Uso (desde la raíz del repo):
#     bash scripts/b1_test_postgres.sh
#
# Exit codes:
#   0 - conexión OK con algún host
#   1 - falta .env o psql
#   2 - todos los hosts fallaron
#   3 - usuario canceló (Ctrl+C en password)

set -uo pipefail

readonly TIMEOUT_SECONDS=5

section() {
    printf '\n%s\n' "============================================================"
    printf '  %s\n'  "$1"
    printf '%s\n'   "============================================================"
}

# ── 0. Pre-requisitos ────────────────────────────────────
if ! command -v psql >/dev/null 2>&1; then
    echo "ERROR: psql no está en PATH."
    echo "  Instalá con: sudo apt install postgresql-client-16"
    exit 1
fi

if [[ ! -f .env ]]; then
    echo "ERROR: no encontré .env en la raíz del repo."
    exit 1
fi

# ── 1. Leer credenciales de .env ─────────────────────────
read_env() {
    local key="$1"
    local default="${2:-}"
    local val
    val="$(grep -E "^${key}=" .env | head -1 | cut -d= -f2- | tr -d '\r' | tr -d '"' || true)"
    if [[ -z "${val}" ]]; then
        echo "${default}"
    else
        echo "${val}"
    fi
}

DB_HOST="$(read_env DB_HOST localhost)"
DB_PORT="$(read_env DB_PORT 5432)"
DB_NAME="$(read_env DB_NAME borsenhirn)"
DB_USER="$(read_env DB_USER postgres)"

section "[1] Credenciales detectadas en .env"
echo "  DB_HOST: ${DB_HOST}"
echo "  DB_PORT: ${DB_PORT}"
echo "  DB_NAME: ${DB_NAME}"
echo "  DB_USER: ${DB_USER}"
echo "  DB_PASSWORD: <oculta — te la pido en el prompt>"

# ── 2. Construir lista de hosts a probar ─────────────────
declare -a HOSTS_TO_TRY=()
HOSTS_TO_TRY+=("${DB_HOST}")

# Si DB_HOST es localhost y estamos en WSL2, agregar IP de Windows host
WIN_HOST=""
if [[ "${DB_HOST}" == "localhost" || "${DB_HOST}" == "127.0.0.1" ]]; then
    if command -v ip >/dev/null 2>&1; then
        WIN_HOST="$(ip route show default 2>/dev/null | awk '{print $3}' | head -1)"
        if [[ -n "${WIN_HOST}" && "${WIN_HOST}" != "${DB_HOST}" ]]; then
            HOSTS_TO_TRY+=("${WIN_HOST}")
        fi
    fi
    # Fallback hardcoded WSL2
    if [[ -n "${WIN_HOST}" ]] && [[ "${WIN_HOST}" != "172.25.144.1" ]]; then
        HOSTS_TO_TRY+=("172.25.144.1")
    fi
fi

section "[2] Hosts a probar (en orden)"
for h in "${HOSTS_TO_TRY[@]}"; do
    echo "  - ${h}"
done

# ── 3. Pedir password una vez ────────────────────────────
section "[3] Password de Postgres"
echo "Ingresá la password del usuario '${DB_USER}'."
echo "(no se va a mostrar en pantalla mientras escribís)"
echo

if ! read -r -s -p "Password: " DB_PASSWORD; then
    echo
    echo "Cancelado."
    exit 3
fi
echo
if [[ -z "${DB_PASSWORD}" ]]; then
    echo "Password vacía. Probemos sin ella (puede que tu pg_hba.conf use 'trust')."
fi

export PGPASSWORD="${DB_PASSWORD}"
export PGCONNECT_TIMEOUT="${TIMEOUT_SECONDS}"

# ── 4. Probar cada host ──────────────────────────────────
section "[4] Pruebas de conexión"

successful_host=""
for host in "${HOSTS_TO_TRY[@]}"; do
    printf '  Probando %s ... ' "${host}"
    if output="$(psql -h "${host}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -tAc "SELECT version();" 2>&1)"; then
        echo "OK"
        echo "    ${output}"
        successful_host="${host}"
        break
    else
        echo "FAIL"
        # Indentar el error
        echo "${output}" | sed 's/^/    /'
        echo
    fi
done

unset PGPASSWORD

# ── 5. Resultado ─────────────────────────────────────────
section "[5] Resultado"
if [[ -n "${successful_host}" ]]; then
    echo "OK: conexión exitosa a host '${successful_host}'."
    echo
    if [[ "${successful_host}" != "${DB_HOST}" ]]; then
        echo "AVISO: tu .env tiene DB_HOST=${DB_HOST} pero el que funcionó es"
        echo "       '${successful_host}'. Para Bloque 0 vamos a usar:"
        echo "         DB_HOST=${successful_host}"
        echo "       Considerá actualizar tu .env (o dejarlo como está si"
        echo "       el bot single-tenant ya funciona — Postgres puede"
        echo "       estar accesible por ambas rutas)."
    else
        echo "El host del .env funcionó tal cual. Sin cambios necesarios."
    fi
    echo
    echo "Datos para el Bloque 0:"
    echo "  HOST_BLOQUE_0=${successful_host}"
    echo "  PORT=${DB_PORT}"
    echo "  USER=${DB_USER}"
    echo "  DB=${DB_NAME}"
    exit 0
else
    echo "FAIL: ningún host respondió."
    echo
    echo "Diagnóstico sugerido:"
    echo "  1. ¿Postgres está corriendo en Windows?"
    echo "     Desde PowerShell (admin):"
    echo "       Get-Service postgresql*"
    echo "     Si está 'Stopped': Start-Service postgresql-x64-18"
    echo
    echo "  2. ¿Postgres escucha en TCP, no solo socket Unix?"
    echo "     En Windows, abrir:"
    echo "       C:\\Program Files\\PostgreSQL\\18\\data\\postgresql.conf"
    echo "     Verificar:  listen_addresses = '*'  (o = 'localhost,172.25.144.1')"
    echo "     Si lo cambias, reiniciar el servicio."
    echo
    echo "  3. ¿pg_hba.conf permite conexión desde la subnet de WSL?"
    echo "     En:  C:\\Program Files\\PostgreSQL\\18\\data\\pg_hba.conf"
    echo "     Agregar línea (para WSL2):"
    echo "       host  all  all  172.16.0.0/12  scram-sha-256"
    echo "     Reiniciar servicio."
    echo
    echo "  4. ¿Firewall de Windows bloqueando puerto 5432?"
    echo "     Desde PowerShell (admin):"
    echo "       New-NetFirewallRule -DisplayName 'PostgreSQL WSL' \\"
    echo "         -Direction Inbound -Protocol TCP -LocalPort 5432 -Action Allow"
    echo
    echo "  5. ¿La password es correcta?"
    echo "     Probá con psql desde PowerShell directamente para descartar."
    exit 2
fi
