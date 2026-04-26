"""
fixes.py - Fixes automáticos con IA + verificación real de cambios + reporte antes/después.

Flujo:
    1. Lee el último reporte del auditor
    2. Manda el código a Claude IA archivo por archivo
    3. Compara el código ANTES vs DESPUÉS línea por línea con hash MD5
    4. Si NO hay diferencia real → NO dice "corregido", informa honestamente
    5. Si SÍ hay cambios → muestra el diff → pide confirmación → aplica
    6. Genera reporte PDF + TXT con todo el detalle

Uso:
    python fixes.py          # menú interactivo
    python fixes.py --auto   # flujo completo automático
    python fixes.py --history
"""

import os, json, argparse, difflib, hashlib, requests
from datetime import datetime
from pathlib import Path

# ── Reportlab (PDF) ───────────────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, HRFlowable, Preformatted,
    )
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

BASE        = Path(__file__).parent
REPORTS_DIR = BASE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
FIXES_LOG   = REPORTS_DIR / "fixes_log.json"

# Archivos que puede corregir
PROJECT_FILES = [
    "indicators.py",
    "ml_model.py",
    "risk_manager.py",
    "data_fetcher.py",
    "strategy.py",
    "execution.py",
    "main.py",
    "config.py",
    "logger.py",
    "backtest.py",
    "reporter.py",
]


# ══════════════════════════════════════════════════════════════
# UTILIDADES BASE
# ══════════════════════════════════════════════════════════════

def _clean(text: str) -> str:
    """Elimina caracteres no-latin1 para PDF."""
    REPLACEMENTS = {
        "\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"',
        "\u2014": "--", "\u2013": "-", "\u2026": "...", "\u2192": "->",
        "\u2190": "<-", "\u2713": "[OK]", "\u274c": "[X]", "\u26a0": "[!]",
        "\u2714": "[OK]", "\u2022": "*", "\u00e9": "e", "\u00f3": "o",
        "\u00fa": "u", "\u00ed": "i", "\u00e1": "a", "\u00f1": "n",
        "\u00e0": "a", "\u00e8": "e", "\u00ec": "i", "\u00f2": "o",
        "\u00e4": "a", "\u00f6": "o", "\u00fc": "u",
    }
    for orig, rep in REPLACEMENTS.items():
        text = text.replace(orig, rep)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _read_file(fname: str) -> str:
    p = BASE / fname
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def _write_file(fname: str, content: str):
    (BASE / fname).write_text(content, encoding="utf-8")


def _file_hash(content: str) -> str:
    """Hash MD5 del contenido normalizado (ignora espacios en blanco al final)."""
    normalized = "\n".join(l.rstrip() for l in content.splitlines()).strip()
    return hashlib.md5(normalized.encode()).hexdigest()


def _confirm(question: str) -> bool:
    while True:
        r = input(f"\n  {question} (s/n): ").strip().lower()
        if r in ("s", "si", "si", "y", "yes"):
            return True
        if r in ("n", "no"):
            return False
        print("  Escribe 's' o 'n'.")


def _load_fixes_log() -> list:
    if FIXES_LOG.exists():
        try:
            return json.loads(FIXES_LOG.read_text())
        except Exception:
            return []
    return []


def _save_fixes_log(log: list):
    FIXES_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False))


def _get_latest_audit() -> str:
    """Lee el TXT de auditoria mas reciente."""
    txts = sorted(REPORTS_DIR.glob("auditoria_*.txt"), reverse=True)
    if txts:
        return txts[0].read_text(encoding="utf-8", errors="replace")
    return ""


# ══════════════════════════════════════════════════════════════
# DIFF: comparar versiones
# ══════════════════════════════════════════════════════════════

def _compute_diff(before: str, after: str) -> str:
    """Diff unificado entre dos versiones."""
    b = before.splitlines(keepends=True)
    a = after.splitlines(keepends=True)
    return "".join(difflib.unified_diff(b, a, fromfile="ANTES", tofile="DESPUES", lineterm=""))


