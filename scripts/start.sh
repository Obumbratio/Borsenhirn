#!/usr/bin/env bash
# Ritual de inicio: traer cambios y mostrar el estado del sprint.
set -euo pipefail

# Solo hace pull si hay un upstream configurado para la rama actual.
if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  git pull --rebase
else
  echo "ℹ  Sin upstream para esta rama; me salto el pull."
fi

echo "✓ Al día:"
head -15 docs/ESTADO.md 2>/dev/null || true
