"""
auditor.py - Auditoría completa automática del proyecto de trading.

Revisa TODO el código y genera un reporte PDF con:
- Lo que está bien
- Lo que hay que mejorar
- Errores potenciales
- Sugerencias concretas
- Puntuación general del proyecto

Uso:
    python auditor.py
"""

import os
import ast
import sys
import importlib
import requests
import logging
from datetime import datetime

import config
from logger import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

try:
    from fpdf import FPDF
    PDF_OK = True
except ImportError:
    PDF_OK = False

# Archivos del proyecto a auditar
PROJECT_FILES = [
    "config.py", "data_fetcher.py", "indicators.py",
    "ml_model.py", "strategy.py", "risk_manager.py",
    "execution.py", "logger.py", "backtest.py",
    "main.py", "reporter.py",
]

BASE = os.path.dirname(os.path.abspath(__file__))


# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════
def _clean(text: str) -> str:
    replacements = {
        "\u2014":"-","\u2013":"-","\u2019":"'","\u2018":"'",
        "\u201c":'"',"\u201d":'"',"\u2022":"*","\u2026":"...",
        "\u2192":"->","\u2191":"^","\u2193":"v","\u2713":"OK",
        "\u274c":"X","\u2705":"OK","\u26a0":"!","\u2b50":"*",
        "**":"", "##":"",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _claude(messages: list, system: str, max_tokens: int = 2500) -> str:
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": os.getenv("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": max_tokens,
                "system": system,
                "messages": messages,
            },
            timeout=60,
        )
        data = resp.json()
        if "content" not in data:
            return f"Error API: {data.get('error',{}).get('message', str(data))}"
        return data["content"][0]["text"]
    except Exception as e:
        return f"[Error IA: {e}]"


# ══════════════════════════════════════════════════════════════
# AUDITORÍA ESTÁTICA (sin IA)
# ══════════════════════════════════════════════════════════════
def check_syntax(filepath: str) -> dict:
    """Verifica sintaxis Python del archivo."""
    result = {"file": filepath, "syntax_ok": False, "error": None}
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
        ast.parse(source)
        result["syntax_ok"] = True
    except SyntaxError as e:
        result["error"] = f"Línea {e.lineno}: {e.msg}"
    except Exception as e:
        result["error"] = str(e)
    return result


def check_imports(filepath: str) -> dict:
    """Verifica que los imports del archivo estén disponibles."""
    result = {"file": filepath, "missing": [], "ok": []}
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    names = [alias.name.split(".")[0] for alias in node.names]
                else:
                    names = [node.module.split(".")[0]] if node.module else []
                for name in names:
                    # Ignorar imports locales del proyecto
                    if name in ("config","data_fetcher","indicators","ml_model",
                                "strategy","risk_manager","execution","logger",
                                "reporter","backtest","auditor"):
                        continue
                    try:
                        importlib.import_module(name)
                        if name not in result["ok"]:
                            result["ok"].append(name)
                    except ImportError:
                        if name not in result["missing"]:
                            result["missing"].append(name)
    except Exception as e:
        result["error"] = str(e)
    return result


def check_try_except(filepath: str) -> dict:
    """Cuenta funciones con y sin manejo de errores."""
    result = {"file": filepath, "funcs_total": 0,
              "funcs_with_try": 0, "funcs_without_try": []}
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                result["funcs_total"] += 1
                has_try = any(isinstance(n, ast.Try)
                              for n in ast.walk(node))
                if has_try:
                    result["funcs_with_try"] += 1
                else:
                    result["funcs_without_try"].append(node.name)
    except Exception:
        pass
    return result


def check_docstrings(filepath: str) -> dict:
    """Verifica funciones/clases sin docstrings."""
    result = {"file": filepath, "missing_docs": []}
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if not (node.body and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)):
                    result["missing_docs"].append(node.name)
    except Exception:
        pass
    return result


def check_file_structure() -> dict:
    """Verifica que existan todos los archivos y carpetas necesarios."""
    required_files   = PROJECT_FILES + [".env", "requirements.txt"]
    required_folders = ["models", "logs", "results", "reports"]
    missing_files    = []
    missing_folders  = []

    for f in required_files:
        if not os.path.exists(os.path.join(BASE, f)):
            missing_files.append(f)

    for d in required_folders:
        if not os.path.exists(os.path.join(BASE, d)):
            missing_folders.append(d)

    return {"missing_files": missing_files, "missing_folders": missing_folders}


