# B5 — Cierre (Audit log)

> Síntesis. Diseño/decisiones → [B5_AUDIT_PLAN.md](B5_AUDIT_PLAN.md). Estado: [ESTADO.md](ESTADO.md).

## Resultado en una frase

Hay un **registro de auditoría append-only y tenant-scoped** (`audit_log`, RLS):
las acciones sensibles (credenciales, billing, lifecycle de tenant, kill-switch)
quedan registradas con quién/qué/cuándo, el runtime **no puede alterarlas** (solo
INSERT+SELECT), y cada tenant ve su propia traza vía `GET /me/audit`.

## Qué se entregó

| Sub-bloque | Resultado |
|---|---|
| B5.1 | Tabla `audit_log` (tenant-scoped + RLS + DEFAULT del GUC); **append-only por permisos** (app role: INSERT+SELECT, sin UPDATE/DELETE). 18/18 tablas con RLS. |
| B5.2 | `borsenhirn/audit/`: `AuditLogger.record` (insert vía app pool + set_tenant), actor por contextvar (default 'system'), **soft-fail** (auditar nunca rompe la op), `AuditAction`. |
| B5.3 | Hooks (lazy + soft-fail) en credenciales (set/get/delete), billing (webhook, actor='stripe'), lifecycle de tenant (provision/suspend/disable/reactivate), kill-switch (halt/clear). Actor seteado por la auth dependency. |
| B5.4 | Endpoint `GET /me/audit` (la traza del tenant, bajo RLS). |

## Diseño (claves)

- **Append-only por permisos** (no por triggers): simple y fuerte. Tamper-
  *evidence* (hash-chain) queda como futuro.
- **Soft-fail**: un error al auditar loggea WARNING y no propaga — la operación
  principal nunca se rompe (decisión D4).
- **Actor por contextvar**: la auth dependency setea el `clerk_user_id`; los
  eventos de sistema (webhooks/jobs) quedan 'system'/'stripe'.
- **Hooks lazy** (import dentro del método): sin riesgo de ciclos de import.

## Métricas

- **Tests:** 12 nuevos (logger 4, hooks 3, audit e2e 3, endpoint e2e 2) →
  baseline **354 → 361 passed**. Los 60 tests de los módulos hookeados intactos.
- Producción intacta; verificado contra `borsenhirn_dev`.

## Lo que queda (fuera del backend)

1. **Migración `audit_log` a prod** (con el flujo de B8; incluye los grants
   append-only al rol app de prod).
2. **UI** de visualización del audit (frontend).
3. **Futuro:** hash-chain (tamper-evidence), retención/archivado, export a SIEM.

## Para CV / portfolio

> "Audit log append-only multi-tenant: tabla con RLS y permisos INSERT+SELECT
> (sin UPDATE/DELETE para el rol de runtime → tamper-resistant), logging
> best-effort que nunca rompe la operación, actor por contextvar desde la capa de
> auth, y hooks en las acciones sensibles (credenciales, pagos, lifecycle,
> kill-switch)."