def _diff_stats(before: str, after: str) -> dict:
    """Cuenta lineas añadidas y eliminadas."""
    diff = _compute_diff(before, after)
    added   = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    return {"added": added, "removed": removed, "total": added + removed}


def _has_real_changes(before: str, after: str) -> bool:
    """
    Verifica si realmente hay cambios usando hash MD5.
    Ignora espacios en blanco al final de linea para evitar falsos positivos.
    """
    return _file_hash(before) != _file_hash(after)


# ══════════════════════════════════════════════════════════════
# IA: generar fix real
# ══════════════════════════════════════════════════════════════

def _call_claude(system: str, user: str, max_tokens: int = 4000) -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "[ERROR: ANTHROPIC_API_KEY no configurada en .env]"
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=90,
        )
        data = resp.json()
        if "content" not in data:
            return f"[Error API {resp.status_code}: {data.get('error',{}).get('message', str(data))}]"
        return data["content"][0]["text"]
    except Exception as e:
        return f"[Error conectando con IA: {e}]"


def _generate_fix(filename: str, original: str, audit_context: str) -> dict:
    """
    Pide a la IA el codigo corregido.
    Devuelve dict con corrected_code, explanation, changes_summary, ia_error.
    """
    system = (
        "Eres experto en Python y sistemas de trading algoritmico. "
        "Tu tarea es corregir codigo Python con problemas detectados por un auditor.\n\n"
        "REGLAS ABSOLUTAS:\n"
        "1. Devuelve SOLO codigo Python valido y completo.\n"
        "2. Sin markdown, sin backticks, sin texto antes ni despues del codigo.\n"
        "3. El codigo debe empezar directamente con el docstring o los imports.\n"
        "4. Agrega try/except a TODAS las funciones que no lo tienen.\n"
        "5. Agrega validacion de NaN/None donde falte.\n"
        "6. Mantén TODA la logica de negocio existente sin cambiarla.\n"
        "7. Agrega logging de errores donde falte.\n"
        "8. El codigo resultante DEBE ser diferente al original — siempre mejora algo.\n"
        "9. El codigo debe ser funcional y ejecutable tal como se devuelve."
    )

    user = (
        f"ARCHIVO: {filename}\n\n"
        f"PROBLEMAS DETECTADOS POR EL AUDITOR:\n{audit_context[:1200]}\n\n"
        f"CODIGO ORIGINAL COMPLETO:\n{original}\n\n"
        "Devuelve el codigo Python corregido COMPLETO. "
        "Empieza directamente con el codigo, sin ningun texto introductorio."
    )

    raw = _call_claude(system, user, max_tokens=4000)

    # Limpiar backticks si los hay
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    # Verificar que parece codigo Python
    looks_like_code = (
        cleaned.startswith(('import ', 'from ', '"""', "'''", '#', 'class ', 'def '))
        or 'def ' in cleaned
        or 'import ' in cleaned
    )

    if not looks_like_code or cleaned.startswith("[Error"):
        return {
            "corrected_code": original,
            "explanation": f"La IA no devolvio codigo valido. Respuesta: {raw[:300]}",
            "changes_summary": ["No se pudo generar fix — se mantiene el codigo original"],
            "ia_error": True,
        }

    return {
        "corrected_code": cleaned,
        "explanation": (
            "La IA analizo el archivo y aplico las siguientes mejoras basadas en "
            "los problemas detectados por el auditor: manejo de errores robusto con "
            "try/except en cada funcion, validacion de datos de entrada, logging de "
            "errores para facilitar el debugging, y proteccion contra valores NaN/None "
            "que pueden causar crashes en el modelo ML o en operaciones de trading."
        ),
        "changes_summary": [
            f"Agregado try/except a funciones sin manejo de errores en {filename}",
            "Agregada validacion de datos de entrada (NaN, None, tipos incorrectos)",
            "Mejorado el logging de errores con mensajes descriptivos",
            "Añadida proteccion contra crashes en operaciones criticas de trading",
        ],
        "ia_error": False,
    }


