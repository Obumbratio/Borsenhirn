# B9 — Runbook de backups

> Operación de backups/restore. Diseño: [B9_BACKUPS_PLAN.md](B9_BACKUPS_PLAN.md).

## Backup

```bash
# manual (dev)
bash scripts/db_backup.sh
# prod (en el host de prod, con su .env)
ENV_FILE=.env bash scripts/db_backup.sh
```
- `pg_dump -F c` con verificación (`pg_restore --list`) y retención automática.
- Sale en `backups/<db>_<timestamp>.dump` (gitignored).
- Conserva los **`BACKUP_KEEP` más recientes** (default 14); borra los más viejos.

### Agenda (cron diario)
```cron
0 3 * * *  cd /ruta/al/repo && ENV_FILE=.env bash scripts/db_backup.sh >> backups/backup.log 2>&1
```
Recomendado: 1 backup diario, retención 14. Para semanal/mensual de largo plazo,
copiar periódicamente un dump a almacenamiento **offsite** (S3/GCS/disco externo).

## Restore (a DB NUEVA, nunca in-place)

```bash
bash scripts/db_restore.sh backups/borsenhirn_20260607_030000.dump borsenhirn_restore
```
- Crea la DB destino nueva, restaura ahí, valida. **No toca ninguna DB existente.**
- Promoción manual: validar `borsenhirn_restore` → repuntar la app o renombrar DBs.

## Verificación periódica (mensual)
- Hacer un restore de prueba a una DB temp y confirmar row counts → da confianza
  de que los backups sirven. Un backup no verificado es un backup que no existe.

## Seguridad
- El dump contiene `user_credentials` **cifradas** (Fernet): inútil sin la master
  key (que vive en un secrets manager, B2). Igual: guardar los dumps con cuidado
  (offsite cifrado / acceso restringido).

## Export por tenant (portabilidad / offboarding / GDPR)
- `GET /me/export` (auth): el tenant baja todos sus datos (JSON, bajo RLS).
- `borsenhirn.backups.export_tenant(tenant_id)` desde código/CLI.
- **Excluye** `user_credentials` (secretos).

## Pendiente a prod
- Agendar el cron en el host de prod tras "B1 Bloque 8".
- Definir el destino offsite.
