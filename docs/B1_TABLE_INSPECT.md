# B1 Sprint - Inspect cat-D Unknown Tables

Generated: 2026-04-26 22:43:25 UTC
Database: `borsenhirn_dev` @ `172.25.144.1:5432`
Tables inspected: 9

Each section reports for one table:
1. Exact row count (`SELECT count(*)`)
2. Columns + types (information_schema)
3. Timestamp/date range (if any timestamp-like column)
4. Sample 2 rows (most recent first if a timestamp exists)
5. Outgoing foreign keys
6. Code usage (grep over main.py + bot_memory_pg.py + borsenhirn/ + scripts/ + tests/)

**Recommendation** is left empty - Claude fills it after reviewing this report.

---

## `assistant_history`

### 1. Row count

```
12
```

### 2. Columns

```
 column_name |        data_type         | is_nullable 
-------------+--------------------------+-------------
 id          | integer                  | NO
 role        | character varying        | NO
 content     | text                     | NO
 created_at  | timestamp with time zone | YES
(4 rows)

```

### 3. Timestamp range (column: `created_at`)

```
            min_ts             |            max_ts             
-------------------------------+-------------------------------
 2026-03-26 13:59:55.312489-07 | 2026-04-26 10:38:21.343993-07
(1 row)

```

### 4. Sample (2 rows)

```
 id |   role    |                                                                                          content                                                                                           |          created_at           
----+-----------+--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+-------------------------------
 12 | assistant | ## Análisis Actualizado - Börsenhirn                                                                                                                                                      +| 2026-04-26 10:38:21.343993-07
    |           |                                                                                                                                                                                           +| 
    |           | ### (1) Salud del portafolio                                                                                                                                                              +| 
    |           | **Estado: SALUDABLE** — $107.9K equity con $139.7K buying power. Sistema operativo con datos de mercado funcionando correctamente (régimen BULL 75%, VIX 18.7).                           +| 
    |           |                                                                                                                                                                                           +| 
    |           | ### (2) Performance destacable                                                                                                                                                            +| 
    |           | **Sistema recién inicializado** — 0 trades históricos sugiere configuración nueva o reset completo. El equity de $107.9K indica capital inicial asignado correctamente para paper trading.+| 
    |           |                                                                                                                                                                                           +| 
    |           | ### (3) Sugerencia concreta                                                                                                                                                               +| 
    |           | **Momento óptimo para iniciar**: Las condiciones son ideales:                                                                                                                             +| 
    |           | - Régimen BULL confirmado (75% confianza)                                                                                                                                                 +| 
    |           | - VIX en 18.7 = volatilidad moderada/normal                                                                                                                                               +| 
    |           | - SPY en tendencia UP                                                                                                                                                                     +| 
    |           |                                                                                                                                                                                           +| 
    |           | **Estrategia recomendada**: Iniciar con position sizing conservador (2-3% = $2,000-3,000 por trade) para generar historial y calibrar los módulos M1-M4.                                  +| 
    |           |                                                                                                                                                                                           +| 
    |           | ### (4) Puntos de atención                                                                                                                                                                +| 
    |           | ✅ **Feeds de datos restaurados** (vs. el problema anterior de VIX 0.0)                                                                                                                   +| 
    |           | ⚠️ **Sin historial de referencia** — Los primeros trades serán críticos para establecer baselines                                                                                          +| 
    |           | 📊 **Cash allocation**: 29% en cash ($31.8K) permite flexibilidad para oportunidades                                                                                                      +| 
    |           |                                                                                                                                                                                           +| 
    |           | ---                                                                                                                                                                                       +| 
    |           |                                                                                                                                                                                           +| 
    |           | **Veredicto**: Sistema listo para operar. Régimen BULL + VIX normal = condiciones favorables para trading activo.                                                                         +| 
    |           |                                                                                                                                                                                           +| 
    |           | ¿Quieres que evalúe oportunidades específicas en el mercado actual, o prefieres configurar parámetros antes de iniciar?                                                                    | 
 11 | user      | /analisis                                                                                                                                                                                  | 2026-04-26 10:38:21.268918-07
(2 rows)

```

### 5. Outgoing foreign keys

```
 constraint_name | local_column | foreign_table | foreign_column 
-----------------+--------------+---------------+----------------
(0 rows)

```

### 6. Code usage (grep)

```
(no SQL references found)
```

### 7. Recommendation

_Pending - Claude will fill after reviewing this output._

---

## `assistant_suggestions`

### 1. Row count

```
1
```

### 2. Columns

```
 column_name |        data_type         | is_nullable 
-------------+--------------------------+-------------
 id          | integer                  | NO
 suggestion  | text                     | NO
 context     | text                     | YES
 applied     | boolean                  | YES
 created_at  | timestamp with time zone | YES
(5 rows)

```

