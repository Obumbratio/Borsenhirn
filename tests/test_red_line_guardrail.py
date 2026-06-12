"""
Guardrail de la LÍNEA ROJA (Paso 1.5 de docs/RESECUENCIACION_PLAN.md).

El producto de cliente NUNCA debe auto-ejecutar. El auto-trader vive en
`borsenhirn.internal.autotrader`. Este test falla si el API de cliente
(`borsenhirn.api.main`) importa ese paquete — directa o TRANSITIVAMENTE (p.ej. si
importara `BotEngine`, que importa el auto-trader).

Cómo: importa `borsenhirn.api.main` en un SUBPROCESO limpio y revisa `sys.modules`.
Si aparece cualquier `borsenhirn.internal.autotrader*`, la red roja se cruzó.
"""

from __future__ import annotations

import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Máquinas de AUTO-ejecución que el flujo de cliente NO debe poder alcanzar:
#  - internal.autotrader  : el AutoExecutor (manda órdenes solo).
#  - borsenhirn.engine     : BotEngine, el orquestador del auto-trader.
#  - workers.bot_cycle     : make_bot_cycle_fn, que construye BotEngine.
# (engine/bot_cycle se incluyen porque importan el autotrader, a veces lazy.)
_FORBIDDEN = (
    "borsenhirn.internal.autotrader",
    "borsenhirn.engine",
    "borsenhirn.workers.bot_cycle",
)

# Importa el API de cliente y reporta si quedó cargada alguna de esas máquinas.
_CHECK = (
    "import importlib, sys; "
    f"FORB = {_FORBIDDEN!r}; "
    "importlib.import_module('borsenhirn.api.main'); "
    "bad = sorted(m for m in sys.modules if any(m.startswith(p) for p in FORB)); "
    "print('BAD:' + ','.join(bad)); "
    "sys.exit(2 if bad else 0)"
)


def _run_import_check() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-c", _CHECK],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )


def test_client_api_does_not_import_autotrader():
    r = _run_import_check()
    assert r.returncode == 0, (
        "⛔ LÍNEA ROJA cruzada: borsenhirn.api.main importó "
        "borsenhirn.internal.autotrader (directa o transitivamente). "
        "El flujo de cliente NO debe poder auto-ejecutar.\n"
        f"módulos detectados: {r.stdout.strip()}\n"
        f"stderr: {r.stderr[-1500:]}"
    )
    # Confirmar que el chequeo realmente corrió (importó el API y reportó).
    assert "BAD:" in r.stdout, f"el subproceso no reportó: {r.stdout!r} / {r.stderr[-800:]}"