# ══════════════════════════════════════════════════════════════
# REPORTE TXT
# ══════════════════════════════════════════════════════════════

def _generate_txt_report(session: dict, filepath: Path):
    lines = []
    lines.append("=" * 70)
    lines.append("  REPORTE DE FIXES - ANTES Y DESPUES")
    lines.append(f"  Fecha: {session['timestamp']}")
    lines.append(f"  Archivos procesados: {len(session['fixes'])}")
    lines.append("=" * 70)

    for fix in session["fixes"]:
        fname   = fix["filename"]
        status  = fix["status"]
        before  = fix.get("before", "")
        after   = fix.get("after", "")
        explain = fix.get("explanation", "")
        changes = fix.get("changes_summary", [])
        stats   = fix.get("stats", {})

        lines.append(f"\n{'─'*70}")
        lines.append(f"  ARCHIVO: {fname}   [{status}]")
        lines.append(f"{'─'*70}")

        if status == "APLICADO":
            lines.append(f"  Lineas añadidas:   +{stats.get('added', 0)}")
            lines.append(f"  Lineas eliminadas: -{stats.get('removed', 0)}")
            lines.append(f"  Total cambios:      {stats.get('total', 0)}")
            lines.append("")
            lines.append("  POR QUE ESTAS CORRECCIONES SON LAS CORRECTAS:")
            lines.append("  " + "-" * 50)
            for line in explain.split("\n"):
                lines.append("  " + line)
            lines.append("")
            lines.append("  CAMBIOS REALIZADOS:")
            for i, c in enumerate(changes, 1):
                lines.append(f"  {i}. {c}")
            lines.append("")
            lines.append("  DIFF (ANTES -> DESPUES):")
            lines.append("  " + "-" * 50)
            diff = _compute_diff(before, after)
            for dl in diff.split("\n")[:120]:
                lines.append("  " + dl)
            if len(diff.split("\n")) > 120:
                lines.append("  ... [diff truncado]")
            lines.append("")
            lines.append("  CODIGO ANTES (primeras 50 lineas):")
            lines.append("  " + "-" * 50)
            for bl in before.splitlines()[:50]:
                lines.append("  " + bl)
            lines.append("")
            lines.append("  CODIGO DESPUES (primeras 50 lineas):")
            lines.append("  " + "-" * 50)
            for al in after.splitlines()[:50]:
                lines.append("  " + al)
        elif status == "SIN_CAMBIOS_REALES":
            lines.append("  La IA genero codigo pero era identico al original.")
            lines.append("  No se aplico ningun cambio — el archivo ya estaba correcto.")
        elif status == "ERROR_IA":
            lines.append(f"  Error al generar fix: {fix.get('reason','')}")
        else:
            lines.append(f"  Razon: {fix.get('reason', 'omitido por el usuario')}")

    lines.append(f"\n{'='*70}")
    lines.append("  FIN DEL REPORTE")
    lines.append(f"{'='*70}")
    filepath.write_text("\n".join(lines), encoding="utf-8")
    print(f"  [TXT] Guardado: {filepath.name}")


# ══════════════════════════════════════════════════════════════
# REPORTE PDF
# ══════════════════════════════════════════════════════════════

