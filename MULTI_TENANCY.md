# Multi-tenancy con Postgres RLS — Gap 4

**Objetivo:** un único bot/API/DB capaz de servir a múltiples usuarios
SaaS donde **es matemáticamente imposible que el usuario A vea data del
usuario B**, incluso si hay un bug en la capa de aplicación.

Estrategia: **Postgres Row-Level Security (RLS)**. La defensa vive en la
base de datos, no en el código Python — eso elimina la clase entera de
bugs "se me olvidó filtrar por user_id".

---

## ⚠️ ATENCIÓN — superusers de Postgres bypassan RLS

**Esto es lo más importante de este documento.** Postgres tiene una regla
no negociable: los roles `SUPERUSER` o `BYPASSRLS` **siempre saltan
todas las policies de RLS**, incluso con `FORCE ROW LEVEL SECURITY`
activado. La doc oficial:

> Superusers and roles with the BYPASSRLS attribute always bypass the
> row security system when accessing a table. Table owners normally
> bypass row security as well, though a table owner can choose to be
> subject to row security with ALTER TABLE ... FORCE ROW LEVEL SECURITY.

**Consecuencia operativa:**

- El usuario `postgres` (default superuser) **NO** se puede usar para
  validar el aislamiento. Todos los tests darán "ve todas las filas".
- Tu app/bot debe conectarse con un rol específico **sin** SUPERUSER
  ni BYPASSRLS — típicamente `borsenhirn_app`.
- Solo `psql` administrativo, migraciones, backups y dashboards
  internos usan `postgres` o un rol `borsenhirn_admin` con
  BYPASSRLS.

**Configuración mínima recomendada:**

```sql
-- Rol para la app/bot (NO bypassea RLS)
CREATE ROLE borsenhirn_app LOGIN PASSWORD 'xxxxx';
GRANT CONNECT ON DATABASE borsenhirn TO borsenhirn_app;
GRANT USAGE ON SCHEMA public TO borsenhirn_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
    TO borsenhirn_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO borsenhirn_app;
-- Aplicable también a tablas futuras:
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO borsenhirn_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO borsenhirn_app;

-- Rol admin (sí bypassea RLS — para dashboards / soporte / scripts)
CREATE ROLE borsenhirn_admin LOGIN PASSWORD 'yyyyy' BYPASSRLS;
GRANT ALL PRIVILEGES ON DATABASE borsenhirn TO borsenhirn_admin;
GRANT ALL PRIVILEGES ON SCHEMA public TO borsenhirn_admin;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO borsenhirn_admin;
```

Después en `.env` para la app:

```env
DB_USER=borsenhirn_app
DB_PASSWORD=xxxxx
```

`postgres` queda solo para `psql -f migrations.sql` (no app, no API,
no bot).

**Diagnóstico rápido de tu instalación:**

```bash
python scripts/diagnose_rls.py
```

Te dice: tu rol actual es superuser?, qué tablas tienen RLS, qué
policies, y qué hacer si tu rol bypassea.

---

## Estado de implementación

Esta entrega es **fase A (foundation)**. La fase B (migrar el bot
existente a multi-tenant) viene después, cuando estés listo para abrir
a usuarios externos.

### Fase A — listo ✅

- `borsenhirn/tenancy/` con módulos `tenant`, `db`, `management`.
- `borsenhirn/tenancy/migrations.sql` con tabla `tenants` + función
  helper `borsenhirn_enable_rls(table)`.
- `TenantContext` (context manager) que setea `app.current_tenant_id`.
- `TenantManager` con CRUD completo (create, get, list, suspend, etc.).
- `scripts/tenancy_demo.py` con verificación end-to-end de aislamiento.
- 48 unit tests cubriendo helpers + TenantManager con DB mock.

### Fase B — pendiente (cuando quieras lanzar SaaS)

- Aplicar `borsenhirn_enable_rls(...)` a las tablas existentes
  (`trades`, `positions`, `equity_snapshots`, `hirn_memory`,
  `signals`, `regime_states`, `killswitch_state`, `alerts_log`,
  `user_credentials`).
- Refactor de `bot_memory_pg.py` para que cada conexión/query use
  `TenantContext`.
- Refactor de `borsenhirn/safety/state_store_pg.py` para que el kill
  switch sea per-tenant (probablemente sí — un tenant puede estar
  HALT mientras otros operan).
- Refactor de `borsenhirn/security/credentials.py` para que las
  credenciales también respeten RLS (probable: agregar `tenant_id` a
  `user_credentials`).
- API de signup/login (separado, no parte de este gap).

---

## Arquitectura

