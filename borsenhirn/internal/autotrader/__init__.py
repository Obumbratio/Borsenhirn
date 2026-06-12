"""
borsenhirn.internal.autotrader — AUTO-TRADER (cara interna, NO-producto).

⛔ NO importar desde el flujo de cliente. El `AutoExecutor` AUTO-EJECUTA órdenes
(discrecional) en paper; es la herramienta privada de Uriel (R&D + genera el track
record), no el producto. El producto de cliente ejecuta SOLO cuando el usuario
aprieta el botón (ejecución manual, otro módulo). Ver docs/RESECUENCIACION_PLAN.md.
"""

from borsenhirn.internal.autotrader.executor import AutoExecutor, CycleCtx

__all__ = ["AutoExecutor", "CycleCtx"]
