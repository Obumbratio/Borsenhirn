# B1 — Capa de aplicación multi-tenant

> **Qué cubre:** cómo la capa de app del bot habla con Postgres después del
> Sprint B1, qué contrato expone cada módulo de persistencia, y cómo agregar
> código nuevo sin romper el aislamiento RLS.
>
> **Qué NO duplica:** la arquitectura/garantías de RLS están en
> [`../MULTI_TENANCY.md`](../MULTI_TENANCY.md); la misión y decisiones (D1..D8)
> en [PLAN.md](PLAN.md); la cronología bloque-por-bloque en
> [B1_SESSION_LOG.md](B1_SESSION_LOG.md).

---

## 1. La regla de oro

**Después de B1, toda la persistencia de runtime pasa por `borsenhirn/db.py`,
con un tenant context activo.** Nada de runtime abre conexiones por su cuenta ni
usa el rol `postgres`.

```
  request / arranque del bot
          │
   resolver tenant_id   (hoy: DEFAULT_TENANT_UUID; futuro B3: del JWT de Clerk)
          │
   with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, tenant_id):
          │
   SET app.current_tenant_id = <uuid>
          │
   Postgres aplica RLS → cada query ve solo las filas del tenant
```

Si nadie setea el tenant, las queries devuelven **0 filas** (`FORCE RLS`).
Fail-closed: el olvido nunca expone data de otro tenant.

---

## 2. Dos roles, dos pools

| Rol | Quién lo usa | RLS | Pool |
|---|---|---|---|
| `borsenhirn_app` (NOSUPERUSER, NOBYPASSRLS) | **todo el runtime** del bot | sí, filtra | `get_app_pool()` / `get_conn(role="app")` |
| `postgres` (superuser, BYPASSRLS) | migraciones, `TenantManager`, DDL de bootstrap, batch admin | bypass | `get_admin_pool()` / `get_conn(role="admin")` |

Config (en `config.py`, leído de env):

```
DB_HOST / DB_PORT / DB_NAME          # endpoint común
DB_USER / DB_PASSWORD                # admin (postgres)
APP_DB_USER / APP_DB_PASSWORD        # app (borsenhirn_app)
```

`APP_DB_USER`/`APP_DB_PASSWORD` hacen **fallback a las admin** si no están
seteadas → single-user dev sigue funcionando sin setup, pero **sin enforcement
real de RLS** (corre como superuser). Para tener aislamiento de verdad hay que
setear las dos APP vars en `.env`/`.env.dev`. Ver §9 (gotchas).

---

## 3. API de `borsenhirn/db.py`

```python
import borsenhirn.db as bdb
from borsenhirn.tenancy.constants import DEFAULT_TENANT_UUID, SYSTEM_TENANT_ID

# Conexión de runtime (sujeta a RLS) + tenant context
with bdb.get_conn(role="app") as conn, bdb.set_tenant(conn, DEFAULT_TENANT_UUID):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM bot_trade_outcomes")   # filtrado por RLS

# Operación admin (cross-tenant, peligrosa) — solo tareas administrativas
with bdb.get_conn(role="admin") as conn:
    ...

# Ver across-tenants SIN ser superuser (policy admin_bypass)
with bdb.get_conn(role="app") as conn, bdb.bypass_rls(conn):
    ...   # loggea WARNING al activarse
```

| Símbolo | Qué es |
|---|---|
| `get_conn(role="app"\|"admin")` | context manager; saca conn del pool y la devuelve (rollback si quedó txn abierta; no la cierra). |
| `set_tenant(conn, uuid)` | alias de `TenantContext`; `SET app.current_tenant_id`; limpia al salir (incluso con excepción). |
| `bypass_rls(conn)` | `SET LOCAL app.bypass_rls='on'` por la txn; activa la policy `admin_bypass`. |
| `get_app_pool()` / `get_admin_pool()` | pools lazy singleton (no abren al import). |
| `close_all_pools()` | cierra y resetea (shutdown / tests). |
| `set_connection_factory(fn)` / `clear_connection_factory()` | hook para tests que inyectan una conn fake (sin tocar Postgres). |

`TenantContext` soporta anidamiento: al salir restaura el tenant previo (útil
para admin que actúa "como" otro tenant temporalmente).

---

## 4. Contrato de los módulos de persistencia

Los 3 módulos refactoreados en 5.4 reciben el tenant por **constructor** y lo
propagan a cada query. Dos políticas de default según backwards-compat:

| Módulo | Constructor | Default tenant | Cómo aísla |
|---|---|---|---|
| `bot_memory_pg.BotMemory` | `BotMemory(tenant_id=DEFAULT_TENANT_UUID)` | **DEFAULT** (el bot legacy es un tenant real) | `_db()` → `bdb.get_conn("app")` + `set_tenant`. Bootstrap DDL usa `role="admin"`. |
| `borsenhirn/security/credentials.py` | `(..., tenant_id=None)` | **None** (preserva 24 tests que mockean) | helper `_scoped_cursor`: si `tenant_id` está seteado, envuelve en `TenantContext`; si es None, cursor plano. |
| `borsenhirn/safety/state_store_pg.py` | `PostgresStateStore(get_conn, tenant_id=None)` y `make_dashboard_db_write(get_conn, tenant_id=None)` | **None** (protege `ks_admin.py`) | mismo patrón de cursor scoped. |