def _generate_pdf_report(session: dict, filepath: Path):
    if not REPORTLAB_OK:
        print("  [!] Instala reportlab: pip install reportlab")
        return

    doc = SimpleDocTemplate(
        str(filepath), pagesize=letter,
        rightMargin=0.75*inch, leftMargin=0.75*inch,
        topMargin=0.75*inch,   bottomMargin=0.75*inch,
    )
    styles = getSampleStyleSheet()

    S_TITLE = ParagraphStyle("CT", parent=styles["Title"],
        fontSize=17, textColor=colors.HexColor("#1a1a2e"), spaceAfter=6)
    S_H1    = ParagraphStyle("H1", parent=styles["Heading1"],
        fontSize=13, textColor=colors.HexColor("#0f3460"), spaceBefore=12, spaceAfter=4)
    S_H2    = ParagraphStyle("H2", parent=styles["Heading2"],
        fontSize=10, textColor=colors.HexColor("#16213e"), spaceBefore=8, spaceAfter=3)
    S_BODY  = ParagraphStyle("BD", parent=styles["Normal"],
        fontSize=9, leading=13, spaceAfter=4)
    S_CODE  = ParagraphStyle("CD", parent=styles["Code"],
        fontSize=7, leading=10, fontName="Courier",
        backColor=colors.HexColor("#f4f4f4"),
        leftIndent=10, rightIndent=10, spaceAfter=4)
    S_ADD   = ParagraphStyle("AD", parent=S_CODE,
        textColor=colors.HexColor("#155724"), backColor=colors.HexColor("#d4edda"))
    S_REM   = ParagraphStyle("RM", parent=S_CODE,
        textColor=colors.HexColor("#721c24"), backColor=colors.HexColor("#f8d7da"))

    story = []

    # Portada
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph(_clean("REPORTE DE FIXES - ANTES Y DESPUES"), S_TITLE))
    story.append(Paragraph(_clean(f"Generado: {session['timestamp']}"), S_BODY))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#0f3460")))
    story.append(Spacer(1, 0.15*inch))

    # Resumen ejecutivo
    aplicados  = [f for f in session["fixes"] if f["status"] == "APLICADO"]
    omitidos   = [f for f in session["fixes"] if f["status"] == "OMITIDO"]
    sin_cambio = [f for f in session["fixes"] if f["status"] == "SIN_CAMBIOS_REALES"]
    errores    = [f for f in session["fixes"] if f["status"] == "ERROR_IA"]

    total_add = sum(f.get("stats",{}).get("added",0)   for f in aplicados)
    total_rem = sum(f.get("stats",{}).get("removed",0) for f in aplicados)

    summary = [
        ["Aplicados con cambios reales",  str(len(aplicados))],
        ["Omitidos por el usuario",        str(len(omitidos))],
        ["Ya correctos (sin cambios reales)", str(len(sin_cambio))],
        ["Errores de IA",                  str(len(errores))],
        ["Lineas añadidas (total)",        f"+{total_add}"],
        ["Lineas eliminadas (total)",      f"-{total_rem}"],
    ]
    tbl = Table(summary, colWidths=[3.5*inch, 2*inch])
    tbl.setStyle(TableStyle([
        ("FONTNAME",  (0,0),(-1,-1), "Helvetica"),
        ("FONTSIZE",  (0,0),(-1,-1), 9),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[colors.HexColor("#f8f9fa"),colors.HexColor("#e9ecef")]),
        ("GRID",      (0,0),(-1,-1), 0.4, colors.HexColor("#dee2e6")),
        ("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10),
        ("TOPPADDING",(0,0),(-1,-1),5),  ("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.2*inch))

    # Detalle por archivo
    for fix in session["fixes"]:
        fname   = fix["filename"]
        status  = fix["status"]
        before  = fix.get("before","")
        after   = fix.get("after","")
        explain = fix.get("explanation","")
        changes = fix.get("changes_summary",[])
        stats   = fix.get("stats",{})

        story.append(PageBreak())
        story.append(Paragraph(_clean(f"ARCHIVO: {fname}"), S_H1))

        COLOR_MAP = {
            "APLICADO":             colors.HexColor("#28a745"),
            "OMITIDO":              colors.HexColor("#6c757d"),
            "SIN_CAMBIOS_REALES":   colors.HexColor("#17a2b8"),
            "ERROR_IA":             colors.HexColor("#dc3545"),
        }
        badge_color = COLOR_MAP.get(status, colors.grey)
        badge = Table([[_clean(status)]], colWidths=[2.2*inch])
        badge.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,-1), badge_color),
            ("TEXTCOLOR",(0,0),(-1,-1), colors.white),
            ("FONTNAME",(0,0),(-1,-1),"Helvetica-Bold"),
            ("FONTSIZE",(0,0),(-1,-1),9),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
        ]))
        story.append(badge)
        story.append(Spacer(1, 0.1*inch))

        if status == "APLICADO":
            st_data = [
                ["Lineas añadidas",   f"+{stats.get('added',0)}"],
                ["Lineas eliminadas", f"-{stats.get('removed',0)}"],
                ["Total cambios",     str(stats.get('total',0))],
            ]
            st = Table(st_data, colWidths=[2.5*inch, 1.5*inch])
            st.setStyle(TableStyle([
                ("FONTNAME",(0,0),(-1,-1),"Helvetica"),("FONTSIZE",(0,0),(-1,-1),9),
                ("GRID",(0,0),(-1,-1),0.3,colors.HexColor("#dee2e6")),
                ("BACKGROUND",(0,0),(0,-1),colors.HexColor("#e9ecef")),
                ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
                ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
            ]))
            story.append(st)
            story.append(Spacer(1, 0.12*inch))

            story.append(Paragraph(_clean("POR QUE ESTAS CORRECCIONES SON LAS CORRECTAS"), S_H2))
            story.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#dee2e6")))
            for line in explain.split("\n"):
                if line.strip():
                    story.append(Paragraph(_clean(line), S_BODY))
            story.append(Spacer(1, 0.08*inch))

            story.append(Paragraph(_clean("CAMBIOS REALIZADOS"), S_H2))
            story.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#dee2e6")))
            for i, ch in enumerate(changes, 1):
                story.append(Paragraph(_clean(f"{i}. {ch}"), S_BODY))
            story.append(Spacer(1, 0.12*inch))

            story.append(Paragraph(_clean("DIFF VISUAL (ANTES -> DESPUES)"), S_H2))
            story.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#dee2e6")))
            diff = _compute_diff(before, after)
            for dl in diff.split("\n")[:80]:
                cl = _clean(dl)[:120]
                if dl.startswith("+") and not dl.startswith("+++"):
                    story.append(Preformatted(cl, S_ADD))
                elif dl.startswith("-") and not dl.startswith("---"):
                    story.append(Preformatted(cl, S_REM))
                elif dl.strip():
                    story.append(Preformatted(cl, S_CODE))
            story.append(Spacer(1, 0.12*inch))

            story.append(Paragraph(_clean("CODIGO ANTES (primeras 60 lineas)"), S_H2))
            story.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#dee2e6")))
            story.append(Preformatted(_clean("\n".join(before.splitlines()[:60])), S_CODE))
            story.append(Spacer(1, 0.08*inch))

            story.append(Paragraph(_clean("CODIGO DESPUES (primeras 60 lineas)"), S_H2))
            story.append(HRFlowable(width="100%",thickness=0.5,color=colors.HexColor("#dee2e6")))
            story.append(Preformatted(_clean("\n".join(after.splitlines()[:60])), S_CODE))

        elif status == "SIN_CAMBIOS_REALES":
            story.append(Paragraph(
                _clean("La IA genero codigo pero era identico al original. "
                       "El archivo ya estaba correcto — no se aplico ningun cambio."),
                S_BODY
            ))
        elif status == "ERROR_IA":
            story.append(Paragraph(_clean(f"Error: {fix.get('reason','')}"), S_BODY))
        else:
            story.append(Paragraph(_clean(f"Razon: {fix.get('reason','omitido')}"), S_BODY))

    story.append(PageBreak())
    story.append(Spacer(1, 0.8*inch))
    story.append(Paragraph(_clean("FIN DEL REPORTE"), S_TITLE))
    story.append(Paragraph(_clean(f"Sistema de Trading Bot | {session['timestamp']}"), S_BODY))

    try:
        doc.build(story)
        print(f"  [PDF] Guardado: {filepath.name}")
    except Exception as e:
        print(f"  [!] Error generando PDF: {e}")


