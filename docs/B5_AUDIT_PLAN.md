# B5 — Audit log · Plan (para revisar)

> Plan del bloqueador B5. Greenfield (no hay infra de audit). Estado: [ESTADO.md](ESTADO.md).

## 1. Objetivo y alcance

**Objetivo:** un **registro de auditoría append-only** de las acciones sensibles
del SaaS — quién hizo qué, sobre qué tenant, cuándo — para seguridad y
compliance (manejamos credenciales de broker y pagos).

| | |
|---|---|
| **IN scope** | Tabla `audit_log` (tenant-scoped + RLS), un módulo `audit` para registrar eventos, y hooks en los puntos sensibles (credenciales, billing, lifecycle de tenant, kill-switch). |
| **OUT scope** | UI de visualización (frontend). SIEM externo (futuro). |

## 2. Estado actual

- **Nada de audit.** Existe `user_credentials_audit` **comentada** en
  `security/migrations.sql` (semilla: action read/write/delete/rotate).
- `alerts_log` (RLS, jsonb meta) sirve de referencia de schema.
- Puntos auditables ya ubicados: `tenancy/management` (provision/suspend/disable/
  set_billing), `security/credentials` (set/get/delete), `safety/killswitch`
  (manual_halt/clear).

## 3. Schema (recomendado)

`audit_log` tenant-scoped con RLS:

```
id            bigserial PK
tenant_id     uuid NOT NULL  (FK tenants, RLS)
actor         text NOT NULL  -- 'system' | 'admin' | clerk_user_id
action        text NOT NULL  -- 'credentials.read', 'billing.updated', 'tenant.suspended', ...
resource      text           -- opcional (p.ej. provider, subscription_id)
at            timestamptz NOT NULL DEFAULT now()
metadata      jsonb NOT NULL DEFAULT '{}'
```
Index `(tenant_id, at DESC)`. RLS igual que las 17 tablas A.

## 4. Append-only (decisión D1)

**Recomendado:** el rol `borsenhirn_app` recibe **solo INSERT + SELECT** en
`audit_log` (sin UPDATE ni DELETE). Así el runtime no puede alterar ni borrar el
historial → tamper-resistant por permisos. (Tamper-*evidence* con hash-chain
queda como mejora futura, no MVP.)

## 5. Módulo `borsenhirn/audit`

```
AuditLogger.record(tenant_id, actor, action, *, resource=None, metadata=None)
  -> INSERT en audit_log (vía bdb.get_conn('app') + set_tenant)
get_audit_logger()  -> singleton (inyectable/desactivable en tests)
```
- Falla "blanda": un error al auditar **no debe romper la operación principal**
  (loggea WARNING). Excepción: acciones donde el audit es crítico (a decidir).
- Helpers de acción: `audit_credentials(...)`, `audit_billing(...)`, etc.

## 6. Qué auditar primero (decisión D2)

Candidatos (todos sensibles):
- **Credenciales:** read/write/delete/rotate de claves de broker.
- **Billing:** cambios de suscripción/estado (desde el webhook).
- **Tenant lifecycle:** provision / suspend / disable / reactivate.
- **Kill-switch:** manual_halt / clear.

## 7. Decisiones (CONFIRMADAS 2026-06-07)

- **D1 ✅ append-only por permisos.** Rol app: INSERT+SELECT en `audit_log`; sin UPDATE/DELETE.
- **D2 ✅ las 4 categorías:** credenciales, billing, lifecycle de tenant, kill-switch.
- **D3 → default:** solo append-only en MVP; hash-chain (tamper-evidence) queda futuro.
- **D4 → default:** el fallo al auditar NUNCA rompe la operación principal (WARNING).

## 8. Secuencia (sub-bloques)

| Sub-bloque | Qué |
|---|---|
| B5.1 | Schema `audit_log` + RLS + grants append-only (dev) |
| B5.2 | Módulo `borsenhirn/audit` (`AuditLogger` + helpers) + tests |
| B5.3 | Hooks en los puntos sensibles (según D2) + tests |
| B5.4 | Endpoint `GET /me/audit` (lista el audit del tenant) + docs |

B5.1–B5.4 son todos buildeables sin dependencias externas.

## 9. Riesgos

| Riesgo | Mitigación |
|---|---|
| Auditar rompe la operación principal | fallo blando (WARNING), no propaga (D4) |
| El runtime borra/edita el log | grants append-only (D1) |
| Fugas de datos sensibles en metadata | NUNCA guardar plaintext de secretos en metadata |
| Volumen | index por (tenant, at); retención/archivado es futuro |
