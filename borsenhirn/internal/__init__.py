"""
borsenhirn.internal — código INTERNO / NO-PRODUCTO.

⛔ LÍNEA ROJA: NADA de este paquete debe ser importado por el flujo de cliente
(el API de cliente `borsenhirn/api/main.py` ni lo que el usuario toca). Acá vive
el auto-trader (auto-ejecución discrecional), que es herramienta privada/R&D, no
producto. El producto de cliente usa ejecución MANUAL (el usuario aprieta el botón).

Un test de guardrail (`tests/test_red_line_guardrail.py`) hace cumplir esto: falla
si `borsenhirn.api.main` importa (directa o transitivamente) `borsenhirn.internal.autotrader`.
Ver docs/RESECUENCIACION_PLAN.md (Paso 1.5).
"""
