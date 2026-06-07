#!/usr/bin/env bash
# scripts/b1_clean_git.sh
#
# Limpieza idempotente del estado del repo antes del Bloque 0 del Sprint B1:
#   1. Refuerza .gitignore con líneas que faltan (idempotente).
#   2. Destrackea archivos que ya están en git pero no deberían
#      (.idea/, .claude/settings.local.json, .coverage, pytest-cache-files-*).
#   3. Crea rama backup-pre-b1-YYYYMMDD desde el estado actual (sin checkout).
#   4. Muestra git status final.
#
# NO HACE COMMIT. Vos revisás `git status` y commiteás manualmente.
#
# Idempotente: correrlo dos veces no rompe nada.
#
# Pre-requisito: scripts/b1_unlock_git.sh ya corrió OK (no hay lock huérfano).
#
# Uso (desde la raíz del repo):
#     bash scripts/b1_clean_git.sh
#
# Exit codes:
#   0 - OK
#   1 - no estamos en raíz de repo git
#   2 - hay un .git/index.lock (correr b1_unlock_git.sh primero)
#   3 - git no responde por otro motivo

set -euo pipefail

readonly GITIGNORE=".gitignore"
readonly BACKUP_BRANCH="backup-pre-b1-$(date +%Y%m%d)"

# Líneas que QUEREMOS asegurar en .gitignore.
# Cada línea aparece una sola vez (chequeamos antes de append).
readonly LINES_TO_ENSURE=(
    ".claude/settings.local.json"
    ".coverage"
    ".coverage.*"
    "htmlcov/"
    "pytest-cache-files-*/"
    ".pytest_cache/"
    ".streamlit/secrets.toml"
)

# Paths a destrackear (si están trackeados).
# Cada uno: <flag> <path>  donde flag es "" para file o "-r" para dir.
readonly UNTRACK_TARGETS=(
    "-r:.idea/"
    ":.claude/settings.local.json"
    ":.coverage"
    "-r:pytest-cache-files-ni9xj5_5/"
)

section() {
    printf '\n%s\n' "============================================================"
    printf '  %s\n'  "$1"
    printf '%s\n'   "============================================================"
}

# ── 0. Sanidad ───────────────────────────────────────────
if [[ ! -d .git ]]; then
    echo "ERROR: corré desde la raíz del repo."
    exit 1
fi

if [[ -f .git/index.lock ]]; then
    echo "ERROR: .git/index.lock existe. Corré primero:"
    echo "  bash scripts/b1_unlock_git.sh"
    exit 2
fi

if ! git status >/dev/null 2>&1; then
    echo "ERROR: git status falla. Diagnosticá antes de seguir."
    git status 2>&1 | head -5
    exit 3
fi

# ── 1. Reforzar .gitignore ───────────────────────────────
section "[1] Reforzar .gitignore (idempotente)"

if [[ ! -f "${GITIGNORE}" ]]; then
    echo "ERROR: .gitignore no existe en la raíz."
    exit 1
fi

added=0
skipped=0
{
    echo ""
    echo "# ── Sprint B1 cleanup ────────────────────────────────────"
} > /tmp/b1_gitignore_addendum.tmp

for line in "${LINES_TO_ENSURE[@]}"; do
    # Match exacto de la línea (no substring) para evitar duplicados
    if grep -Fxq "${line}" "${GITIGNORE}"; then
        echo "  skip (ya está): ${line}"
        skipped=$(( skipped + 1 ))
    else
        echo "  add:           ${line}"
        echo "${line}" >> /tmp/b1_gitignore_addendum.tmp
        added=$(( added + 1 ))
    fi
done

if (( added > 0 )); then
    cat /tmp/b1_gitignore_addendum.tmp >> "${GITIGNORE}"
    echo
    echo "Agregadas ${added} líneas nuevas a .gitignore."
else
    echo
    echo "Nada que agregar — .gitignore ya tiene todo."
fi
rm -f /tmp/b1_gitignore_addendum.tmp

# ── 2. Destrackear archivos ──────────────────────────────
section "[2] Destrackear archivos que no deberían estar en git"

for entry in "${UNTRACK_TARGETS[@]}"; do
    flag="${entry%%:*}"
    path="${entry#*:}"

    # ¿Está trackeado? `git ls-files --error-unmatch` falla si no está.
    if ! git ls-files --error-unmatch "${path}" >/dev/null 2>&1; then
        # Para dirs probamos con / al final
        if [[ "${flag}" == "-r" ]] && ! git ls-files --error-unmatch "${path%/}" >/dev/null 2>&1; then
            # Última prueba: ls-files con prefix
            tracked_count="$(git ls-files "${path}" 2>/dev/null | wc -l)"
            if [[ "${tracked_count}" -eq 0 ]]; then
                echo "  skip (no trackeado): ${path}"
                continue
            fi
        else
            echo "  skip (no trackeado): ${path}"
            continue
        fi
    fi

    echo "  destrackear: ${path}"
    if [[ "${flag}" == "-r" ]]; then
        if git rm -r --cached "${path}" 2>&1 | sed 's/^/      /'; then
            echo "      -> OK"
        else
            echo "      -> FAIL (revisar manual)"
        fi
    else
        if git rm --cached "${path}" 2>&1 | sed 's/^/      /'; then
            echo "      -> OK"
        else
            echo "      -> FAIL (revisar manual)"
        fi
    fi
done

# ── 3. Crear rama de respaldo (sin checkout) ─────────────
section "[3] Rama de respaldo: ${BACKUP_BRANCH}"

if git rev-parse --verify "${BACKUP_BRANCH}" >/dev/null 2>&1; then
    echo "Ya existe la rama ${BACKUP_BRANCH}. La dejo como está (idempotente)."
else
    if git branch "${BACKUP_BRANCH}" 2>&1 | sed 's/^/  /'; then
        echo "OK: rama ${BACKUP_BRANCH} creada (sin checkout — seguís en la actual)."
    else
        echo "FAIL al crear rama ${BACKUP_BRANCH}."
    fi
fi

# ── 4. git status final ──────────────────────────────────
section "[4] git status final"
echo "Branch actual: $(git rev-parse --abbrev-ref HEAD)"
echo
git status --short

echo
section "[5] Próximos pasos"
echo "1. Revisá el git status de arriba — verificá que NO hay nada extraño."
echo "2. Si te conforma, commiteá MANUALMENTE:"
echo "     git add .gitignore"
echo "     git commit -m \"chore: refuerzo gitignore + destrack archivos basura\""
echo "3. Después corré: bash scripts/b1_test_postgres.sh"
echo
echo "NO se commiteó nada automáticamente. Tu llamada."
