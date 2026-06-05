# PLAN — Börsenhirn SaaS

> Misión y decisiones de fondo del proyecto. Estado vivo: [ESTADO.md](ESTADO.md).
> Este doc **no duplica**: la arquitectura técnica de RLS vive en [`../MULTI_TENANCY.md`](../MULTI_TENANCY.md);
> el log cronológico bloque-por-bloque vive en [B1_SESSION_LOG.md](B1_SESSION_LOG.md);
> la auditoría de gaps en [`../AUDITORIA.md`](../AUDITORIA.md).

---

## La misión en una frase

**Convertir el trading bot Börsenhirn de single-user a multi-tenant a nivel de base de datos**,
para que cuando lleguen usuarios del SaaS, cada uno vea solo sus datos automáticamente —
sin filtrar query por query en el código.

Frase de cabecera del usuario: **"empezar a pensar como SaaS sin romper lo que ya funciona"**.

## Por qué

El bot se diseñó single-user: las 22 tablas asumían un único dueño. Con dos usuarios, sus
datos se mezclarían (trades, scores, credenciales de Alpaca). Como Börsenhirn se comercializa
como SaaS (**Modelo A — BYO Alpaca broker**), el aislamiento debe existir **antes** del primer
cliente pago. Es el bloqueador #1: sin multi-tenancy no hay Vault per-user (B2), ni auth con
sentido (B3), ni billing (B4).

## La decisión técnica central: Postgres Row-Level Security (RLS)

En vez de agregar `WHERE tenant_id = ?` a miles de queries (error-prone), se usa RLS nativo de
Postgres. Cada tabla tiene `tenant_id`; las policies filtran por la variable de sesión
`app.current_tenant_id`. El código solo setea el tenant al conectar; de ahí TODAS las queries
quedan filtradas. **Defensa en profundidad:** si nadie setea el tenant, las queries devuelven 0
filas (`FORCE ROW LEVEL SECURITY`). Es imposible que un usuario vea data de otro por un bug.

Detalle de arquitectura, roles y garantías: ver [`../MULTI_TENANCY.md`](../MULTI_TENANCY.md).

## La idea de fondo: *infrastructure now, scale later*

Post-B1, el bot funciona **idéntico** para el usuario actual (todo va al default tenant
`00000000-…001`). Pero la infra queda lista para que, al sumar Clerk (B3), cada usuario nuevo
reciba un UUID, el bot derive `tenant_id` del JWT, y RLS aísle automáticamente — **sin tocar
más la capa de persistencia**.

---

## Decisiones clave tomadas (las que no son obvias del código)

| # | Decisión | Por qué |
|---|---|---|
| D1 | **17 tablas a multi-tenant**, 4 legacy fuera | Tras inspect: 9 core + 5 reclasificadas de cat-D con datos vivos + 3 de cat-C que Fase A no migró. Las 4 legacy tenían 0 filas y 0 referencias. |
| D2 | **DROP en dev, RENAME `_legacy_*` en prod** | El dump es de un momento puntual; prod pudo escribir filas después. Archivar > borrar irreversible. |
| D3 | **Default tenant `…001` como dueño de las 128 filas legacy** | Backfill seguro; el bot single-user sigue operando sin auth hasta B3. Existe el sentinel `…000` (SYSTEM) reservado para data shared global futura (no es fila real). |
| D4 | **Rol `borsenhirn_app` NOSUPERUSER + NOBYPASSRLS** | Superusers bypassean RLS siempre. La app debe correr con rol no-privilegiado o las garantías son ficticias. Admin/migraciones/backups usan `postgres`. |
| D5 | **`tenant_id=None` por default en los 3 módulos refactoreados** | Backwards compat: protege `ks_admin.py`, `rotate_master_key.py` y 24+ tests que mockean, sin riesgo de regresión. |
| D6 | **GUC canónico `app.current_tenant_id`** (no `app.current_tenant`) | Alinear DB al módulo `tenancy/db.py` existente de Fase A. Bloque 4.5 dropeó+recreó las 34 policies con el nombre correcto. |
| D7 | **`SELECT`-only en `tenants` para el rol app** | El lifecycle de tenants (crear/suspender) es tarea admin, no runtime del bot. |
| D8 | **Cada migración: doble guard + idempotente + atómica** | bash chequea `DB_NAME`; SQL chequea `current_database()` con `RAISE EXCEPTION`. `BEGIN/COMMIT`, `ON_ERROR_STOP`, `IF NOT EXISTS`. |

---

## Roadmap SaaS — 10 bloqueadores

B1 es el cimiento; cada bloque desbloquea al siguiente.

| Bloque | Qué | Estado |
|---|---|---|
| **B1** | **Multi-tenancy (RLS)** | 🔨 ~90% — ver [ESTADO.md](ESTADO.md) |
| B2 | Vault (gestión de secrets por usuario) | pendiente |
| B3 | Auth (Clerk) — resuelve user → tenant_id desde JWT | pendiente |
| B4 | Stripe (billing) | pendiente |
| B5 | Audit log | pendiente |
| B6 | Worker isolation | pendiente |
| B7 | Legal | pendiente |
| B8 | Kill switch global | pendiente |
| B9 | Backups | pendiente |
| B10 | Anomaly detection | pendiente |

### Estructura interna de B1 (bloques -1 a 9)
-1 entorno · 0 dump→dev · 1 audit/categorización · 2 ADD COLUMN+FK+index ·
3 backfill+NOT NULL · 4/4.5 RLS policies+GUC · **5 refactor capa app (acá estoy)** ·
6 tests amplios · 7 bot e2e en dev · **8 aplicar a prod** · 9 docs final.
Cronología detallada: [B1_SESSION_LOG.md](B1_SESSION_LOG.md).

---

## Garantías que se mantienen durante todo el sprint

- Producción `borsenhirn` **nunca** se toca (hasta B8 consciente, con backup).
- pytest baseline **267 passed** verde en cada commit.
- Backwards compat: single-user dev funciona idéntico (default tenant automático).
- Cada migración SQL: idempotente, atómica, con doble guard anti-prod.

## "Misión cumplida" =

Tras el Bloque 8 (B1 aplicado a prod), el SaaS **técnicamente puede empezar a vender**.
Faltan B2–B10 para estar completo, pero B1 desbloquea todo lo demás.
