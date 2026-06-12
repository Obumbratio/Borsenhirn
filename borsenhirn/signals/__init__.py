"""
borsenhirn.signals — el "cerebro compartido": produce señal/análisis, NO ejecuta.

`SignalEngine.analyze()` devuelve un `CycleSignals` (régimen + contexto + resultado
del scanner). No manda órdenes ni escribe outcomes. Lo consumen dos caras:
el AutoExecutor interno (auto-trade en paper) y, en el producto, la ejecución
manual del usuario. Ver docs/RESECUENCIACION_PLAN.md.
"""

from borsenhirn.signals.engine import CycleSignals, SignalEngine

__all__ = ["CycleSignals", "SignalEngine"]