```
                   ┌──────────────────────┐
                   │  FastAPI / Streamlit │
                   │  (auth: JWT/OAuth)   │
                   └──────────┬───────────┘
                              │
                  resolve user → tenant_id
                              │
                              ▼
                   ┌──────────────────────┐
                   │   TenantContext      │
                   │   (with statement)   │
                   └──────────┬───────────┘
                              │
                  SET app.current_tenant_id = '<uuid>'
                              │
                              ▼
                  ┌────────────────────────────┐
                  │  PostgreSQL                │
                  │  ┌──────────────────────┐  │
                  │  │ trades               │  │
                  │  │  ENABLE RLS          │  │
                  │  │  POLICY tenant_iso   │  │
                  │  │  USING (tenant_id =  │  │
                  │  │    current_setting() │  │
                  │  │  )                   │  │
                  │  └──────────────────────┘  │
                  │  ... idem todas las tablas │
                  └────────────────────────────┘
```

**Lo que esto garantiza:**

- Ninguna fila se devuelve si el `tenant_id` no matchea con el de la
  sesión.
- Si nadie setea `app.current_tenant_id`, **todas las queries devuelven
  0 filas** (gracias a `FORCE ROW LEVEL SECURITY`). Defensa contra el
  caso "se me olvidó setear el contexto".
- INSERTs verifican `WITH CHECK (tenant_id = current_setting(...))` —
  imposible insertar fila para otro tenant aunque pongas el `tenant_id`
  a mano.

---

## Componentes

### `Tenant` (dataclass)

```python
@dataclass
class Tenant:
    tenant_id: str           # UUID v4 string
    slug: str                # short, unique, p.ej. "uriel-x9k2"
    email: str
    display_name: str
    status: TenantStatus     # ACTIVE | SUSPENDED | DISABLED | DELETED
    ...
```

### `TenantContext` (context manager)

```python
# Contrato actual (Sprint B1): la conexión va por borsenhirn/db.py.
from borsenhirn.tenancy import TenantContext
import borsenhirn.db as bdb

with bdb.get_conn(role="app") as conn:        # antes: _get_conn() de bot_memory_pg (eliminado)
    with TenantContext(conn, "user-uuid-123"):
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM trades")  # solo trades del tenant
            rows = cur.fetchall()
```

Soporta anidamiento (útil para admin que actúa "como" otro tenant
temporalmente):

```python
with TenantContext(conn, admin_id):
    # ver datos del admin
    ...
    with TenantContext(conn, user_x_id):
        # ver datos del user X
        ...
    # de vuelta a admin_id
```

### `TenantManager` (CRUD)

```python
from borsenhirn.tenancy import TenantManager

mgr = TenantManager(get_conn=_get_conn)

# Signup
tenant = mgr.create_tenant(
    email="user@example.com",
    display_name="Jane Doe",
    metadata={"signup_source": "landing", "plan": "free"},
)

# Lookups
mgr.get_tenant(tenant_id)
mgr.get_tenant_by_email("user@example.com")
mgr.get_tenant_by_slug("jane-x4k7")

# Lifecycle
mgr.suspend(tenant_id, reason="non-payment")
mgr.disable(tenant_id, reason="user requested cancellation")
mgr.reactivate(tenant_id, reason="user paid up")
mgr.soft_delete(tenant_id, reason="GDPR delete")

# Listings
mgr.list_tenants(status=TenantStatus.ACTIVE, limit=50)
mgr.count_tenants(status=TenantStatus.SUSPENDED)
```

---

## Setup inicial

### 1. Aplicar el schema base

```bash
psql -U postgres -d borsenhirn -f borsenhirn/tenancy/migrations.sql
```

Esto crea:
- Tabla `tenants` con check constraint en status, FK trigger updated_at.
- Tenant especial `00000000-...0000` ("system") para datos legacy.
- Función `borsenhirn_enable_rls(table_name)` para aplicar RLS.
- Función `borsenhirn_disable_rls(table_name)` (emergencias / tests).
- Vista `current_tenant_info` para debugging.

### 2. Verificar la instalación

```bash
psql -U postgres -d borsenhirn -c "SELECT * FROM tenants"
# Debe mostrar al menos 1 fila: el system tenant.

psql -U postgres -d borsenhirn -c "SELECT * FROM current_tenant_info"
# tenant_id = NULL (no hay session activa).
```

### 3. Smoke test end-to-end

```bash
python scripts/tenancy_demo.py
# Esperado:
#   [1] OK tabla `tenants` existe
#   [2] OK creados: A=... B=...
#   [3] OK tabla `demo_rls_trades` creada con RLS habilitado
#   [4a] OK 3 trades insertados como tenant A
#   [4b] OK 1 trade insertado como tenant B
#   [5a] Tenant A ve 3 trades: OK
#   [5b] Tenant B ve 1 trades: OK
#   [6] Sin tenant context: ve 0 trades: OK
#   [7] OK insert sin tenant context fue rechazado por RLS
#   [8] OK cleanup
#   DEMO COMPLETO — RLS aislamiento verificado
```

