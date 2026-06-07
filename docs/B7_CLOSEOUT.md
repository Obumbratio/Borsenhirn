# B7 — Cierre (Legal: aceptación + gating)

> Síntesis. Plan/decisiones → [B7_LEGAL_PLAN.md](B7_LEGAL_PLAN.md). Estado: [ESTADO.md](ESTADO.md).

## Resultado en una frase

Cada tenant debe **aceptar la versión vigente de Términos y Privacidad** para usar
el producto; la aceptación queda registrada de forma **append-only** (versión +
timestamp + actor + ip) y el acceso a endpoints de producto se **gatea con 451**
hasta que acepte.

## Qué se entregó

| Sub-bloque | Resultado |
|---|---|
| B7.1 | Tabla `legal_acceptance` (tenant-scoped + RLS + **append-only**) + versiones vigentes en `config` (`LEGAL_TERMS_VERSION`, `LEGAL_PRIVACY_VERSION`). |
| B7.2 | `borsenhirn/legal/`: `record_acceptance`, `is_compliant`, `current_versions`, `get_acceptances`. |
| B7.3 | Endpoints `GET /legal/current` (público), `POST /me/legal/accept`, `GET /me/legal`; gating `get_compliant_tenant` (451) en `/me/trades/count`. |

## Diseño (claves)

- **Versionado en config**: al cambiar un doc se bumpea la versión → `is_compliant`
  falla → re-aceptación forzada.
- **Append-only** (como `audit_log`): registro no alterable por el runtime.
- **Gating componible**: `get_compliant_tenant` = activo (billing) + compliant
  (legal). `/legal/*` y billing nunca se gatean (para poder aceptar/pagar).

## Métricas

- **Tests:** 6 (4 unit + 2 e2e). Baseline **368 → 372 passed**.
- **Suite de integración completa: 35 passed** (B1 RLS + B3/B4/B5/B6/B7 e2e).
- De paso: arreglados los cleanups e2e que fallaban por FK (el hook de audit de
  B5 crea una fila `audit_log` al provisionar → el teardown ahora borra los child
  rows antes del tenant).

## Lo que queda (fuera del backend)

1. **Contenido legal** revisado por un abogado (los `legal/*.md` son drafts).
2. **UI**: modal de aceptación en el frontend (consume `/legal/*`).
3. **Migración `legal_acceptance` a prod** (con el flujo de B8).

## Para CV / portfolio

> "Compliance legal en SaaS: aceptación versionada de Términos/Privacidad con
> registro append-only (versión + timestamp + actor), gating de acceso por
> aceptación (HTTP 451), re-aceptación forzada al cambiar de versión — sobre el
> aislamiento multi-tenant (RLS) existente."
