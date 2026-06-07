# Encryption at rest para credenciales — Gap 3

**Objetivo:** ningún secreto de usuario (claves Alpaca, API keys, etc.) vive
en plaintext en la base de datos. Si alguien dumpea la DB, no obtiene nada
útil sin la master key — y la master key está en otro lugar.

---

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│  .env (en .gitignore)                                       │
│  BORSENHIRN_MASTER_KEY=Z2VuZXJhdGVkLWZlcm5ldC1rZXktaGVyZQ== │
└─────────────────┬───────────────────────────────────────────┘
                  │ leída al arranque por
                  ▼
              ┌────────┐                ┌─────────────────────┐
              │ Vault  │──── encrypt ──→│ user_credentials    │
              │(Fernet)│                │ (PostgreSQL)        │
              │        │←─── decrypt ───│ api_key_ciphertext  │
              └────────┘                │ api_secret_ciphertext│
                                        └─────────────────────┘
```

**Fernet =** `AES-128-CBC` para confidencialidad +
`HMAC-SHA256` para integridad. Cada encrypt incluye un IV aleatorio + un
timestamp. Es el estándar simétrico recomendado por la
[`cryptography` library](https://cryptography.io/en/latest/fernet/).

---

## Setup inicial

### 1. Generar master key

```bash
python -c "from borsenhirn.security import generate_master_key; print(generate_master_key())"
# → produce algo como: gAAAAABl_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx=
```

Pegala en tu `.env`:

```env
BORSENHIRN_MASTER_KEY=gAAAAABl_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx=
```

**Verificar que `.env` está en `.gitignore`:**

```powershell
Get-Content .gitignore | Select-String "^\.env$"
# Debe devolver una línea. Si no:
Add-Content .gitignore "`n.env"
```

### 2. Aplicar el schema

```bash
psql -U postgres -d borsenhirn -f borsenhirn/security/migrations.sql
```

Crea la tabla `user_credentials`:

```sql
CREATE TABLE user_credentials (
    user_id                uuid         NOT NULL,
    provider               text         NOT NULL,
    api_key_ciphertext     bytea        NOT NULL,  -- ← cifrado
    api_secret_ciphertext  bytea        NOT NULL,  -- ← cifrado
    encryption_version     integer      DEFAULT 1,
    created_at             timestamptz  DEFAULT now(),
    updated_at             timestamptz  DEFAULT now(),
    rotated_at             timestamptz,
    PRIMARY KEY (user_id, provider)
);
```

### 3. Smoke test

```bash
python scripts/vault_demo.py
# Esperado: 6 grupos OK (encrypt/decrypt, tamper, wrong key, passphrase, rotation, validation)

# Test contra Postgres real:
BORSENHIRN_TEST_DB=1 python scripts/vault_demo.py
```

---

## Uso desde código

```python
from borsenhirn.security import Vault, CredentialStore
from bot_memory_pg import _get_conn

vault = Vault.from_env("BORSENHIRN_MASTER_KEY")
store = CredentialStore(get_conn=_get_conn, vault=vault)

# Guardar credenciales (plaintext SOLO en memoria, nunca en DB ni logs)
store.set("user-uuid-123", "alpaca",
          api_key="PKABCDEF1234567890",
          api_secret="abc123secret456")

# Recuperar (decrypt automático)
creds = store.get("user-uuid-123", "alpaca")
print(creds.api_key)        # "PKABCDEF1234567890"
print(creds.api_secret)     # "abc123secret456"

# Listar usuarios (no decripta — solo IDs)
users = store.list_users("alpaca")

# Borrar
store.delete("user-uuid-123", "alpaca")
```

### Uso en el bot multi-tenant (futuro)

```python
# En lugar de leer config.ALPACA_API_KEY, leer del vault por user_id
def get_executor_for_user(user_id):
    creds = store.get(user_id, "alpaca")
    if not creds:
        raise ValueError(f"User {user_id} no tiene credenciales Alpaca")
    return Executor(api_key=creds.api_key, secret_key=creds.api_secret)
