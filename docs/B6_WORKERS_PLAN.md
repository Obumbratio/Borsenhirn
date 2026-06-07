# B6 — Worker isolation · Plan (para revisar)

> Plan del bloqueador B6. Greenfield (el bot es single-tenant). Estado: [ESTADO.md](ESTADO.md).

## 1. Objetivo y alcance

**Objetivo:** correr el bot **por tenant, aislado** — cada tenant con su
`tenant_id` (RLS), sus credenciales de broker (del vault B2), su kill-switch
(ya tenant-scoped), y que **el fallo/halt de un tenant no afecte a otros**.

| | |
|---|---|
| **IN scope** | Capa de orquestación: cargar credenciales por tenant, un `TenantWorker` que ejecuta un ciclo aislado, y un `WorkerOrchestrator` que recorre los tenants activos con aislamiento de errores. |
| **OUT scope** | Infra de deployment (pods/containers por tenant, autoscaling). El multiprocessing real es opcional (ver D1). El cuerpo del loop del bot (`main.run`) se reusa, no se reescribe. |

## 2. Estado actual

- `main.run()` es **single-tenant**: `BotMemory(DEFAULT)`, `SafetyStack(DEFAULT)`,
  `Executor()` con `config.ALPACA_API_KEY` (global), `while True`.
- **No hay** orquestación ni workers.
- `TenantManager.list_tenants(status=ACTIVE)` ya existe → lista de quién correr.
- Credenciales por tenant: `CredentialStore` (B2 vault) ya guarda/lee las claves
  Alpaca cifradas por `user_id`/`tenant_id`.

## 3. Diseño (pluggable + testeable)

```
load_broker_credentials(tenant_id) -> (api_key, api_secret)
    desde CredentialStore (vault). Fallback al config global para el default.

TenantWorker(tenant_id, credentials)
    contexto aislado de un tenant: BotMemory/SafetyStack(tenant_id) +
    Executor/DataFetcher con SUS credenciales. run_cycle(cycle_fn) ejecuta un
    ciclo bajo ese contexto.

WorkerOrchestrator(tenant_manager, cycle_fn)
    .run_once(): lista tenants ACTIVE, saltea los que están en kill-switch
    HALT, y corre el ciclo de cada uno con try/except AISLADO (un error no
    frena a los demás). Devuelve un resumen por tenant.
```
El `cycle_fn` (la lógica del bot por ciclo) es **inyectable** → el orquestador
se testea sin el bot completo; el wire-up del ciclo real reusa `main`.

## 4. Aislamiento garantizado

- **Datos:** cada worker corre bajo su `tenant_id` → RLS aísla (ya probado en B1).
- **Credenciales:** cada worker usa las claves del tenant (vault), no las globales.
- **Fallos:** `try/except` por tenant en el orquestador → un crash no cascadea.
- **Kill-switch:** se saltea el tenant que está HALT (ya es per-tenant).

## 5. Decisiones (CONFIRMADAS 2026-06-07)

- **D1 ✅ Secuencial con aislamiento de errores.** Un proceso recorre los tenants
  activos, try/except por tenant. Migrable a procesos sin cambiar la interfaz.
- **D2 → default:** credenciales por tenant desde el vault; fallback al config
  global para el default tenant (preserva el bot single-user actual).
- **D3 → default:** construir la capa de orquestación ahora (con `cycle_fn`
  inyectable); el wire-up del ciclo real del bot va después/aparte.

## 6. Secuencia (sub-bloques)

| Sub-bloque | Qué |
|---|---|
| B6.1 | `load_broker_credentials(tenant_id)` (vault + fallback) + tests |
| B6.2 | `TenantWorker` (contexto aislado por tenant) + tests |
| B6.3 | `WorkerOrchestrator` (recorre activos, saltea HALT, error-isolado) + tests |
| B6.4 | Entry point / wire-up con el ciclo del bot + docs |

B6.1–B6.3 son buildeables y testeables sin tocar el loop de `main`.

## 7. Riesgos

| Riesgo | Mitigación |
|---|---|
| Un tenant rompe a los demás | try/except por tenant (D1 secuencial) o procesos (D1 multiproc) |
| Credenciales de un tenant filtradas a otro | cada worker carga SOLO las del tenant (vault, RLS) |
| Tenant en HALT igual opera | el orquestador saltea los que están en kill-switch |
| Reescribir el loop del bot (riesgoso) | se reusa `main` vía `cycle_fn`, no se reescribe |
