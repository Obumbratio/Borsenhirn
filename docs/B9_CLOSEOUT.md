# B9 — Cierre (Backups)

> Plan → [B9_BACKUPS_PLAN.md](B9_BACKUPS_PLAN.md) · runbook → [B9_BACKUP_RUNBOOK.md](B9_BACKUP_RUNBOOK.md). Estado: [ESTADO.md](ESTADO.md).

## Resultado en una frase

Hay **backups de DB automatizables, verificados y con retención**, un **restore a
DB nueva** (nunca in-place), un runbook, y **export por tenant** (portabilidad/
GDPR) que el propio usuario puede descargar.

## Qué se entregó

| Pieza | Qué |
|---|---|
| `scripts/db_backup.sh` | `pg_dump -F c` + verificación (`pg_restore --list`) + retención (`BACKUP_KEEP`, default 14). Cron-friendly. Probado contra dev. |
| `scripts/db_restore.sh` | Restore a una DB **nueva** (nunca in-place) + validación + confirmación. |
| `docs/B9_BACKUP_RUNBOOK.md` | Agenda (cron diario), retención, restore, verificación periódica, offsite, seguridad. |
| `borsenhirn/backups/export_tenant` | Dump JSON de los datos del tenant bajo RLS; **excluye `user_credentials`** (secretos). |
| `GET /me/export` | El tenant baja todos sus datos (auth). |

## Diseño (claves)

- **Verificación siempre**: un backup no verificado no cuenta.
- **Restore nunca in-place**: a DB nueva, promoción manual.
- **Export bajo RLS**: el rol app + tenant context garantizan que solo se exporta
  lo del tenant; los secretos cifrados se excluyen.

## Métricas

- **Tests:** 3 e2e (export). Baseline **376 passed**, integración **40 passed**.
- **Fix de paso:** `.gitignore` tenía `backups/` sin anclar → ignoraba el paquete
  `borsenhirn/backups/`. Anclado a `/backups/` (root dumps) y el paquete sí se
  versiona.

## Lo que queda (operacional)

1. **Agendar el cron** de `db_backup.sh` en el host de prod (tras "B1 Bloque 8").
2. **Destino offsite** (S3/GCS) para los dumps de largo plazo.
3. (Futuro) PITR/WAL si el RPO lo exige.

## Para CV / portfolio

> "Backups de Postgres automatizados con verificación y retención, restore seguro
> a DB nueva, y export de datos por tenant (portabilidad/GDPR) bajo RLS excluyendo
> secretos — todo sobre el aislamiento multi-tenant."
