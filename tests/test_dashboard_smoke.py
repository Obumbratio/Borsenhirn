"""
test_dashboard_smoke.py — Garantía mínima de que dashboard.py es ejecutable.

LECCIÓN APRENDIDA · sprint v1.1
────────────────────────────────
36 tests verdes en funciones aisladas no significan nada si nadie verifica
que el archivo principal sea sintácticamente válido y arranque.

Durante el sprint v1.1, una reparación manual del archivo dejó un bloque
duplicado fuera de cualquier f-string · `ast.parse(open(file).read())` y
los tests unitarios pasaron porque el AST tolera el código muerto, pero
`python -m py_compile` falló y `streamlit run` rompía con SyntaxError.

Estos tres tests cierran ese hueco. Se ejecutan en CI antes que cualquier
otro · si fallan, ningún otro test importa.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = REPO_ROOT / "dashboard.py"


def test_dashboard_compiles():
    """py_compile · garantía sintáctica de bajo nivel."""
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(DASHBOARD)],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"dashboard.py no compila:\n{result.stderr.decode('utf-8', errors='replace')}"
    )


def test_dashboard_imports_without_streamlit_runtime(monkeypatch):
    """
    El módulo dashboard debe poder importarse · usamos un Streamlit mock para
    no requerir un servidor corriendo. Si el archivo tiene SyntaxError o
    NameError de import, este test lo detecta antes que el deploy.
    """
    # Subprocess aislado para no contaminar el sys.modules de pytest
    code = (
        "import sys, types\n"
        # Stub de streamlit que no hace nada · suficiente para que el import
        # del dashboard llegue al final del archivo.
        "st = types.ModuleType('streamlit')\n"
        "class _Cache:\n"
        "    def clear(self): pass\n"
        "    def __call__(self, *a, **kw): return lambda f: f\n"
        "st.cache_data = _Cache()\n"
        "st.session_state = {}\n"
        "st.set_page_config = lambda *a, **kw: None\n"
        "st.markdown = lambda *a, **kw: None\n"
        "st.stop = lambda: (_ for _ in ()).throw(SystemExit('stop'))\n"
        "st.columns = lambda spec, **kw: [type('C', (), {'__enter__': lambda s: None, '__exit__': lambda s,*a: None})() for _ in range(spec if isinstance(spec,int) else len(spec))]\n"
        "st.button = lambda *a, **kw: False\n"
        "st.text_input = lambda *a, **kw: ''\n"
        "st.checkbox = lambda *a, **kw: False\n"
        "st.spinner = lambda *a, **kw: type('S', (), {'__enter__': lambda s: None, '__exit__': lambda s,*a: None})()\n"
        "st.success = st.error = st.warning = st.info = lambda *a, **kw: None\n"
        "st.rerun = lambda: None\n"
        "st.plotly_chart = lambda *a, **kw: None\n"
        "st.dataframe = lambda *a, **kw: None\n"
        "st.expander = lambda *a, **kw: type('E', (), {'__enter__': lambda s: None, '__exit__': lambda s,*a: None})()\n"
        "sys.modules['streamlit'] = st\n"
        "import importlib.util\n"
        "spec = importlib.util.spec_from_file_location('dashboard_check', " + repr(str(DASHBOARD)) + ")\n"
        "mod = importlib.util.module_from_spec(spec)\n"
        "try:\n"
        "    spec.loader.exec_module(mod)\n"
        "except SystemExit:\n"
        "    pass  # st.stop() es esperado cuando no hay backend\n"
        "print('IMPORT_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=30,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert result.returncode == 0 and "IMPORT_OK" in stdout, (
        f"dashboard.py no importa\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
    )


def test_dashboard_no_orphan_strings():
    """
    Cazador de regresiones: ninguna línea fuera de un string Python debe
    empezar con un literal CSS huérfano (e.g., '9px;', 'color:', 'background:').
    Detecta el patrón exacto que causó el SyntaxError del v1.1.
    """
    src = DASHBOARD.read_text(encoding="utf-8")
    forbidden_starts = (
        "9px;", "10px;", "11px;", "12px;",
        "color:", "background:", "border:", "padding:", "margin:",
    )
    issues = []
    for lineno, line in enumerate(src.splitlines(), start=1):
        stripped = line.lstrip()
        for token in forbidden_starts:
            if stripped.startswith(token):
                issues.append(f"line {lineno}: {line!r}")
                break
    assert not issues, (
        "dashboard.py tiene CSS huérfano fuera de un string Python:\n  "
        + "\n  ".join(issues)
    )


def test_dashboard_balanced_quotes():
    """
    Sanidad: el número de triple-quotes debe ser par. Si un string queda
    sin cerrar, el archivo entero se desconfigura silenciosamente.
    """
    src = DASHBOARD.read_text(encoding="utf-8")
    triple_double = src.count('"""')
    triple_single = src.count("'''")
    assert triple_double % 2 == 0, (
        f'dashboard.py tiene {triple_double} triple-comillas dobles · debe ser par'
    )
    assert triple_single % 2 == 0, (
        f"dashboard.py tiene {triple_single} triple-comillas simples · debe ser par"
    )


# ─── Cobertura extendida · todos los módulos del dashboard ──────────────────

DASHBOARD_MODULES = [
    REPO_ROOT / "borsenhirn" / "dashboard" / "bitacora_theme.py",
    REPO_ROOT / "borsenhirn" / "dashboard" / "bitacora_data.py",
    REPO_ROOT / "borsenhirn" / "dashboard" / "bitacora_voice.py",
    REPO_ROOT / "borsenhirn" / "dashboard" / "bitacora_state.py",
]


@pytest.mark.parametrize("module_path", DASHBOARD_MODULES,
                          ids=lambda p: p.name)
