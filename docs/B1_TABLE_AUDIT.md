# B1 Table Audit - 2026-04-26 (FINAL post inspect)

**DB auditada:** `borsenhirn_dev`@`172.25.144.1`
**Generado por:** `scripts/b1_block1_audit.sh` (inicial)
**Refinado por:** `scripts/b1_block1_inspect_unknown.sh` + decision manual de Uriel

## Categorias

- **A** = Tabla legacy del bot. Necesita `tenant_id` + RLS en bloques 2-4.
- **B** = Shared global. NO lleva `tenant_id` por diseno.
- **DROP_DEV** = Legacy duplicada (0 filas + 0 usos en codigo). Drop en `borsenhirn_dev`. En produccion se renombra a `_legacy_*` para revision manual antes de borrar definitivo.

## Decision final post-inspect

| CAT | Tabla | Rows (dev) | Decision | Justificacion |
|-----|-------|-----------:|----------|---------------|
| A | `bot_daily_state` | - | migrar | core bot state |
| A | `bot_entry_context` | - | migrar | core bot state |
| A | `bot_entry_prices` | - | migrar | core bot state |
| A | `bot_ml_metrics` | - | migrar | ML observability |
| A | `bot_ml_training` | 4 | migrar | ML training history |
| A | `bot_performance` | - | migrar | metrics |
| A | `bot_regime_stats` | - | migrar | regime detector |
| A | `bot_symbol_scores` | 21 | migrar | scoring activo |
| A | `bot_trade_outcomes` | 31 | migrar | paper trading data |
| A | `assistant_history` | 12 | migrar | M5 Hirn historial; backfill -> default |
| A | `assistant_suggestions` | 1 | migrar | M5 Hirn suggestions; backfill -> default |
| A | `daily_reports` | 0 | migrar | feature activo |
| A | `signals` | 0 | migrar | feature futuro |
| A | `trades` | 0 | migrar | usado por `tenancy/db.py` (demo) |
| A | `alerts_log` | 3 | migrar | reclasificada de C: foundation no llego a migrarla; backfill -> default |
| A | `killswitch_state` | 0 | migrar | reclasificada de C: idem |
| A | `user_credentials` | 0 | migrar | reclasificada de C: idem |
| B | `tenants` | - | NO TOCAR | shared (es la tabla destino del FK) |
| DROP_DEV | `bot_state` | 0 | DROP | legacy duplicada de `bot_daily_state`; 0 usos en codigo |
| DROP_DEV | `entry_context` | 0 | DROP | legacy duplicada de `bot_entry_context`; 0 usos en codigo |
| DROP_DEV | `regime_stats` | 0 | DROP | legacy duplicada de `bot_regime_stats`; 0 usos en codigo |
| DROP_DEV | `symbol_memory` | 0 | DROP | legacy duplicada de `bot_symbol_scores`; 0 usos en codigo |

## Listas finales (para uso en scripts)

```python
TABLAS_A = [
    # Core bot (ya estaban en whitelist)
    "bot_daily_state", "bot_entry_context", "bot_entry_prices",
    "bot_ml_metrics", "bot_ml_training", "bot_performance",
    "bot_regime_stats", "bot_symbol_scores", "bot_trade_outcomes",
    # M5 Hirn + reportes + features
    "assistant_history", "assistant_suggestions", "daily_reports",
    "signals", "trades",
    # Reclasificadas desde cat-C (foundation pero sin migrar)
    "alerts_log", "killswitch_state", "user_credentials",
]
# Total: 17 tablas

TABLAS_DROP_EN_DEV = [
    "bot_state", "entry_context", "regime_stats", "symbol_memory",
]
# Total: 4 tablas

TABLAS_NO_TOCAR = [
    "tenants",  # destino del FK; ya tiene su lugar
]
```

## Politica de DROP en produccion

Las 4 tablas de `TABLAS_DROP_EN_DEV` **NO** se dropean en `borsenhirn` durante
el Bloque 8. En su lugar, el script de produccion las **renombra** a
`_legacy_<nombre>` (por ejemplo `_legacy_bot_state`) para que Uriel pueda
revisarlas manualmente con `psql` antes de borrar definitivo en una ventana
de mantenimiento posterior.

Razon: en produccion podria haber datos historicos que el inspector de dev
no detecta (la copia es del momento del dump, las tablas pueden haberse
escrito despues). Mejor archivar que borrar irreversiblemente.

## Trazabilidad

- Inspector script: `scripts/b1_block1_inspect_unknown.sh`
- Inspector output: `docs/B1_TABLE_INSPECT.md`
- Decision logged en: `docs/B1_SESSION_LOG.md` (entrada Bloque 1 - CERRADO)

## Proximo paso

Bloque 2: `scripts/b1_block2_migration.sql` aplica:
1. INSERT del default tenant (UUID fijo) en `tenants`.
2. DROP de las 4 legacy en `borsenhirn_dev`.
3. ADD COLUMN `tenant_id UUID` (NULL temporal) en las 17 tablas A.
4. FK a `tenants(id)` en cada una.
5. INDEX en `tenant_id`.

Backfill + `NOT NULL` van en Bloque 3. RLS policies en Bloque 4.