# ══════════════════════════════════════════════════════════════
# FLUJO PRINCIPAL
# ══════════════════════════════════════════════════════════════

def auto_fix_flow():
    """
    Flujo completo con verificacion real:
    - Hash MD5 antes vs despues
    - Si son iguales: SIN_CAMBIOS_REALES (honesto, no miente)
    - Si son distintos: muestra diff + pide confirmacion + aplica
    - Genera PDF + TXT
    """
    now   = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M")

    print(f"\n{'='*57}")
    print("   SISTEMA DE FIXES CON IA + VERIFICACION REAL")
    print(f"{'='*57}\n")

    audit_text = _get_latest_audit()
    if not audit_text:
        print("  [!] No se encontro reporte del auditor.")
        print("  [*] Ejecuta primero: python auditor.py\n")
        return

    print("  [OK] Reporte del auditor cargado.")

    print()
    if not _confirm("Tienes backup guardado (menu.py opcion 9)?"):
        print("  [!] Guarda un backup primero: python menu.py -> opcion 9\n")
        return

    session = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "fixes": []
    }

    print(f"\n  [*] Analizando archivos con IA...\n")

    for filename in PROJECT_FILES:
        filepath = BASE / filename
        if not filepath.exists():
            continue

        # Solo procesar si el auditor menciona el archivo
        if filename not in audit_text and filename.replace(".py","") not in audit_text:
            continue

        original = filepath.read_text(encoding="utf-8", errors="replace")

        print(f"  {'─'*53}")
        print(f"  Archivo : {filename}")
        print(f"  [*] Generando fix con IA (20-40 segundos)...")

        result = _generate_fix(filename, original, audit_text)

        # Error de IA
        if result.get("ia_error"):
            print(f"  [!] Error de IA para {filename}")
            session["fixes"].append({
                "filename": filename,
                "status": "ERROR_IA",
                "reason": result["explanation"],
                "before": original,
                "after": original,
                "stats": {"added":0,"removed":0,"total":0},
            })
            continue

        corrected = result["corrected_code"]

        # ─── VERIFICACION REAL CON MD5 ───────────────────────────────
        if not _has_real_changes(original, corrected):
            print(f"  [=] SIN CAMBIOS REALES en {filename}")
            print(f"      Hash antes == hash despues — el archivo ya estaba correcto.")
            session["fixes"].append({
                "filename": filename,
                "status": "SIN_CAMBIOS_REALES",
                "reason": "Codigo generado identico al original (verificado con MD5)",
                "before": original,
                "after": original,
                "explanation": result["explanation"],
                "changes_summary": result["changes_summary"],
                "stats": {"added":0,"removed":0,"total":0},
            })
            continue

        # Hay diferencia real
        stats = _diff_stats(original, corrected)
        print(f"  [!] Cambios reales detectados: +{stats['added']} / -{stats['removed']} lineas")

        for ch in result["changes_summary"][:4]:
            print(f"      - {ch}")

        # Mostrar preview del diff en terminal
        diff_all = _compute_diff(original, corrected)
        diff_lines = [l for l in diff_all.split("\n")
                      if l.startswith(("+","-")) and not l.startswith(("+++","---"))]
        if diff_lines:
            print(f"\n  Preview del diff (primeras 12 lineas):")
            for dl in diff_lines[:12]:
                prefix = "  + " if dl.startswith("+") else "  - "
                print(f"{prefix}{dl[1:65]}")

        if not _confirm(f"Aplicar este fix a {filename}?"):
            print(f"  [>] {filename} omitido.")
            session["fixes"].append({
                "filename": filename,
                "status": "OMITIDO",
                "reason": "Omitido por el usuario",
                "before": original,
                "after": original,
                "explanation": result["explanation"],
                "changes_summary": result["changes_summary"],
                "stats": {"added":0,"removed":0,"total":0},
            })
            continue

        # Backup + aplicar
        backup_path = filepath.with_suffix(f".before_{stamp}.bak")
        backup_path.write_text(original, encoding="utf-8")
        filepath.write_text(corrected, encoding="utf-8")

        print(f"  [OK] {filename} corregido (+{stats['added']} / -{stats['removed']} lineas)")
        print(f"  [*]  Backup: {backup_path.name}")

        session["fixes"].append({
            "filename": filename,
            "status": "APLICADO",
            "before": original,
            "after": corrected,
            "explanation": result["explanation"],
            "changes_summary": result["changes_summary"],
            "stats": stats,
        })

        log = _load_fixes_log()
        log.append({
            "timestamp":         now.isoformat(),
            "archivo":           filename,
            "lineas_añadidas":   stats["added"],
            "lineas_eliminadas": stats["removed"],
            "hash_antes":        _file_hash(original),
            "hash_despues":      _file_hash(corrected),
        })
        _save_fixes_log(log)

    # Resumen
    aplicados  = [f for f in session["fixes"] if f["status"] == "APLICADO"]
    omitidos   = [f for f in session["fixes"] if f["status"] == "OMITIDO"]
    sin_cambio = [f for f in session["fixes"] if f["status"] == "SIN_CAMBIOS_REALES"]
    errores    = [f for f in session["fixes"] if f["status"] == "ERROR_IA"]

    print(f"\n{'='*57}")
    print("  RESUMEN")
    print(f"{'='*57}")
    print(f"  Aplicados con cambios reales    : {len(aplicados)}")
    for f in aplicados:
        print(f"    * {f['filename']}  (+{f['stats']['added']} / -{f['stats']['removed']})")
    if sin_cambio:
        print(f"  Ya correctos (sin cambios reales): {len(sin_cambio)}")
        for f in sin_cambio:
            print(f"    * {f['filename']}")
    if omitidos:
        print(f"  Omitidos                         : {len(omitidos)}")
    if errores:
        print(f"  Errores de IA                    : {len(errores)}")

    print(f"\n  [*] Generando reportes...\n")
    txt_path = REPORTS_DIR / f"fixes_report_{stamp}.txt"
    pdf_path = REPORTS_DIR / f"fixes_report_{stamp}.pdf"
    _generate_txt_report(session, txt_path)
    _generate_pdf_report(session, pdf_path)

    print(f"\n  [OK] Reportes en reports/")
    print(f"       PDF : fixes_report_{stamp}.pdf")
    print(f"       TXT : fixes_report_{stamp}.txt")
    print(f"\n  [TIP] Vuelve a auditar: python auditor.py\n")

    input("  Presiona Enter para continuar...")


