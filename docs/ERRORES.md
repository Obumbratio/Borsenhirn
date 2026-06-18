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

### [2026-06-17] El frontend tira "Failed to fetch" al backend (parecía "API caída")
- Síntoma: la pantalla de conectar Alpaca (`/dashboard/broker`) mostraba "Failed to
  fetch" / "No se pudo contactar al backend en localhost:8000". Las tarjetas
  (`/dashboard`) SÍ funcionaban. La API respondía `/health`=200 desde dentro de WSL.
- DOS causas distintas (ojo: la API NUNCA estuvo caída):
  1. **Binding WSL.** uvicorn estaba en `--host 127.0.0.1` → solo loopback interno de
     WSL. El browser corre en Windows y el reenvío de `localhost` de WSL2 SOLO alcanza
     binds en `0.0.0.0`. Por eso Next (`*:3000`) sí y la API (`127.0.0.1:8000`) no.
  2. **CORS.** El fetch de las tarjetas es server-side (Next dentro de WSL → API dentro
     de WSL, sin CORS). El de broker es client-side (browser → :8000) con header
     `Authorization` → el browser manda un preflight `OPTIONS`. La API no tenía
     CORSMiddleware → `OPTIONS`=405 sin `Access-Control-Allow-Origin` → browser bloquea.
- Fix: (1) levantar la API con `--host 0.0.0.0`; (2) `CORSMiddleware` en
  `borsenhirn/api/main.py` (orígenes por env `CORS_ALLOW_ORIGINS`, default
  `localhost:3000`). Ambos quedan baked en `scripts/run_dev_stack.sh`.
- Lección: "Failed to fetch" = falla de RED del browser (no un 5xx). En WSL2, para
  superficies client-side: bindear la API a 0.0.0.0 Y habilitar CORS. Un 5xx, en
  cambio, llega como respuesta (res.ok=false), no como "Failed to fetch".
