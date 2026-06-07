# B1 — Cierre del Sprint (multi-tenancy Phase B)

> Síntesis de resultados del sprint. No repite: misión/decisiones en
> [PLAN.md](PLAN.md) · capa de app en [B1_APP_LAYER.md](B1_APP_LAYER.md) ·
> cronología bloque-por-bloque en [B1_SESSION_LOG.md](B1_SESSION_LOG.md) ·
> aplicación a prod en [B1_BLOCK8_PLAN.md](B1_BLOCK8_PLAN.md).

## Resultado en una frase

El bot Börsenhirn pasó de single-user a **multi-tenant a nivel de base de
datos** con Postgres RLS: cada query queda aislada por `tenant_id`
automáticamente, es imposible que un usuario vea data de otro, y el bot
single-user actual sigue funcionando idéntico. **Probado end-to-end en
`borsenhirn_dev`; listo para aplicar a producción** (Bloque 8 generado, pendiente
de ejecutar en ventana).

## Qué se entregó (por bloque)

| Bloque | Resultado |
|---|---|
| -1, 0 | Entorno WSL↔Postgres operativo; copia `borsenhirn_dev` de prod. |
| 1 | 22 tablas auditadas → 17 a multi-tenant, 4 legacy a archivar, `tenants` exenta. |
| 2–3 | `tenant_id` NOT NULL + FK `ON DELETE RESTRICT` + index en 17 tablas; 128 filas backfilled al default tenant. |
| 4–4.5 | RLS `ENABLE`+`FORCE` + 2 policies/tabla; GUC unificado `app.current_tenant_id`. |
| 5 | Capa de app: `borsenhirn/db.py` (pools app/admin, tenant context), refactor de los 3 módulos de persistencia, wire-up de `main.py`/`bootstrap`/`api`. Rol `borsenhirn_app` (NOSUPERUSER+NOBYPASSRLS). |
| 6 | Tests amplios de aislamiento (WITH CHECK, FK RESTRICT, 2 tenants, cobertura 17/17). |
| 7 | Bot e2e (capa DB) → **destapó y arregló 2 bugs** (ver abajo). |
| 8 | 6 scripts de aplicación a prod (consolidada + rol + backup + verify + rollback), validados; **sin ejecutar**. |
| 9 | Este cierre. |

## Estado físico final

- **`borsenhirn_dev`:** estado multi-tenant production-grade. 17 tablas con RLS
  forzado, default tenant dueño de las 128 filas legacy, rol app funcionando.
- **Código:** persistencia 100% vía `borsenhirn/db.py` con tenant context;
  backwards-compat preservada (`tenant_id=None` para callers admin).
- **Producción `borsenhirn`:** **intacta**. Scripts listos para migrarla.

## Los 2 bugs que sólo el e2e (B7) podía encontrar

1. **INSERT sin `tenant_id`** — los ~17 INSERT de los 3 módulos refactoreados no
   incluían la columna; RLS WITH CHECK los rechazaba. Reads OK, writes rotas.
   Fix: `DEFAULT` de `tenant_id` desde el GUC de sesión en las 17 tablas.
2. **Pool-leak en la safety stack** — `PostgresStateStore` no devolvía las conns
   al pool; `is_halted()` por iteración agotaba el pool (~10 vueltas) y crasheaba
   el bot. Fix: helper `_acquire` que recicla la conn vía context manager.

Ambos invisibles para los unit tests (mockean la DB). Lección reforzada: **un
e2e real contra la DB encuentra lo que los mocks ocultan.**

## Métricas

- **18 commits** en `feature/multi-tenancy-phase-b` (8 esta sesión).
- **pytest:** 267 passed (baseline, mantenido en todos los commits) + **16 tests
  de integración** RLS (gated por `RUN_DB_INTEGRATION`, dev-only).
- **~1.6k líneas de SQL** (migraciones + scripts admin), 3 archivos de tests B1
  (~514 líneas), 8 docs B1.
- `check_rls_coverage --strict`: 17/17 con RLS, 0 sin RLS.

## Garantías cumplidas

- Producción nunca se tocó. Cada migración: idempotente, atómica, doble guard.
- Baseline de tests verde en cada commit. Single-user dev funciona idéntico.

## Lecciones

Las transversales (patrón RLS, gotchas psql, WSL↔Postgres, workflow IA) se
guardaron en el vault de conocimiento. Específicas del sprint: ver "Lecciones" en
el [session log](B1_SESSION_LOG.md) y los 2 bugs de arriba.

## Lo que queda

1. **Ejecutar Bloque 8** en prod (backup → apply → rol → verify → re-arranque).
   Es lo único entre "dev-complete" y "misión cumplida".
2. **Roadmap SaaS:** B2 Vault → B3 Auth (Clerk; recién acá el `tenant_id` sale
   del JWT del usuario) → B4 Stripe → B5..B10. B1 es el cimiento que los desbloquea.

## Cabos menores (no bloqueantes)

- Comentario en `borsenhirn/tenancy/constants.py` dice que el tenant SYSTEM `…000`
  no existe como fila, pero la migración de Fase A sí lo creó. Aclarar comentario.
- `TESTS.md` typo de path: ya estaba corregido (verificado en AUDITORIA R-2).

## Para CV / portfolio

> "Migré un trading bot de single-user a multi-tenant SaaS con Postgres
> Row-Level Security: aislamiento garantizado a nivel de DB (FORCE RLS + policies
> WITH CHECK), rol de aplicación sin privilegios, capa de conexiones con tenant
> context, migración idempotente/atómica con backfill seguro y rename-no-drop de
> legacy, 16 tests de integración de aislamiento (INSERT/UPDATE cross-tenant,
> FK RESTRICT, 2-tenant) + e2e que destapó 2 bugs latentes que los mocks ocultaban."
