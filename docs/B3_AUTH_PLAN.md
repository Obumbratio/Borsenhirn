# B3 — Auth con Clerk · Plan (para revisar)

> Plan del bloqueador B3 del roadmap SaaS. Documento para revisar **antes** de
> tocar código. Cierra el "resolve user → tenant_id" que B1 dejó como TODO en
> `borsenhirn/api/main.py` y en la checklist Fase B de `MULTI_TENANCY.md`.
> Estado vivo: [ESTADO.md](ESTADO.md).

## Decisiones ya tomadas (2026-06-05)
- **Modelo: 1 usuario Clerk = 1 tenant.** Provisión lazy en el primer login;
  mapeo por `clerk_user_id`.
- **Enfoque: plan primero** (este doc), luego implementación por sub-bloques.

## 1. Objetivo y alcance

**Objetivo:** que la API verifique el JWT de Clerk, resuelva el tenant del
usuario, y **inyecte el `tenant_id`** para que toda query corra bajo el RLS
correcto (multi-tenancy de B1 aplicada por-request).

| | |
|---|---|
| **IN scope** | Backend (FastAPI): verificación JWT, resolución/provisión de tenant, dependency que setea el RLS context, proteger endpoints tenant-scoped. |
| **OUT scope** | Frontend Next.js (no existe en este repo — esfuerzo separado). El plan asume que el cliente manda `Authorization: Bearer <jwt de Clerk>`. |

## 2. Estado actual

- API mínima (`borsenhirn/api/main.py`): `/`, `/status`, `/signal`, `/health`.
  **Sin auth.** `/signal` cachea a Redis, todavía no toca tablas con RLS.
- `tenants`: PK `tenant_id`, tiene `email`/`slug`/`status`; **no** tiene
  `clerk_user_id`.
- `TenantManager`: `create_tenant`, `get_tenant`, `get_tenant_by_email/slug`,
  lifecycle. **Falta** `get_tenant_by_clerk_id`.
- **PyJWT no instalado** (sí `cryptography`, `httpx`).

## 3. Modelo identidad → tenant (1:1)

- `tenants` gana **`clerk_user_id text UNIQUE`** (nullable; system/default lo
  tienen NULL).
- **Provisión lazy:** primer request autenticado sin tenant para ese
  `clerk_user_id` → `TenantManager.create_tenant(email, display_name,
  metadata={"clerk_user_id": ...})` + set `clerk_user_id`. Idempotente: la
  unique constraint resuelve la race de dos requests simultáneos.

## 4. Flujo de verificación (por request)

1. Cliente: `Authorization: Bearer <jwt>` (session token o JWT template de Clerk).
2. Backend obtiene el **JWKS** de Clerk (cacheado, refresh por `kid` desconocido).
3. Verifica firma **RS256** + claims: `exp`, `nbf`, `iss` (= tu issuer de Clerk),
   opcional `azp`/`aud`.
4. Extrae `sub` (Clerk user id) + email/nombre (si están en el token template).
5. `resolve_or_provision_tenant(claims)` → `tenant_id`.
6. `set_tenant(conn, tenant_id)` para las queries de esa request.

## 5. Diseño (pluggable, testeable sin Clerk vivo)

Mismo patrón que los secret providers de B2: una abstracción + implementaciones
intercambiables, para poder testear sin un Clerk real.

```
TokenVerifier (protocol):  verify(token: str) -> Claims
  ├─ ClerkJWKSVerifier   — real: JWKS + RS256 + validación de claims
  └─ StaticTokenVerifier — dev/tests: verifica con una key/HS o un mapping fijo

resolve_or_provision_tenant(claims) -> tenant_id   (usa TenantManager, pool admin)

get_current_tenant(request) -> str                 (FastAPI Depends; ata todo;
                                                    cachea el resultado por request)
```

- Config por env: `AUTH_VERIFIER` (clerk|dev), `CLERK_ISSUER`, `CLERK_JWKS_URL`,
  `CLERK_AUDIENCE` (opcional).