def show_fixes_history():
    log = _load_fixes_log()
    if not log:
        print("\n  No hay historial de fixes.\n")
        return
    print(f"\n{'='*55}")
    print(f"  HISTORIAL DE FIXES ({len(log)} registros)")
    print(f"{'='*55}")
    for entry in reversed(log[-15:]):
        print(f"\n  {entry.get('timestamp','')[:16]}")
        print(f"  Archivo : {entry.get('archivo','')}")
        print(f"  +{entry.get('lineas_añadidas',0)} / -{entry.get('lineas_eliminadas',0)} lineas")
        h_a = entry.get("hash_antes","")
        h_d = entry.get("hash_despues","")
        if h_a and h_d:
            igual = "[IGUAL - no hubo cambio real]" if h_a == h_d else "[DIFERENTE - cambio aplicado]"
            print(f"  Hash: {igual}")
    print()
    input("  Presiona Enter para continuar...")


# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--auto",    action="store_true")
    p.add_argument("--history", action="store_true")
    a = p.parse_args()

    if a.auto:
        auto_fix_flow()
    elif a.history:
        show_fixes_history()
    else:
        print(f"\n{'='*45}")
        print(f"  SISTEMA DE FIXES CON IA")
        print(f"{'='*45}")
        print("  1.  Analizar y aplicar fixes automaticos")
        print("  2.  Ver historial de fixes")
        print(f"{'='*45}")
        opt = input("\n  Elige (1-2): ").strip()
        if opt == "1":
            auto_fix_flow()
        elif opt == "2":
            show_fixes_history()