def check_env() -> dict:
    """Verifica que el .env tenga todas las variables necesarias."""
    required = ["ALPACA_API_KEY", "ALPACA_SECRET_KEY",
                "ALPACA_BASE_URL", "ANTHROPIC_API_KEY"]
    from dotenv import dotenv_values
    env = dotenv_values(os.path.join(BASE, ".env"))
    missing  = [k for k in required if not env.get(k)]
    present  = [k for k in required if env.get(k)]
    return {"present": present, "missing": missing}


def check_model_trained() -> dict:
    """Verifica si el modelo ML está entrenado."""
    model_ok  = os.path.exists(os.path.join(BASE, config.MODEL_PATH))
    scaler_ok = os.path.exists(os.path.join(BASE, config.SCALER_PATH))
    return {"model": model_ok, "scaler": scaler_ok,
            "trained": model_ok and scaler_ok}


def check_logs() -> dict:
    """Analiza los logs en busca de errores recientes."""
    log_path = os.path.join(BASE, "logs", "trading_bot.log")
    result   = {"errors": [], "warnings": [], "total_lines": 0}
    if not os.path.exists(log_path):
        result["note"] = "Sin logs todavía (normal si el bot no ha corrido)"
        return result
    with open(log_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    result["total_lines"] = len(lines)
    for line in lines[-200:]:   # últimas 200 líneas
        if "ERROR" in line:
            result["errors"].append(line.strip()[:120])
        elif "WARNING" in line:
            result["warnings"].append(line.strip()[:120])
    return result


# ══════════════════════════════════════════════════════════════
# AUDITORÍA CON IA
# ══════════════════════════════════════════════════════════════
def ai_code_review(file_results: list) -> str:
    """Claude revisa todos los resultados y da análisis completo."""

    # Leer contenido de los archivos más importantes
    code_snippets = {}
    key_files = PROJECT_FILES  # leer TODOS los archivos completos
    for fname in key_files:
        fpath = os.path.join(BASE, fname)
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                code_snippets[fname] = f.read()  # archivo completo

    system = """
Eres un experto en trading algorítmico y Python. Vas a auditar un proyecto de trading bot.
Analiza los resultados de las pruebas automáticas Y el código fuente proporcionado.
Sé específico, usa ejemplos concretos del código cuando detectes problemas.
Responde en español.
"""

    prompt = f"""
RESULTADOS DE AUDITORÍA AUTOMÁTICA:
{_format_results_for_ai(file_results)}

CÓDIGO FUENTE COMPLETO DE TODOS LOS ARCHIVOS:
(Tienes acceso al código 100% completo de cada archivo, analiza en profundidad)
{_format_code_for_ai(code_snippets)}

Genera una auditoría completa con estas secciones EXACTAS:

## PUNTUACION GENERAL: X/10

## LO QUE ESTA BIEN (mínimo 5 puntos)
(qué funciona correctamente, qué está bien implementado)

## PROBLEMAS CRITICOS (si los hay)
(bugs, errores de lógica, riesgos de seguridad)

## AREAS DE MEJORA
(no son errores pero podrían ser mejores)

## MEJORAS EN LA ESTRATEGIA DE TRADING
(específicamente para mejorar el rendimiento del bot)

## PLAN DE ACCION PRIORIZADO
(lista ordenada de qué hacer primero, con estimado de impacto)

## VEREDICTO FINAL
(¿está listo para paper trading? ¿y para dinero real? ¿qué falta?)
"""

    return _claude([{"role": "user", "content": prompt}], system, max_tokens=4096)


def _format_results_for_ai(results: list) -> str:
    lines = []
    for r in results:
        lines.append(f"\n--- {r.get('file','general')} ---")
        for k, v in r.items():
            if k != "file":
                lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _format_code_for_ai(snippets: dict) -> str:
    lines = []
    for fname, code in snippets.items():
        lines.append(f"\n=== {fname} ===\n{code}\n")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# GENERAR PDF DE AUDITORÍA
# ══════════════════════════════════════════════════════════════
def generate_audit_pdf(static_results: dict, ai_review: str, score: str):
    if not PDF_OK:
        print("fpdf2 no instalado. Solo se guarda TXT.")
        return

    today    = datetime.now().strftime("%Y-%m-%d %H:%M")
    pdf_path = f"reports/auditoria_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
    pdf      = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    # ── Portada ───────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(20, 40, 100)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 20, "AUDITORIA DEL PROYECTO", ln=True, fill=True, align="C")
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 12, "Trading Bot Algoritmico con IA", ln=True, fill=True, align="C")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(5)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"Fecha: {today}", ln=True, align="C")
    pdf.cell(0, 7, f"Puntuacion: {score}", ln=True, align="C")
    pdf.ln(8)

    # ── Resumen de checks estáticos ───────────────────────────
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_fill_color(230, 240, 255)
    pdf.cell(0, 9, "RESULTADOS DE VERIFICACION AUTOMATICA", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 10)
    pdf.ln(2)

    # Archivos
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Archivos del proyecto:", ln=True)
    pdf.set_font("Helvetica", "", 10)
    struct = static_results.get("structure", {})
    if struct.get("missing_files"):
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 6, f"  Archivos faltantes: {', '.join(struct['missing_files'])}", ln=True)
        pdf.set_text_color(0, 0, 0)
    else:
        pdf.set_text_color(0, 150, 0)
        pdf.cell(0, 6, "  Todos los archivos presentes  OK", ln=True)
        pdf.set_text_color(0, 0, 0)

    # Modelo ML
    ml = static_results.get("model", {})
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Modelo ML:", ln=True)
    pdf.set_font("Helvetica", "", 10)
    status = "Entrenado y listo" if ml.get("trained") else "NO entrenado"
    color  = (0, 150, 0) if ml.get("trained") else (200, 0, 0)
    pdf.set_text_color(*color)
    pdf.cell(0, 6, f"  {status}", ln=True)
    pdf.set_text_color(0, 0, 0)

    # .env
    env = static_results.get("env", {})
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Variables de entorno (.env):", ln=True)
    pdf.set_font("Helvetica", "", 10)
    for k in env.get("present", []):
        pdf.set_text_color(0, 150, 0)
        pdf.cell(0, 5, f"  OK  {k}", ln=True)
    for k in env.get("missing", []):
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 5, f"  FALTA  {k}", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # Sintaxis por archivo
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, "Sintaxis de archivos:", ln=True)
    pdf.set_font("Helvetica", "", 9)
    for r in static_results.get("syntax", []):
        if r["syntax_ok"]:
            pdf.set_text_color(0, 150, 0)
            pdf.cell(0, 5, f"  OK   {r['file']}", ln=True)
        else:
            pdf.set_text_color(200, 0, 0)
            pdf.cell(0, 5, f"  ERROR  {r['file']}: {r.get('error','')}", ln=True)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)

    # Logs
    logs = static_results.get("logs", {})
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, f"Logs ({logs.get('total_lines',0)} lineas):", ln=True)
    pdf.set_font("Helvetica", "", 9)
    if logs.get("errors"):
        pdf.set_text_color(200, 0, 0)
        pdf.cell(0, 5, f"  Errores recientes: {len(logs['errors'])}", ln=True)
        for e in logs["errors"][:3]:
            pdf.cell(0, 4, f"    {_clean(e[:100])}", ln=True)
    else:
        pdf.set_text_color(0, 150, 0)
        pdf.cell(0, 5, "  Sin errores en logs  OK", ln=True)
    pdf.set_text_color(0, 0, 0)

    # ── Análisis IA ───────────────────────────────────────────
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_fill_color(230, 240, 255)
    pdf.cell(0, 9, "ANALISIS COMPLETO POR IA", ln=True, fill=True)
    pdf.set_font("Helvetica", "", 9)
    pdf.ln(3)

    for line in ai_review.split("\n"):
        line = _clean(line.strip())
        if not line:
            pdf.ln(2); continue
        if line.startswith("##") or line.startswith("PUNTUACION") or line.isupper():
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_fill_color(220, 230, 255)
            pdf.cell(0, 7, line.replace("##","").strip(), ln=True, fill=True)
            pdf.set_font("Helvetica", "", 9)
        elif line.startswith("-") or line.startswith("*"):
            while len(line) > 105:
                pdf.cell(0, 5, "  " + line[:105], ln=True)
                line = line[105:]
            pdf.cell(0, 5, "  " + line, ln=True)
        else:
            while len(line) > 105:
                pdf.cell(0, 5, line[:105], ln=True)
                line = line[105:]
            if line:
                pdf.cell(0, 5, line, ln=True)

    pdf.output(pdf_path)
    print(f"\n✅ PDF de auditoría guardado en: {pdf_path}")
    return pdf_path


