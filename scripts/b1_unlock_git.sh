#!/usr/bin/env bash
# scripts/b1_unlock_git.sh
#
# Detecta y (con confirmación explícita) elimina .git/index.lock huérfano.
# Causa típica: comando git interrumpido por antivirus/PyCharm/cierre brusco.
#
# Uso (desde la raíz del repo):
#     bash scripts/b1_unlock_git.sh
#
# IMPORTANTE: cerrá PyCharm antes de correr esto. PyCharm tiene git
# integrado que puede sostener locks transitorios.
#
# Salidas (exit codes):
#   0  - OK (lock no existía, o se borró y git responde)
#   1  - hay procesos git activos legítimos: detenelos vos
#   2  - usuario respondió distinto a 'yes' al prompt
#   3  - el lock se borró pero git sigue roto
#   4  - no estamos en raíz de repo git

set -euo pipefail

readonly LOCK_PATH=".git/index.lock"
readonly STALE_THRESHOLD_SECONDS=300   # 5 minutos

section() {
    printf '\n%s\n' "============================================================"
    printf '  %s\n'  "$1"
    printf '%s\n'   "============================================================"
}

# ── 0. Estamos en la raíz del repo? ──────────────────────
if [[ ! -d .git ]]; then
    echo "ERROR: no veo .git/. Corré este script desde la raíz del repo."
    echo "  cd /mnt/c/Users/Uriel/PyCharmMiscProject/proyecto_trading && bash scripts/b1_unlock_git.sh"
    exit 4
fi

# ── 1. ¿Hay procesos git corriendo? ──────────────────────
section "[1] Procesos git activos"

# pgrep -af devuelve PID + comando completo. Excluimos pgrep mismo y greps.
git_procs="$(pgrep -af '\bgit\b' 2>/dev/null | grep -vE 'pgrep|grep|b1_unlock_git' || true)"

if [[ -n "${git_procs}" ]]; then
    echo "Encontré procesos git activos en WSL:"
    echo "${git_procs}"
    echo
    echo "ABORTO. Detené esos procesos manualmente (o cerrá la terminal/IDE"
    echo "que los inició) y volvé a correr este script."
    echo "Si estás seguro de que son zombies, podés matarlos con:"
    echo "  echo \"\${PIDS}\" | xargs -r kill"
    exit 1
fi
echo "OK: no hay procesos git activos en WSL."
echo
echo "Recordatorio: si tenés PyCharm abierto en este repo, su integración"
echo "git puede mantener locks transitorios. Si el problema persiste,"
echo "cerrá PyCharm y volvé a correr."

# ── 2. ¿Existe el lock? ──────────────────────────────────
section "[2] Inspección de ${LOCK_PATH}"

if [[ ! -f "${LOCK_PATH}" ]]; then
    echo "No hay ${LOCK_PATH}. No hay nada que desbloquear."
    echo
    section "[3] Verificación final: git status"
    if git status >/dev/null 2>&1; then
        echo "OK: git status responde sin error."
        exit 0
    else
        echo "ATENCIÓN: git status falló aunque no hay lock visible."
        git status 2>&1 | head -20
        exit 3
    fi
fi

# ── 3. ¿Qué tan viejo es? ────────────────────────────────
lock_mtime="$(stat -c %Y "${LOCK_PATH}" 2>/dev/null || stat -f %m "${LOCK_PATH}")"
now_epoch="$(date +%s)"
age_seconds=$(( now_epoch - lock_mtime ))
age_human=""
if (( age_seconds < 60 )); then
    age_human="${age_seconds}s"
elif (( age_seconds < 3600 )); then
    age_human="$(( age_seconds / 60 ))m $(( age_seconds % 60 ))s"
else
    age_human="$(( age_seconds / 3600 ))h $(( (age_seconds % 3600) / 60 ))m"
fi

lock_size="$(stat -c %s "${LOCK_PATH}" 2>/dev/null || stat -f %z "${LOCK_PATH}")"
echo "Lock encontrado:"
echo "  path:  ${LOCK_PATH}"
echo "  size:  ${lock_size} bytes"
echo "  mtime: $(date -d "@${lock_mtime}" 2>/dev/null || date -r "${lock_mtime}")"
echo "  edad:  ${age_human}"

if (( age_seconds < STALE_THRESHOLD_SECONDS )); then
    echo
    echo "AVISO: el lock tiene MENOS de ${STALE_THRESHOLD_SECONDS}s. Puede ser"
    echo "una operación git LEGÍTIMA en curso. Si estás seguro de que no hay"
    echo "git activo (paso [1] confirmó cero procesos), podés borrarlo."
fi

# ── 4. Confirmación explícita ────────────────────────────
section "[3] Confirmación"
echo "Voy a borrar ${LOCK_PATH}."
echo "Esto es seguro SOLO si no hay procesos git activos (ya verificado)."
read -r -p "¿Borrar el lock? (escribí 'yes' para confirmar): " confirm

if [[ "${confirm}" != "yes" ]]; then
    echo "Cancelado. No se borró nada."
    exit 2
fi

# ── 5. Borrar ────────────────────────────────────────────
rm -f "${LOCK_PATH}"
if [[ -f "${LOCK_PATH}" ]]; then
    echo "FAIL: el lock sigue existiendo. Permisos? ¿Filesystem read-only?"
    ls -la "${LOCK_PATH}"
    exit 3
fi
echo "OK: ${LOCK_PATH} borrado."

# ── 6. Verificar que git funciona ───────────────────────
section "[4] Verificación: git status"
if git status >/dev/null 2>&1; then
    echo "OK: git status responde."
    git status --short | head -20
    exit 0
else
    echo "FAIL: git sigue roto después de borrar el lock."
    git status 2>&1 | head -20
    exit 3
fi