### 4. Tests unitarios

```bash
pytest tests/test_tenancy_tenant.py tests/test_tenancy_db.py tests/test_tenancy_management.py -v
# Esperado: 48 tests pasando
```

---

## Fase B — plan de migración (futuro)

> ⚠️ **NOTA 2026-06-05 — esta sección es el PLAN ORIGINAL, ya superado por la
> implementación real (Sprint B1, branch `feature/multi-tenancy-phase-b`, ~90%).**
> El contrato de código actual **difiere** de los snippets de abajo:
> - El pool y `_get_conn` de `bot_memory_pg.py` **fueron eliminados**. La conexión
>   ahora va por `borsenhirn/db.py` → `get_conn(role='app')` + `set_tenant`.
>   **No importes `_get_conn` de `bot_memory_pg`** (ya no existe; causó un bug
>   latente en `main.py` — ver `docs/ERRORES.md`).
> - El tenant del bot legacy es `DEFAULT_TENANT_UUID` (`00000000-…001`), **no**
>   `SYSTEM_TENANT_ID` (`…000`). El SYSTEM es un sentinel sin fila, reservado para
>   data shared global futura. Ambos viven en `borsenhirn/tenancy/constants.py`.
> - Los 3 módulos refactoreados (`bot_memory_pg`, `security/credentials`,
>   `safety/state_store_pg`) usan `tenant_id` como parámetro de constructor.
>
> Cronología real en [`docs/B1_SESSION_LOG.md`](docs/B1_SESSION_LOG.md);
> decisiones en [`docs/PLAN.md`](docs/PLAN.md). Los snippets de abajo se conservan
> como referencia histórica del diseño.

### Estrategia conservadora: backfill + RLS gradual

Para cada tabla del bot existente (digamos `trades`):

```sql
-- Aplica todo de una vez vía la función helper:
SELECT borsenhirn_enable_rls('trades');

-- Eso internamente hace:
-- 1. ALTER TABLE trades ADD COLUMN tenant_id uuid;
-- 2. UPDATE trades SET tenant_id = '00...0' WHERE tenant_id IS NULL;
-- 3. ALTER TABLE trades ALTER COLUMN tenant_id SET NOT NULL;
-- 4. ALTER TABLE trades ADD CONSTRAINT trades_tenant_fk FOREIGN KEY ...;
-- 5. CREATE INDEX idx_trades_tenant ON trades(tenant_id);
-- 6. ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
-- 7. ALTER TABLE trades FORCE ROW LEVEL SECURITY;
-- 8. CREATE POLICY tenant_isolation ON trades ...;
```

**Lo bueno:** la función es **idempotente** — podés correrla varias
veces sin problema, y en cada tabla por separado, en horarios distintos
si querés.

**Lo importante:** después de aplicar, **TODAS las queries de tu bot
necesitan ir dentro de `TenantContext`** o no devuelven nada. Para el
bot single-user actual eso significa:

```python
# main.py al arrancar:
from borsenhirn.tenancy import TenantContext, SYSTEM_TENANT_ID

# Para que el bot legacy siga funcionando sobre las filas con
# tenant_id = SYSTEM_TENANT_ID:
def get_tenant_for_legacy_bot() -> str:
    return SYSTEM_TENANT_ID

# En cada función de bot_memory_pg.py:
def get_daily_state():
    conn = _get_conn()
    with TenantContext(conn, get_tenant_for_legacy_bot()):
        # ... queries existentes sin cambios
```

### Tablas a migrar (orden recomendado)

| Tabla | Prioridad | Por qué |
|---|---|---|
| `trades` | P0 | Datos sensibles, alta frecuencia |
| `positions` | P0 | Idem |
| `equity_snapshots` | P0 | Métricas financieras |
| `hirn_memory` | P0 | Conversaciones privadas con LLM |
| `user_credentials` | P0 | API keys del broker |
| `killswitch_state` | P1 | Cada tenant puede estar HALT independiente |
| `alerts_log` | P1 | Histórico de alertas |
| `signals` | P2 | Señales del scanner |
| `regime_states` | P2 | Estado de régimen (puede ser global) |
| `bot_memory` | P2 | Estado misc |

### Refactor de funciones legacy

El patrón general en `bot_memory_pg.py`:

**Antes:**
```python
class BotMemory:
    def get_daily_state(self):
        conn = self._db()
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM bot_state WHERE date = current_date")
            return cur.fetchone()
```

**Después:**
```python
from borsenhirn.tenancy import TenantContext, SYSTEM_TENANT_ID

class BotMemory:
    def __init__(self, tenant_id: str = SYSTEM_TENANT_ID):
        self.tenant_id = tenant_id

    def get_daily_state(self):
        conn = self._db()
        with TenantContext(conn, self.tenant_id):
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM bot_state WHERE date = current_date")
                return cur.fetchone()
```