def test_dashboard_module_compiles(module_path):
    """
    Cada módulo del dashboard debe pasar `python -m py_compile`. Si alguno
    falla, dashboard.py rompe en runtime aunque dashboard.py mismo esté OK.
    Esta es la regresión exacta que dejó el sprint v1.1: bitacora_theme.py
    quedó truncado y dashboard.py no podía importarlo.
    """
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(module_path)],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"{module_path.name} no compila:\n"
        f"{result.stderr.decode('utf-8', errors='replace')}"
    )


@pytest.mark.parametrize("module_path", DASHBOARD_MODULES,
                          ids=lambda p: p.name)
def test_dashboard_module_balanced_brackets(module_path):
    """
    Brackets balanceados a nivel de archivo. No reemplaza a `py_compile` pero
    captura un patrón específico de corrupción (truncado mid-list seguido de
    auto-fix duplicado): cuando los brackets quedan duplicados, el conteo
    diverge antes que py_compile detecte el SyntaxError.
    """
    src = module_path.read_text(encoding="utf-8")
    # Excluir brackets dentro de strings · approach simple: contar en source
    # crudo y aceptar diff = 0. El test es robusto porque los strings con
    # brackets balanceados no afectan el conteo total.
    assert src.count("[") == src.count("]"), (
        f"{module_path.name} tiene corchetes desbalanceados · "
        f"posible duplicación post-truncado"
    )
    assert src.count("{") == src.count("}"), (
        f"{module_path.name} tiene llaves desbalanceadas"
    )
    assert src.count("(") == src.count(")"), (
        f"{module_path.name} tiene paréntesis desbalanceados"
    )


def test_dashboard_module_imports_chain():
    """
    Cadena completa de imports: bitacora_theme → bitacora_voice → bitacora_state
    → bitacora_data. Si cualquiera falla, dashboard.py también falla.
    """
    code = (
        "import borsenhirn.dashboard.bitacora_theme as t\n"
        "import borsenhirn.dashboard.bitacora_voice as v\n"
        "import borsenhirn.dashboard.bitacora_state as s\n"
        "import borsenhirn.dashboard.bitacora_data as d\n"
        "assert hasattr(t, 'PALETTE')\n"
        "assert hasattr(v, 'get_observation')\n"
        "assert hasattr(s, 'current_eintrag')\n"
        "assert hasattr(d, 'build_payload')\n"
        "print('CHAIN_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=15,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "CHAIN_OK" in stdout, (
        f"cadena de imports rota\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
    )


# ─── Cobertura extendida · todos los módulos del dashboard ──────────────────

DASHBOARD_MODULES = [
    REPO_ROOT / "borsenhirn" / "dashboard" / "bitacora_theme.py",
    REPO_ROOT / "borsenhirn" / "dashboard" / "bitacora_data.py",
    REPO_ROOT / "borsenhirn" / "dashboard" / "bitacora_voice.py",
    REPO_ROOT / "borsenhirn" / "dashboard" / "bitacora_state.py",
]


@pytest.mark.parametrize("module_path", DASHBOARD_MODULES,
                          ids=lambda p: p.name)
def test_dashboard_module_compiles(module_path):
    """
    Cada módulo del dashboard debe pasar `python -m py_compile`. Si alguno
    falla, dashboard.py rompe en runtime aunque dashboard.py mismo este OK.
    Esta es la regresion exacta que dejo el sprint v1.1: bitacora_theme.py
    quedo truncado y dashboard.py no podia importarlo.
    """
    result = subprocess.run(
        [sys.executable, "-m", "py_compile", str(module_path)],
        capture_output=True,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"{module_path.name} no compila:\n"
        f"{result.stderr.decode('utf-8', errors='replace')}"
    )


@pytest.mark.parametrize("module_path", DASHBOARD_MODULES,
                          ids=lambda p: p.name)
def test_dashboard_module_balanced_brackets(module_path):
    """
    Brackets balanceados a nivel de archivo. Captura un patron especifico
    de corrupcion (truncado mid-list seguido de auto-fix duplicado): cuando
    los brackets quedan duplicados, el conteo diverge antes que py_compile
    detecte el SyntaxError.
    """
    src = module_path.read_text(encoding="utf-8")
    assert src.count("[") == src.count("]"), (
        f"{module_path.name} tiene corchetes desbalanceados · "
        f"posible duplicacion post-truncado"
    )
    assert src.count("{") == src.count("}"), (
        f"{module_path.name} tiene llaves desbalanceadas"
    )
    assert src.count("(") == src.count(")"), (
        f"{module_path.name} tiene parentesis desbalanceados"
    )


def test_dashboard_module_imports_chain():
    """
    Cadena completa de imports: theme -> voice -> state -> data.
    Si cualquiera falla, dashboard.py tambien falla.
    """
    code = (
        "import borsenhirn.dashboard.bitacora_theme as t\n"
        "import borsenhirn.dashboard.bitacora_voice as v\n"
        "import borsenhirn.dashboard.bitacora_state as s\n"
        "import borsenhirn.dashboard.bitacora_data as d\n"
        "assert hasattr(t, 'PALETTE')\n"
        "assert hasattr(v, 'get_observation')\n"
        "assert hasattr(s, 'current_eintrag')\n"
        "assert hasattr(d, 'build_payload')\n"
        "print('CHAIN_OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        cwd=str(REPO_ROOT),
        timeout=15,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "CHAIN_OK" in stdout, (
        f"cadena de imports rota\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
    )
        cwd=str(REPO_ROOT),
        timeout=15,
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    assert "CHAIN_OK" in stdout, (
        f"cadena de imports rota\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}"
    )