### 3. Timestamp range (column: `created_at`)

```
            min_ts             |            max_ts             
-------------------------------+-------------------------------
 2026-03-26 13:59:55.397099-07 | 2026-03-26 13:59:55.397099-07
(1 row)

```

### 4. Sample (2 rows)

```
 id |                                                                                   suggestion                                                                                    |                                                                                                 context                                                                                                  | applied |          created_at           
----+---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------+---------+-------------------------------
  1 | ## Resumen Ejecutivo - Börsenhirn                                                                                                                                              +| Analiza el estado actual de Börsenhirn y dame un resumen ejecutivo. Incluye: (1) salud del portafolio, (2) algo destacable del performance, (3) una sugerencia concreta si ves algo que mejorar, (4) cua | f       | 2026-03-26 13:59:55.397099-07
    |                                                                                                                                                                                +|                                                                                                                                                                                                          |         | 
    | ### (1) Salud del portafolio                                                                                                                                                   +|                                                                                                                                                                                                          |         | 
    | **Estado: INACTIVO** — La cuenta está en $0.00 equity con 0 posiciones. El sistema está configurado en modo paper trading pero completamente sin actividad.                    +|                                                                                                                                                                                                          |         | 
    |                                                                                                                                                                                +|                                                                                                                                                                                                          |         | 
    | ### (2) Performance destacable                                                                                                                                                 +|                                                                                                                                                                                                          |         | 
    | **Sin datos históricos** — No hay trades registrados, por lo que no puedo evaluar performance. Esta es una configuración inicial o el sistema ha sido reiniciado completamente.+|                                                                                                                                                                                                          |         | 
    |                                                                                                                                                                                +|                                                                                                                                                                                                          |         | 
    | ### (3) Sugerencia concreta                                                                                                                                                    +|                                                                                                                                                                                                          |         | 
    | **Prioridad alta**: Configurar capital inic                                                                                                                                     |                                                                                                                                                                                                          |         | 
(1 row)

```

### 5. Outgoing foreign keys

```
 constraint_name | local_column | foreign_table | foreign_column 
-----------------+--------------+---------------+----------------
(0 rows)

```

### 6. Code usage (grep)

```
(no SQL references found)
```

### 7. Recommendation

_Pending - Claude will fill after reviewing this output._

---

## `bot_state`

### 1. Row count

```
0
```

### 2. Columns

```
   column_name    |          data_type          | is_nullable 
------------------+-----------------------------+-------------
 id               | integer                     | NO
 date             | character varying           | YES
 trades_today     | integer                     | YES
 wins_today       | integer                     | YES
 losses_today     | integer                     | YES
 day_start_equity | double precision            | YES
 updated_at       | timestamp without time zone | YES
(7 rows)

```

### 3. Timestamp range (column: `updated_at`)

```
 min_ts | max_ts 
--------+--------
        | 
(1 row)

```

### 4. Sample (2 rows)

```
(table is empty)
```

### 5. Outgoing foreign keys

```
 constraint_name | local_column | foreign_table | foreign_column 
-----------------+--------------+---------------+----------------
(0 rows)

```

### 6. Code usage (grep)

```
(no SQL references found)
```

### 7. Recommendation

_Pending - Claude will fill after reviewing this output._

---

## `daily_reports`

### 1. Row count

```
0
```

### 2. Columns

```
 column_name |          data_type          | is_nullable 
-------------+-----------------------------+-------------
 id          | integer                     | NO
 date        | character varying           | YES
 report_type | character varying           | YES
 content     | text                        | YES
 metrics     | json                        | YES
 created_at  | timestamp without time zone | YES
(6 rows)

```

### 3. Timestamp range (column: `created_at`)

```
 min_ts | max_ts 
--------+--------
        | 
(1 row)

```

### 4. Sample (2 rows)

```
(table is empty)
```

### 5. Outgoing foreign keys

```
 constraint_name | local_column | foreign_table | foreign_column 
-----------------+--------------+---------------+----------------
(0 rows)

```

### 6. Code usage (grep)

```
(no SQL references found)
```

### 7. Recommendation

_Pending - Claude will fill after reviewing this output._

---

## `entry_context`

### 1. Row count

```
0
```

### 2. Columns

```
  column_name  |          data_type          | is_nullable 
---------------+-----------------------------+-------------
 symbol        | character varying           | NO
 entry_price   | double precision            | YES
 highest_price | double precision            | YES
 rsi           | double precision            | YES
 regime        | character varying           | YES
 vix           | double precision            | YES
 ma_trend      | character varying           | YES
 ml_prob       | double precision            | YES
 saved_at      | timestamp without time zone | YES
(9 rows)

```

### 3. Timestamp range (column: `saved_at`)