Y al construir:

```python
# Single-tenant legacy
memory = BotMemory()  # usa SYSTEM_TENANT_ID

# Multi-tenant
memory = BotMemory(tenant_id=resolved_user_tenant_id)
```

### Tests obligatorios antes de mergear fase B

1. **Test de aislamiento real**: dos tenants distintos, plantar 100
   trades en cada uno, confirmar que cada uno solo ve los suyos.
2. **Test de no-leakage en aggregations**: `SELECT COUNT(*)` y
   `SELECT SUM(pnl)` deben respetar RLS también (lo hacen porque RLS
   aplica antes del aggregate).
3. **Test de FORCE RLS**: sin context, todas las queries devuelven 0.
4. **Test de INSERT cross-tenant**: insertar una fila con
   `tenant_id = X` desde una sesión con `current_tenant_id = Y` debe
   FALLAR.
5. **Test de UPDATE cross-tenant**: idem para UPDATE.
6. **Test de FK constraint**: borrar un tenant que tiene filas en
   `trades` debe fallar (ON DELETE RESTRICT).

---

## Cuidados de operación

### El admin tiene que poder ver todo

Para herramientas administrativas (dashboard interno, scripts de
soporte), necesitás un usuario Postgres separado que **bypass RLS**:

```sql
-- Crear rol admin que NO está sujeto a RLS
CREATE ROLE borsenhirn_admin BYPASSRLS LOGIN PASSWORD 'xxx';
GRANT SELECT ON ALL TABLES IN SCHEMA public TO borsenhirn_admin;

-- Tu app usa el rol regular borsenhirn_app (sin BYPASSRLS).
-- Tu CLI admin usa borsenhirn_admin.
```

**No le pongas BYPASSRLS al usuario que usa la app.** Si por error la
app se conecta como admin, perdés todas las garantías.

### Los superusers de Postgres siempre bypass RLS

Regla obligatoria: **el usuario `postgres` no debe ser quien se conecta
desde la app**. Crear un rol específico `borsenhirn_app` con permisos
mínimos.

### Backups

Los backups (`pg_dump`) los hacen los superusers, así que ven todas las
filas. No es leak — pero si el backup queda en un bucket S3 mal
configurado, otro problema.

### Migraciones futuras

Si agregás una tabla nueva mañana, **no te olvides de aplicar
`borsenhirn_enable_rls('nueva_tabla')`**. Te conviene tener un script
en `scripts/check_rls_coverage.py` que liste tablas SIN RLS para que CI
te avise.

---

## Checklist Gap 4 fase A (lo que entregamos hoy)

- [ ] `psql -f borsenhirn/tenancy/migrations.sql` aplicado.
- [ ] `psql -c "SELECT * FROM tenants"` muestra el system tenant.
- [ ] `python scripts/tenancy_demo.py` → 8 pasos OK.
- [ ] `pytest tests/test_tenancy_*.py` → 48 tests pasan.
- [ ] Lectura del módulo: `borsenhirn/tenancy/__init__.py` exporta lo
      esperado.

## Checklist Gap 4 fase B (cuando quieras lanzar SaaS)

- [ ] Crear rol Postgres `borsenhirn_app` con permisos mínimos (sin
      BYPASSRLS).
- [ ] Crear rol Postgres `borsenhirn_admin` con BYPASSRLS para CLI.
- [ ] Aplicar `borsenhirn_enable_rls(...)` a las 8-10 tablas del bot.
- [ ] Refactor de `bot_memory_pg.py` para usar `TenantContext` en cada
      función.
- [ ] Refactor de `borsenhirn/safety/state_store_pg.py` para kill
      switches per-tenant.
- [ ] Refactor de `borsenhirn/security/credentials.py` con `tenant_id`.
- [ ] Tests de aislamiento real (no mocks) en CI.
- [ ] `scripts/check_rls_coverage.py` que falle si una tabla nueva no
      tiene RLS.
- [ ] Auth (JWT/OAuth) que resuelve user → tenant_id en cada request.
- [ ] Documentación de deployment con dos roles DB separados.

---

## Para CV / portfolio

Línea defendible:

> "Multi-tenancy con Postgres Row-Level Security: aislamiento garantizado a
> nivel de DB (FORCE RLS), context manager Python para inyectar tenant en
> cada sesión, función SQL idempotente para habilitar RLS en tablas
> existentes con backfill seguro, 48 unit tests + smoke test end-to-end."

Mostrar en una entrevista esto + el script `tenancy_demo.py` corriendo
en pantalla = +1 nivel sobre el promedio de juniors.
