"""
Audit de lenguaje legalmente riesgoso en el código y documentación.

Busca palabras/frases que suenan a "asesoría de inversión" o que prometen
resultados — usarlas en UI pública puede traer riesgo regulatorio (SEC,
FINRA, SFC). Reporta cada match con archivo, línea y la palabra detectada.

Uso:
    python scripts/audit_language.py
    python scripts/audit_language.py --strict       # incluye palabras borderline
    python scripts/audit_language.py --fix-suggest  # propone reemplazos

Salida:
    Exit 0 → sin matches.
    Exit 1 → hay matches (revisar).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Tuple

# ── Términos peligrosos ──────────────────────────────────────

# Nivel ALTO: estos términos son los más riesgosos regulatoriamente.
HIGH_RISK_TERMS = [
    # Inglés
    r"\bguaranteed?\b(?! losses)",
    r"\bwill profit\b",
    r"\bwill (make|earn) (money|returns?)\b",
    r"\brisk[- ]free\b",
    r"\bsure thing\b",
    r"\bno risk\b",
    r"\bcan't lose\b",
    r"\bproven profits?\b",
    # Palabras de advisor/fiduciario
    r"\bfinancial advisor\b",
    r"\binvestment advice\b",
    r"\bfiduciary\b",
    # Español
    r"\bgaranti[sz]ad[oa]s?\b",
    r"\bsin riesgo\b",
    r"\bvas a ganar\b",
    r"\brendimientos? seguros?\b",
    r"\basesoría financiera\b",
    r"\brecomendación de inversión\b",
]

# Nivel MEDIO: requieren revisión pero pueden ser OK con contexto.
MEDIUM_RISK_TERMS = [
    r"\brecommend(ed|ation)?\b",        # "we recommend..." problematic
    r"\badvice\b",
    r"\badvis(e|er|or)\b",
    r"\bshould buy\b",
    r"\bshould sell\b",
    r"\bbest investment\b",
    r"\btop stock\b(?! pick)",
    r"\bhot stock\b",
    # Español
    r"\brecomendamos\b",
    r"\bmejor inversión\b",
    r"\basesoramos\b",
    r"\bdeberías comprar\b",
    r"\bdeberías vender\b",
]

# Reemplazos sugeridos (neutros, defendibles).
REPLACEMENTS = {
    "recommend": "flag as an educational signal",
    "recommendation": "educational signal",
    "advice": "information",
    "guaranteed": "historical",
    "garantizado": "histórico",
    "recomendamos": "señalamos",
    "recomendación": "señal educativa",
    "advisor": "research tool",
    "asesoría": "análisis educativo",
    "asesoramos": "analizamos",
    "mejor inversión": "oportunidad histórica destacada",
    "should buy": "historically bullish pattern",
    "should sell": "historically bearish pattern",
    "deberías comprar": "patrón históricamente alcista",
    "deberías vender": "patrón históricamente bajista",
}

# Extensiones a escanear.
SCAN_EXT = {".py", ".md", ".html", ".txt", ".js", ".jsx", ".ts", ".tsx"}

# Directorios a ignorar.
IGNORE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", "htmlcov", "results", "models", "logs",
    "legal",          # los docs legales contienen estos términos a propósito
}

# Archivos a ignorar individualmente.
IGNORE_FILES = {
    "audit_language.py",          # este mismo script
    "PLAN_PRODUCCION.md",         # plan interno
    "PLAN_VALIDACION_ML.md",      # plan interno
    "REPRODUCIBILIDAD.md",
    "TESTS.md",
    "INTEGRACION_SAFETY.md",
    "README.md",                  # suele tener disclaimer + términos mezclados
}


# ── Dataclass de hallazgo ────────────────────────────────────

@dataclass
class Match:
    path: str
    line_no: int
    line_text: str
    term: str
    level: str


def scan_file(path: str, patterns: List[Tuple[str, str]]) -> List[Match]:
    matches: List[Match] = []
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f, start=1):
                for pattern, level in patterns:
                    m = re.search(pattern, line, re.IGNORECASE)
                    if m:
                        matches.append(Match(
                            path=path, line_no=i,
                            line_text=line.rstrip(),
                            term=m.group(0), level=level,
                        ))
                        break
    except Exception as exc:
        print(f"  [skip] {path}: {exc}", file=sys.stderr)
    return matches


def scan_tree(root: str, patterns: List[Tuple[str, str]]) -> List[Match]:
    all_matches: List[Match] = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Filtrar directorios ignorados in-place
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for fn in filenames:
            if fn in IGNORE_FILES:
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext not in SCAN_EXT:
                continue
            full = os.path.join(dirpath, fn)
            all_matches.extend(scan_file(full, patterns))
    return all_matches


def suggest(term: str) -> str:
    low = term.lower()
    for key, repl in REPLACEMENTS.items():
        if key in low:
            return repl
    return "(no hay sugerencia automática)"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--strict", action="store_true",
                   help="incluir términos de riesgo medio")
    p.add_argument("--fix-suggest", action="store_true",
                   help="proponer reemplazo para cada match")
    p.add_argument("--root", default=".",
                   help="directorio raíz a escanear (default: cwd)")
    args = p.parse_args()

    patterns = [(pat, "HIGH") for pat in HIGH_RISK_TERMS]
    if args.strict:
        patterns += [(pat, "MEDIUM") for pat in MEDIUM_RISK_TERMS]

    root = os.path.abspath(args.root)
    print(f"Escaneando {root}")
    print(f"Nivel: {'HIGH + MEDIUM' if args.strict else 'HIGH only'}")
    print(f"Ignorando dirs: {sorted(IGNORE_DIRS)}")
    print()

    matches = scan_tree(root, patterns)

    if not matches:
        print("✅ Sin matches. Lenguaje OK.")
        sys.exit(0)

    # Agrupar por archivo
    by_file: dict[str, List[Match]] = {}
    for m in matches:
        by_file.setdefault(m.path, []).append(m)

    total_high = sum(1 for m in matches if m.level == "HIGH")
    total_med = sum(1 for m in matches if m.level == "MEDIUM")

    for path, entries in sorted(by_file.items()):
        rel = os.path.relpath(path, root)
        print(f"▸ {rel}")
        for m in entries:
            marker = "🔴" if m.level == "HIGH" else "🟡"
            print(f"    {marker} L{m.line_no:<4} [{m.term!r}]")
            print(f"        {m.line_text[:120]}")
            if args.fix_suggest:
                repl = suggest(m.term)
                print(f"        → sugerencia: {repl}")
        print()

    print("=" * 60)
    print(f"TOTAL: {total_high} HIGH, {total_med} MEDIUM")
    print("=" * 60)
    sys.exit(1 if total_high > 0 else 0)


if __name__ == "__main__":
    main()
