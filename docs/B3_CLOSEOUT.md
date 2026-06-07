# B3 — Cierre (Auth con Clerk, backend)

> Síntesis del bloqueador B3. No repite el diseño/decisiones → ver
> [B3_AUTH_PLAN.md](B3_AUTH_PLAN.md). Estado vivo: [ESTADO.md](ESTADO.md).

## Resultado en una frase

El backend ahora **autentica con JWT de Clerk y aísla por tenant**: un request
con `Authorization: Bearer <jwt>` se verifica (firma + exp + issuer), se resuelve
(o provisiona 1:1) el tenant del usuario, y los handlers corren sus queries bajo
el RLS context de ese tenant. **Backend completo y testeado**; falta solo poner
los valores reales de Clerk en prod y el frontend (esfuerzo aparte).

## Qué se entregó

| Sub-bloque | Resultado |
|---|---|
| B3.1 | `tenants.clerk_user_id` (UNIQUE) + `provision_for_clerk_user` (lazy, race-safe, sin huérfanos). |
| B3.2 | `borsenhirn/auth/`: `Claims`, `AuthError`, `TokenVerifier` (protocol), `StaticTokenVerifier` (HS256, dev/tests). |
| B3.3 | `ClerkJWKSVerifier` (RS256 + JWKS de Clerk) + `build_verifier_from_env()` (factory por env). |
| B3.4 | `get_current_tenant` (FastAPI dep) + endpoints `/me`, `/me/trades/count`. |

## Diseño (claves)

- **Verifier pluggable** (mismo patrón que los secret providers de B2): real
  (Clerk JWKS) o dev (HS256), elegido por `AUTH_VERIFIER`. Testeable sin Clerk
  vivo (JWKS mockeado / tokens HS256 propios).
- **Modelo 1 usuario Clerk = 1 tenant**, provisión **lazy** en el primer request
  (`clerk_user_id` UNIQUE hace la race segura). `user_id = tenant_id`.
- **Sin pool-leak**: la conn admin de provisión va por `bdb.get_conn` (fix B7).
- **Inyectable**: `get_verifier`/`get_tenant_manager` se overridean en tests.

## Métricas

- **Tests:** 16 nuevos de auth (verifier static 11, clerk 10, deps 6, e2e 3 →
  + tenancy provision 3). Baseline **267 → 320 passed**.
- **Dep nueva:** `pyjwt[crypto]==2.10.1` (en requirements.in + lockfile).
- Producción intacta; todo testeado contra `borsenhirn_dev`.

## Cómo activar Clerk real (prod)

Solo configuración — el código ya está:
```
AUTH_VERIFIER=clerk
CLERK_ISSUER=https://<tu-app>.clerk.accounts.dev
CLERK_JWKS_URL=https://<tu-frontend-api>/.well-known/jwks.json
CLERK_AUDIENCE=        # opcional
```
(Aplicar la migración `b3_block1_clerk_id` a prod junto con/después de B1 Bloque 8.)

## Lo que queda (fuera del backend)

1. **Frontend Next.js + Clerk** — no existe en este repo; emite el JWT que el
   backend ya sabe verificar.
2. **Migración `clerk_user_id` a prod** (con el flujo de B8).
3. **`api/main.py` importa redis+sqlalchemy** (subsistemas `core/*`) → para
   correr la API hay que tenerlas instaladas (no están en el venv dev). Los
   endpoints `/me` en sí solo usan psycopg2/bdb.

## Cabos de B2 que B3 desbloquea

- **`user_id = tenant_id`** (D2) ya decidido → el modelo de credenciales de B2
  queda cerrado conceptualmente.
- Envelope encryption per-tenant sigue siendo opcional (no bloqueante).

## Para CV / portfolio

> "Auth multi-tenant para SaaS: verificación de JWT de Clerk (RS256 + JWKS) con
> verifier pluggable y testeable sin el IdP vivo, provisión lazy de tenant 1:1
> race-safe, y dependency de FastAPI que inyecta el tenant en el RLS context por
> request — el aislamiento de Postgres (RLS) aplicado automáticamente a cada
> llamada autenticada."
