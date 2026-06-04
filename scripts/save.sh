#!/usr/bin/env bash
# Ritual de cierre: commitear lo que haya y subir. No truena si no hay cambios.
set -euo pipefail

MSG="${1:-wip: avance}"

git add -A

if git diff --cached --quiet; then
  echo "ℹ  Nada que commitear. Working tree limpio."
  exit 0
fi

git commit -m "$MSG"

if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
  git push
  echo "✓ Subido: $MSG"
else
  echo "⚠  Commit hecho, pero esta rama no tiene upstream."
  echo "   Súbela con: git push -u origin \$(git branch --show-current)"
fi