**Por qué dos defaults:** `BotMemory` es el corazón del bot single-user → su
default es el tenant real `…001`. `credentials` y `state_store` tienen callers
admin (rotación de master key, kill-switch CLI) que deben correr sin tenant →
default `None` = comportamiento idéntico al de antes de B1. Decisión D5 en
[PLAN.md](PLAN.md).

### Wire-up (quién construye con qué)

- `main.py`: `BotMemory(tenant_id=DEFAULT_TENANT_UUID)` y
  `SafetyStack.init_from_config(_safety_get_conn, tenant_id=DEFAULT_TENANT_UUID)`.
  Helper local `_safety_get_conn()` devuelve conn del app pool.
- `borsenhirn/safety/bootstrap.py`: `init_from_config(get_conn_fn, tenant_id=None)`
  propaga el tenant a `PostgresStateStore` y `make_dashboard_db_write`.
- `api/main.py`: TODO de wire-up de Clerk JWT → `tenant_id` (out of scope hasta
  el Bloque B3 del roadmap SaaS).

---

## 5. Agregar persistencia nueva (checklist)

1. **Tabla nueva** → migración que le aplica `tenant_id NOT NULL` + FK a
   `tenants(tenant_id) ON DELETE RESTRICT` + index + `ENABLE`/`FORCE` RLS +
   las 2 policies (`tenant_isolation`, `admin_bypass`). Patrón en
   `scripts/b1_block2_migration.sql` y `b1_block4_migration.sql`.
2. **No** crees pools ni conexiones nuevas: usá `bdb.get_conn(role="app")`.
3. Toda query de runtime va dentro de `with bdb.set_tenant(conn, self.tenant_id)`.
4. DDL (`CREATE TABLE`) → `role="admin"` (el rol app no puede crear tablas).
5. Agregá un caso a los tests de aislamiento (§6) para la tabla nueva.
6. Corré `python scripts/check_rls_coverage.py` para confirmar que no quedó
   ninguna tabla sin RLS.

---

## 6. Tests de aislamiento (Bloque 5.6)

Prueban que RLS aísla de verdad con el rol app real (no superuser). **No corren
por default** (gate en `tests/conftest.py`: requieren `RUN_DB_INTEGRATION=1`) y
se auto-saltan si `DB_NAME != borsenhirn_dev`.

```bash
# Opción A — bash puro, sin pytest (READ-ONLY contra dev)
bash scripts/b1_block4_test_isolation.sh

# Opción B — pytest
set -a && source .env.dev && set +a
RUN_DB_INTEGRATION=1 venv/bin/pytest tests/test_b1_rls_integration.py -v
```

Tabla de verdad sobre `bot_trade_outcomes` (31 filas del default tenant):
sin contexto → 0 · default → 31 · tenant ajeno → 0 · `bypass_rls` → 31.
Más un guard que aborta si el rol resulta SUPERUSER/BYPASSRLS (sino la prueba
sería ficción). Verificado verde el 2026-06-05.

---

## 7. Gotchas / pendientes conocidos

- **`DB_PASS` vs `DB_PASSWORD`:** ✅ **resuelto (2026-06-05).** `config.py` ahora
  acepta `DB_PASS` como alias: `DB_PASSWORD = getenv("DB_PASSWORD") or
  getenv("DB_PASS") or "uriel"` (precedencia: canónico → alias → fallback). Esto
  alinea el pool admin y los 7 scripts admin que leen `config.DB_PASSWORD`
  (`ks_admin`, `rotate_master_key`, `check_rls_coverage`, `diagnose_rls`,
  `tenancy_demo`, `test_alerts`, `vault_demo`) con el `DB_PASS` de `.env.dev`.
  Verificado: el pool admin conecta como `postgres@borsenhirn_dev`.
- **`config.py` hace `load_dotenv()` → carga `.env`, no `.env.dev`.** Para correr
  contra dev hay que `source .env.dev` antes (con `override=False`, lo que
  exportes a mano tiene prioridad sobre `.env`).
- **Fallback silencioso a admin:** si `APP_DB_USER` no está seteada, el runtime
  corre como `postgres` (BYPASSRLS) y el aislamiento es ficticio. El guard de
  los tests 5.6 lo detecta; en prod, asegurar que ambas APP vars estén.
- **`api/main.py`** todavía no deriva `tenant_id` del usuario logueado — pendiente
  hasta B3 (Clerk).

---

## 8. Estado del Bloque 5

5.1–5.6 ✅. Pendiente solo el commit de 5.6 y este doc. Próximo: cierre del
sprint hacia Bloque 6 (tests amplios) → 7 (bot e2e en dev) → 8 (prod). Estado
vivo en [ESTADO.md](ESTADO.md).