```

---

## Rotación de master key

Hay que rotar la master key:

- **Periódicamente** (cada 6-12 meses).
- **Inmediatamente** si sospechás que se filtró (commit accidental, leak, ex-empleado).

### Procedimiento sin downtime

```bash
# 1. Generar la nueva master key
NEW_KEY=$(python -c "from borsenhirn.security import generate_master_key; print(generate_master_key())")
echo "$NEW_KEY"
# → gAAAAABnewxxxxxxxxxxxxxxx...

# 2. Setear ambas vars (vieja + nueva) temporalmente
export BORSENHIRN_NEW_MASTER_KEY="$NEW_KEY"

# 3. DRY RUN — no escribe nada, solo cuenta filas
python scripts/rotate_master_key.py --dry-run

# 4. EJECUTAR — reencripta todas las credenciales
python scripts/rotate_master_key.py --confirm

# 5. Validar con un get() usando la nueva key
BORSENHIRN_MASTER_KEY="$NEW_KEY" python scripts/vault_demo.py

# 6. PROMOVER en .env
#    Reemplazar BORSENHIRN_MASTER_KEY=<vieja> por BORSENHIRN_MASTER_KEY=<nueva>
#    Borrar BORSENHIRN_NEW_MASTER_KEY del .env

# 7. Reiniciar bot/api
# 8. Confirmar que el bot puede leer credenciales con la nueva key
# 9. SOLO ENTONCES destruir la vieja master key (de tu password manager)
```

El script es atómico por fila: si algún registro falla, los demás no se
rompen y vas a poder reintentarlo.

### Operacional (B2)

- **Resolución de keys vía secret providers.** El script resuelve la key ACTUAL
  (`BORSENHIRN_MASTER_KEY`) y la NUEVA (`BORSENHIRN_NEW_MASTER_KEY`) con la misma
  cadena `file -> command -> env`. En prod la key activa puede venir de un
  secrets manager: `BORSENHIRN_MASTER_KEY_CMD="doppler secrets get ... --plain"`
  o `..._FILE=/run/secrets/...`. No hace falta pasarla por `.env`.
- **Debe correr como rol admin (cross-tenant).** La rotación recorre TODAS las
  filas de `user_credentials` (de todos los tenants). Eso requiere un rol que
  bypassee RLS (superuser `postgres` o `BYPASSRLS`). El script lo **verifica y
  aborta** si el rol está sujeto a RLS — sino vería 0 filas y "rotaría" nada en
  silencio. Por eso usa `DB_USER`/`DB_PASSWORD` (admin), no `borsenhirn_app`.
- **Si reporta `Total filas: 0`** cuando esperabas credenciales: estás apuntando
  a la DB equivocada o el rol no bypassa RLS. NO promuevas la key nueva.
- **Agenda.** Rotar cada **6 meses** (calendario) y de inmediato ante sospecha de
  leak. Dejar agendado un recordatorio recurrente.

---

## Donde NO meter la master key

❌ **Nunca:**
- En el repo (ni siquiera "para el demo").
- En `.env.example`.
- En screenshots, slack, issues, prompts de IA.
- Hardcodeada en un script de seed.
- Como parte de la URL de DB.
- En logs (el módulo `vault.py` cuida de no loggear plaintext, pero vos también).

✅ **Sí:**
- `.env` local (en `.gitignore`).
- Password manager personal (1Password, Bitwarden).
- Secrets manager en producción:
  - AWS Secrets Manager
  - Doppler
  - HashiCorp Vault
  - GCP Secret Manager
  - Azure Key Vault
- Variables de entorno de tu hosting (Heroku, Fly.io, Railway, etc.).

---

## Master key fuera de `.env` — secret providers (B2)

El código resuelve la master key vía una **cadena de providers intercambiables**
(`borsenhirn/security/secret_provider.py`), sin acoplarse a un manager
específico. `config.BORSENHIRN_MASTER_KEY` y `Vault.from_provider()` usan esta
cadena. Orden de prioridad (gana el primero con valor):

| # | Provider | Cómo se configura | Caso de uso |
|---|---|---|---|
| 1 | `file` | env `BORSENHIRN_MASTER_KEY_FILE=/ruta` | secretos montados (Docker/K8s `/run/secrets/...`) |
| 2 | `command` | env `BORSENHIRN_MASTER_KEY_CMD="..."` | CLI de un secrets manager |
| 3 | `env` | env `BORSENHIRN_MASTER_KEY=...` | dev (`.env`) y PaaS que inyecta env vars |

**Ejemplos de `_CMD` (sin agregar SDKs):**
```bash
# Doppler
export BORSENHIRN_MASTER_KEY_CMD="doppler secrets get BORSENHIRN_MASTER_KEY --plain"
# AWS Secrets Manager
export BORSENHIRN_MASTER_KEY_CMD="aws secretsmanager get-secret-value --secret-id borsenhirn/master_key --query SecretString --output text"
# HashiCorp Vault
export BORSENHIRN_MASTER_KEY_CMD="vault kv get -field=master_key secret/borsenhirn"
# 1Password
export BORSENHIRN_MASTER_KEY_CMD="op read op://Prod/borsenhirn/master_key"
```

**Docker/K8s (file):**
```bash
export BORSENHIRN_MASTER_KEY_FILE=/run/secrets/borsenhirn_master_key
```

En **dev** no configurás nada extra: cae al provider `env` y lee de `.env`
(comportamiento de siempre). En **prod** seteás `_FILE` o `_CMD` y la master key
**nunca toca un archivo `.env` del repo ni del deploy**.

Agregar un manager con SDK (boto3, hvac) = un provider nuevo que implemente
`.get(name)`; no cambia nada más. Tests: `tests/test_security_secret_provider.py`.

---

## Garantías que te da este sistema

| Propiedad | Cómo se logra |
|---|---|
| **Confidencialidad** | AES-128-CBC con IV aleatorio por mensaje |
| **Integridad** | HMAC-SHA256 verificado en decrypt — tamper-evident |
| **No-determinismo** | Dos encrypt del mismo plaintext → ciphertexts distintos |
| **Forward secrecy del esquema** | `encryption_version` permite migrar a algoritmos futuros sin romper rows viejas |
| **Rotación sin downtime** | Script atomic per-row, dual-key durante migración |
| **Defense-in-depth si filtra DB** | DB sin master key = bytes ininteligibles |

## Lo que NO te da (por diseño)

- **Si el atacante tiene acceso al servidor con master key cargada en memoria**, te lee todo.
  → Por eso el master en secrets manager con IAM separado del DB user.
- **Side-channel attacks** sobre el proceso (timing, cache).
  → Mitigación: usar el resultado del decrypt rápido, no comparar strings con `==` sino `secrets.compare_digest`.
- **Tampering de schema SQL.** Si alguien con access a la DB cambia `api_key_ciphertext` por bytes random, decrypt falla → VaultError. NO se silencia.
- **Backups antiguos.** Backup de hace 6 meses con master key vieja sigue siendo descifrable si alguien la roba. → Rotar también backups o usar `Vault.reencrypt()` masivo cada quarter.

---

## Tests

```bash
pytest tests/test_security_vault.py tests/test_security_credentials.py -v
# Esperado: 48 tests pasando (33 vault + 15 credentials)
```

Coverage de `borsenhirn/security/*` debería estar >95%.

---

## Checklist Gap 3

- [ ] `pip install cryptography` (probablemente ya lo tenés desde
      requirements.in).
- [ ] `psql -f borsenhirn/security/migrations.sql` aplicado.
- [ ] `python -c "from borsenhirn.security import generate_master_key; print(generate_master_key())"` ejecutado.
- [ ] Master key pegada en `.env` (NUNCA en `.env.example`).
- [ ] `.env` confirmado en `.gitignore`.
- [ ] `python scripts/vault_demo.py` → 6 grupos OK.
- [ ] `BORSENHIRN_TEST_DB=1 python scripts/vault_demo.py` → 7 grupos OK.
- [ ] `pytest tests/test_security_vault.py tests/test_security_credentials.py` → 48 pasan.
- [ ] (Cuando empiece a haber usuarios) Plan de rotación documentado y agendado cada 6 meses.

Cuando todos los checks ✓ → Gap 3 cerrado.

---

## Para CV / portfolio

Una sola línea defendible:

> "Encryption at rest para credenciales de broker via Fernet (AES-128-CBC + HMAC-SHA256), rotación de master key sin downtime, schema versionado, 48 unit tests con cobertura >95%."

Eso muestra que entendés AppSec mínima a nivel ML Engineer / SRE — bastante más que el promedio de candidatos junior.
