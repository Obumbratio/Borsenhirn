# B8 — Cierre (Kill switch)

> Nota de numeración: este es el **Roadmap B8 = Kill switch**, distinto del
> "B1 Bloque 8" (aplicar la multi-tenancy a prod, pendiente). Estado: [ESTADO.md](ESTADO.md).

## Resultado en una frase

Hay **kill-switch por tenant** (manual + automático por daily-loss/drawdown/
fallos consecutivos, ya existente) **y un kill-switch GLOBAL de plataforma**
(freno de emergencia para todos los tenants), respetado por el orquestador de
workers y controlable por un endpoint admin.

## Qué se entregó

| Pieza | Estado |
|---|---|
| Kill-switch **per-tenant** | ✅ ya existía (`KillSwitch`/`PostgresStateStore`, tenant-scoped; B5 lo audita, B6 lo respeta). |
| Kill-switch **global** | ✅ `borsenhirn/safety/global_killswitch.py` (`is_global_halt`/`trip_global`/`clear_global`) sobre el tenant SYSTEM. Auditado. |
| Integración con workers | ✅ `WorkerOrchestrator.run_once` no corre ningún tenant si el global está activo (`global_halt_check` inyectable, fail-open ante error de chequeo). |
| Control admin | ✅ `GET/POST /admin/killswitch/global` + `/clear`, auth por `X-Admin-Key` = `config.ADMIN_API_KEY` (vacío = admin deshabilitada). |

## Diseño (claves)

- **Global = tenant SYSTEM**: reusa la infra del kill-switch existente (una fila
  de `killswitch_state` bajo `…000`), sin tabla nueva.
- **Fail-open en el chequeo**: si no se puede consultar el estado global, se
  continúa (un error de DB no frena toda la plataforma; la safety per-tenant sigue).
- **Admin por API key** (MVP): suficiente hasta tener auth admin completa.

## Métricas

- **Tests:** 6 (4 unit + 2 e2e). Baseline **372 → 376 passed**. Integración **37 passed**.

## Lo que queda (fuera de scope)

1. Auth admin completa (hoy: API key) y/o panel de ops.
2. Migración a prod va con "B1 Bloque 8" (el kill-switch usa `killswitch_state`,
   ya entre las 17 tablas A).

## Para CV / portfolio

> "Kill-switch multi-tenant: freno automático por tenant (daily-loss/drawdown/
> fallos) + freno global de plataforma respetado por la orquestación de workers,
> auditado y controlable por API admin."