# ══════════════════════════════════════════════════════════════
# MAIN — EJECUTAR AUDITORÍA COMPLETA
# ══════════════════════════════════════════════════════════════
def run_audit():
    print(f"\n{'═'*58}")
    print(f"  🔍  AUDITORÍA COMPLETA DEL PROYECTO")
    print(f"{'═'*58}\n")

    static_results = {}
    all_file_results = []

    # ── 1. Estructura del proyecto ────────────────────────────
    print("📁 Verificando estructura del proyecto...")
    static_results["structure"] = check_file_structure()
    s = static_results["structure"]
    if s["missing_files"]:
        print(f"   ⚠️  Archivos faltantes: {s['missing_files']}")
    else:
        print(f"   ✅  Todos los archivos presentes")

    # ── 2. Variables de entorno ───────────────────────────────
    print("🔑 Verificando .env...")
    static_results["env"] = check_env()
    e = static_results["env"]
    for k in e["present"]:  print(f"   ✅  {k}")
    for k in e["missing"]:  print(f"   ❌  FALTA: {k}")

    # ── 3. Modelo ML ─────────────────────────────────────────
    print("🧠 Verificando modelo ML...")
    static_results["model"] = check_model_trained()
    m = static_results["model"]
    print(f"   {'✅' if m['trained'] else '❌'}  Modelo: {'listo' if m['trained'] else 'NO entrenado'}")

    # ── 4. Sintaxis de cada archivo ───────────────────────────
    print("📝 Verificando sintaxis de archivos...")
    syntax_results = []
    for fname in PROJECT_FILES:
        fpath = os.path.join(BASE, fname)
        if os.path.exists(fpath):
            r = check_syntax(fpath)
            syntax_results.append(r)
            status = "✅" if r["syntax_ok"] else f"❌ {r.get('error','')}"
            print(f"   {status}  {fname}")
            all_file_results.append(r)
    static_results["syntax"] = syntax_results

    # ── 5. Imports ────────────────────────────────────────────
    print("📦 Verificando imports...")
    import_results = []
    for fname in PROJECT_FILES:
        fpath = os.path.join(BASE, fname)
        if os.path.exists(fpath):
            r = check_imports(fpath)
            r["file"] = fname
            import_results.append(r)
            if r["missing"]:
                print(f"   ❌  {fname}: imports faltantes → {r['missing']}")
            all_file_results.append(r)
    static_results["imports"] = import_results

    # ── 6. Manejo de errores ──────────────────────────────────
    print("🛡️  Verificando manejo de errores...")
    try_results = []
    for fname in PROJECT_FILES:
        fpath = os.path.join(BASE, fname)
        if os.path.exists(fpath):
            r = check_try_except(fpath)
            r["file"] = fname
            try_results.append(r)
            if r["funcs_without_try"]:
                print(f"   ⚠️  {fname}: funciones sin try/except → {r['funcs_without_try'][:3]}")
            all_file_results.append(r)
    static_results["try_except"] = try_results

    # ── 7. Docstrings ─────────────────────────────────────────
    print("📖 Verificando documentación...")
    doc_results = []
    for fname in PROJECT_FILES:
        fpath = os.path.join(BASE, fname)
        if os.path.exists(fpath):
            r = check_docstrings(fpath)
            r["file"] = fname
            doc_results.append(r)
            all_file_results.append(r)
    static_results["docs"] = doc_results

    # ── 8. Logs ───────────────────────────────────────────────
    print("📋 Analizando logs...")
    static_results["logs"] = check_logs()
    logs = static_results["logs"]
    print(f"   {'⚠️' if logs.get('errors') else '✅'}  "
          f"{len(logs.get('errors',[]))} errores | "
          f"{len(logs.get('warnings',[]))} warnings en logs")

    # ── 9. Análisis con IA ────────────────────────────────────
    print("\n🧠 Enviando todo a la IA para análisis profundo...")
    print("   (esto puede tardar 20-30 segundos)\n")
    ai_review = ai_code_review(all_file_results)

    # Extraer puntuación
    score = "N/A"
    for line in ai_review.split("\n"):
        if "PUNTUACION" in line.upper() or "PUNTUACIÓN" in line.upper():
            score = line.strip()
            break

    # ── Mostrar resumen en consola ────────────────────────────
    print(f"\n{'═'*58}")
    print(ai_review)
    print(f"{'═'*58}\n")

    # ── Guardar TXT ───────────────────────────────────────────
    txt_path = f"reports/auditoria_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"AUDITORÍA DEL PROYECTO — {datetime.now()}\n{'='*50}\n\n")
        f.write(ai_review)
    print(f"✅ TXT guardado en: {txt_path}")

    # ── Generar PDF ───────────────────────────────────────────
    generate_audit_pdf(static_results, ai_review, score)

    print(f"\n{'═'*58}")
    print(f"  Auditoría completada. Revisa la carpeta reports/")
    print(f"{'═'*58}\n")


if __name__ == "__main__":
    run_audit()