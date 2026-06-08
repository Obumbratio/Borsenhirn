# ERRORES — bitácora
> Formato: error -> causa -> fix -> lección

### [2026-06-01] ImportError: _get_conn en main.py
- Causa: función borrada en refactor 5.4.a, seguía importada
- Fix: quitar el import
- Lección: verificar con ast.parse antes de dar por cerrado

### [2026-06-07] record_ml_metrics crash: schema "np" does not exist
- Síntoma: al entrenar el modelo, INSERT con SQL `np.float64(0.75...)` → `psycopg2.errors.InvalidSchemaName: schema "np" does not exist`.
- Causa: numpy 2.0 cambió el repr de los escalares (`repr(np.float64(0.75))` = "np.float64(0.75)"); psycopg2 adapta np.float64 con ese repr → SQL inválido. Las métricas sklearn (accuracy/precision/...) son np.float64.
- Fix: adaptadores globales numpy→psycopg2 en `borsenhirn/db.py` (float64/float32/int64/int32/bool_ → tipos Python). Cubre TODOS los INSERT con numpy, no solo este.
- Lección: los 387 tests mockean la DB → no atrapan adaptación de tipos. Correr el bot real (paper, dev) destapó el bug. Validar con un run real, no solo unit tests.