- La dependency setea el RLS context para los handlers que tocan tablas tenant.

## 6. Cambios concretos

- **Schema:** migración idempotente `ALTER TABLE tenants ADD COLUMN
  clerk_user_id text UNIQUE` (dev primero; prod junto con B1 Bloque 8 o aparte).
- **`borsenhirn/auth/`** (módulo nuevo): `verifier.py` (TokenVerifier + impls),
  `tenant_resolver.py` (resolve_or_provision), `deps.py` (FastAPI dependency).
- **`TenantManager.get_tenant_by_clerk_id`** + helper de provisión.
- **`api/main.py`:** proteger los endpoints tenant-scoped con `Depends(get_current_tenant)`.
- **Dependencia:** agregar **`pyjwt[crypto]`** a `requirements.in` (recomendado;
  liviano + `PyJWKClient` para JWKS). Alternativa: SDK oficial `clerk-backend-api`.

## 7. Config de Clerk que necesito de vos (para B3.3, la parte real)

- App de Clerk creada.
- **Issuer** / Frontend API URL y **JWKS URL** (`https://<...>/.well-known/jwks.json`).
- (Opcional) **JWT template** con `email` y nombre en los claims (evita un fetch
  extra al Backend API en la provisión).
- Publishable key (frontend) + Secret key (solo si usamos Backend API / SDK).

## 8. Testing (sin Clerk vivo)

- `StaticTokenVerifier` + JWTs firmados con una RSA key generada en el test →
  flujo completo: token válido → tenant resuelto/provisionado → RLS context OK.
- Casos: provisión idempotente, token expirado/inválido/firma mala → 401,
  request sin Authorization → 401.
- (Real) `ClerkJWKSVerifier` contra un JWKS mockeado (httpx) — sin red.

## 9. Decisiones a confirmar antes de implementar

- **D1:** lib JWT → `pyjwt[crypto]` (recomendado) vs SDK `clerk-backend-api`.
- **D2:** `user_credentials.user_id` → ¿= `tenant_id` (1:1) o se mantiene separado?
- **D3:** email/nombre del usuario → ¿vía JWT template de Clerk (recomendado) o
  fetch al Backend API de Clerk en la provisión?
- **D4:** qué endpoints se protegen ahora (¿`/signal`? ¿endpoints nuevos
  tenant-scoped? ¿`/status` queda público?).
- **D5:** provisión **lazy** (primer request, recomendado MVP) vs **webhook**
  de Clerk (`user.created`).

## 10. Secuencia de implementación (sub-bloques)

| Sub-bloque | Qué | Depende de |
|---|---|---|
| B3.1 | Schema `clerk_user_id` + `get_tenant_by_clerk_id` + provisión (dev) | — |
| B3.2 | `TokenVerifier` + `StaticTokenVerifier` + tests | B3.1 |
| B3.3 | `ClerkJWKSVerifier` real + config env | config Clerk (vos) |
| B3.4 | FastAPI `get_current_tenant` + proteger endpoints + RLS context | B3.2 |
| B3.5 | Docs de cierre + (futuro) frontend Next.js | — |

B3.1, B3.2 y B3.4 (con el verifier dev) se pueden construir y testear **ya**, sin
tu cuenta Clerk. Solo B3.3 necesita los specifics de Clerk.

## 11. Riesgos

| Riesgo | Mitigación |
|---|---|
| Sin frontend, no hay flujo real end-to-end hasta que un cliente emita el JWT | StaticTokenVerifier + tokens de test cubren el backend; B3.3 se valida con JWKS mockeado |
| Confiar en claims sin verificar firma | la dependency SIEMPRE verifica firma+exp+iss antes de usar `sub` |
| Race en provisión (2 requests del mismo user nuevo) | `clerk_user_id UNIQUE` + catch → re-lookup |
| Rotación de JWKS de Clerk | cache con refresh ante `kid` desconocido |
| Aplicar el schema a prod | va con el flujo de B1 Bloque 8 o como migración aparte, mismo cuidado |