```
 min_ts | max_ts 
--------+--------
        | 
(1 row)

```

### 4. Sample (2 rows)

```
(table is empty)
```

### 5. Outgoing foreign keys

```
 constraint_name | local_column | foreign_table | foreign_column 
-----------------+--------------+---------------+----------------
(0 rows)

```

### 6. Code usage (grep)

```
(no SQL references found)
```

### 7. Recommendation

_Pending - Claude will fill after reviewing this output._

---

## `regime_stats`

### 1. Row count

```
0
```

### 2. Columns

```
 column_name |          data_type          | is_nullable 
-------------+-----------------------------+-------------
 regime      | character varying           | NO
 wins        | integer                     | YES
 losses      | integer                     | YES
 total_pnl   | double precision            | YES
 updated_at  | timestamp without time zone | YES
(5 rows)

```

### 3. Timestamp range (column: `updated_at`)

```
 min_ts | max_ts 
--------+--------
        | 
(1 row)

```

### 4. Sample (2 rows)

```
(table is empty)
```

### 5. Outgoing foreign keys

```
 constraint_name | local_column | foreign_table | foreign_column 
-----------------+--------------+---------------+----------------
(0 rows)

```

### 6. Code usage (grep)

```
(no SQL references found)
```

### 7. Recommendation

_Pending - Claude will fill after reviewing this output._

---

## `signals`

### 1. Row count

```
0
```

### 2. Columns

```
 column_name |          data_type          | is_nullable 
-------------+-----------------------------+-------------
 id          | integer                     | NO
 timestamp   | timestamp without time zone | YES
 symbol      | character varying           | YES
 source      | character varying           | YES
 signal_type | character varying           | YES
 score       | double precision            | YES
 extra_data  | json                        | YES
 consumed    | boolean                     | YES
(8 rows)

```

### 3. Timestamp range (column: `timestamp`)

```
 min_ts | max_ts 
--------+--------
        | 
(1 row)

```

### 4. Sample (2 rows)

```
(table is empty)
```

### 5. Outgoing foreign keys

```
 constraint_name | local_column | foreign_table | foreign_column 
-----------------+--------------+---------------+----------------
(0 rows)

```

### 6. Code usage (grep)

```
(no SQL references found)
```

### 7. Recommendation

_Pending - Claude will fill after reviewing this output._

---

## `symbol_memory`

### 1. Row count

```
0
```

### 2. Columns

```
 column_name  |          data_type          | is_nullable 
--------------+-----------------------------+-------------
 symbol       | character varying           | NO
 score        | double precision            | YES
 total_trades | integer                     | YES
 wins         | integer                     | YES
 losses       | integer                     | YES
 total_pnl    | double precision            | YES
 updated_at   | timestamp without time zone | YES
(7 rows)

```

### 3. Timestamp range (column: `updated_at`)

```
 min_ts | max_ts 
--------+--------
        | 
(1 row)

```

### 4. Sample (2 rows)

```
(table is empty)
```

### 5. Outgoing foreign keys

```
 constraint_name | local_column | foreign_table | foreign_column 
-----------------+--------------+---------------+----------------
(0 rows)

```

### 6. Code usage (grep)

```
(no SQL references found)
```

### 7. Recommendation

_Pending - Claude will fill after reviewing this output._

---

## `trades`

### 1. Row count

```
0
```

### 2. Columns

```
 column_name |          data_type          | is_nullable 
-------------+-----------------------------+-------------
 id          | integer                     | NO
 timestamp   | timestamp without time zone | YES
 symbol      | character varying           | YES
 action      | character varying           | YES
 price       | double precision            | YES
 qty         | integer                     | YES
 value       | double precision            | YES
 pnl         | double precision            | YES
 reason      | text                        | YES
 regime      | character varying           | YES
 vix         | double precision            | YES
 ml_prob     | double precision            | YES
 rsi         | double precision            | YES
 ma_trend    | character varying           | YES
(14 rows)

```

### 3. Timestamp range (column: `timestamp`)

```
 min_ts | max_ts 
--------+--------
        | 
(1 row)

```

### 4. Sample (2 rows)

```
(table is empty)
```

### 5. Outgoing foreign keys

```
 constraint_name | local_column | foreign_table | foreign_column 
-----------------+--------------+---------------+----------------
(0 rows)

```

### 6. Code usage (grep)

```
borsenhirn/dashboard/bitacora_data.py:386:    # ── 4. P&L acumulado · derived from trades cerrados ──
borsenhirn/tenancy/db.py:16:        cur.execute("SELECT * FROM trades")  # implícitamente filtrado
borsenhirn/tenancy/db.py:120:                cur.execute("SELECT * FROM trades")
```

### 7. Recommendation

_Pending - Claude will fill after reviewing this output._

---

