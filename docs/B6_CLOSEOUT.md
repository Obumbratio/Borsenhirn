# B6 — Cierre (Worker isolation)

> Síntesis. Diseño/decisiones → [B6_WORKERS_PLAN.md](B6_WORKERS_PLAN.md). Estado: [ESTADO.md](ESTADO.md).

## Resultado en una frase

Hay una **capa de orquestación que corre el bot por tenant, aislado**: cada
tenant con su `tenant_id` (RLS), sus credenciales de broker (vault B2), su
kill-switch (se saltea si está HALT), y **el fallo de un tenant no frena a los
demás** (try/except por tenant).

## Qué se entregó (`borsenhirn/workers/`)

| Pieza | Qué |
|---|---|
| `load_broker_credentials(tenant_id)` | Claves del broker del tenant desde el vault (B2); fallback al config global para el default tenant (preserva single-user). |
| `TenantWorker(tenant_id, credentials)` | Contexto aislado de un tenant; `run_cycle(cycle_fn)` corre un ciclo marcando el actor de audit como `worker:<tenant>`. |
| `WorkerOrchestrator(tenant_manager)` | `run_once(cycle_fn)`: recorre los tenants ACTIVE, saltea los HALT, corre cada ciclo con **try/except aislado**. Devuelve un resumen por tenant. |
| `run_all_tenants` / `make_halted_check` | Wire-up con la DB real (lista activos por admin, kill-switch por tenant). |

## Diseño (claves)

- **Secuencial con aislamiento de errores** (D1): un proceso, try/except por
  tenant. Migrable a proceso-por-tenant sin cambiar la interfaz.
- **`cycle_fn` inyectable**: el orquestador se testea sin el bot completo; el
  ciclo real del bot se enchufa después (reusa `main`, sin reescribir el loop).
- **Aislamiento**: datos por RLS, credenciales por vault, fallos contenidos,
  kill-switch per-tenant respetado.

## Métricas

- **Tests:** 8 (7 unit + 1 e2e contra dev). Baseline **361 → 368 passed**.

## Lo que queda (fuera del framework)

1. **Wire-up del ciclo real del bot** como `cycle_fn` (extraer un ciclo de
   `main.run()` o adaptar). Es lo único entre "framework" y "multi-tenant vivo".
2. **Proceso-por-tenant** (multiprocessing) si la escala lo pide (D1 alternativa).
3. **Scheduler/loop** que llame `run_all_tenants` periódicamente.

## Para CV / portfolio

> "Orquestación multi-tenant del bot: workers aislados por tenant (RLS + creds
> del vault por tenant), aislamiento de fallos (un tenant no tumba a otros),
> kill-switch per-tenant respetado, y diseño con ciclo inyectable testeable sin
> el bot completo — migrable a proceso-por-tenant."
