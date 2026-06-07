# B1 Postgres Fix — abrir Postgres-en-Windows a WSL2

## Síntoma

```
Probando localhost ...     FAIL  (Connection refused)
Probando 172.25.144.1 ...  FAIL  (timeout expired)
```

## Diagnóstico

Postgres está instalado en Windows pero por **default** solo escucha en
`localhost` (127.0.0.1) y no acepta conexiones desde fuera del propio
Windows. WSL2 corre en una VM separada, por eso no puede conectar.

Hay que cambiar 3 cosas:

1. `postgresql.conf` → `listen_addresses = '*'`
2. `pg_hba.conf` → permitir subnet WSL2 (`172.16.0.0/12`)
3. Firewall Windows → permitir puerto 5432
4. Reiniciar el servicio Postgres

---

## Paso 0 — Diagnosticar primero (read-only)

Desde **PowerShell como Administrador** (click derecho → Run as
Administrator), en la raíz del repo:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/b1_diagnose_postgres.ps1
```

Esto **no modifica nada**, solo lee y reporta:
- Servicio Postgres + status
- Quién escucha en puerto 5432 y en qué IP
- `listen_addresses` actual de `postgresql.conf`
- Reglas activas en `pg_hba.conf`
- Reglas de firewall existentes para 5432
- IP del Windows host detectada

**Pegame el output** para confirmar el diagnóstico antes de tocar nada.

---

## Paso 1 — Cambiar `postgresql.conf`

**Como Administrador**, abrí el archivo:

```
C:\Program Files\PostgreSQL\18\data\postgresql.conf
```

(Cambia `18` por la versión que tengas — el script de diagnóstico te
lo confirma.)

Buscá la línea `listen_addresses` (puede estar comentada con `#`).
Cambiala a:

```
listen_addresses = '*'
```

**Guardá el archivo.** Editor recomendado: Notepad++ o VS Code corriendo
como admin (Notepad estándar puede romper el encoding).

> **Alternativa más restrictiva:** si no querés exponer Postgres a *todas*
> las interfaces (mejor seguridad), usá:
>
> ```
> listen_addresses = 'localhost,172.25.144.1'
> ```
>
> Pero ojo: la IP de WSL2 puede cambiar al reiniciar Windows.
> `'*'` es más práctico para desarrollo en máquina personal.

---

## Paso 2 — Cambiar `pg_hba.conf`

Mismo directorio:

```
C:\Program Files\PostgreSQL\18\data\pg_hba.conf
```

Buscá la sección `# IPv4 local connections`. Vas a ver algo como:

```
# TYPE   DATABASE   USER   ADDRESS         METHOD
host     all        all    127.0.0.1/32    scram-sha-256
```

**Agregá una línea nueva justo debajo** para autorizar la subnet WSL2:

```
host     all        all    172.16.0.0/12   scram-sha-256
```

`172.16.0.0/12` cubre todo el rango WSL2 (172.16.0.0 a 172.31.255.255),
así no importa si la IP cambia al reiniciar.

**Guardá.**

---

## Paso 3 — Reiniciar el servicio Postgres

Desde **PowerShell como Administrador**:

```powershell
# Verificar nombre exacto del servicio
Get-Service postgresql*

# Reiniciar (ajustá el nombre según la versión)
Restart-Service postgresql-x64-18
```

Confirmar que volvió a arrancar:

```powershell
Get-Service postgresql-x64-18
# Status debe ser: Running
```

---

## Paso 4 — Abrir firewall (si hace falta)

Postgres a veces NO crea regla de firewall durante instalación. Desde
**PowerShell admin**:

```powershell
# Ver si ya hay regla
Get-NetFirewallRule | Where-Object DisplayName -like "*postgres*"

# Si no hay, crear una para WSL2 explícitamente:
New-NetFirewallRule -DisplayName 'PostgreSQL WSL2' `
    -Direction Inbound -Protocol TCP -LocalPort 5432 `
    -Action Allow -Profile Any
```

> **Más restrictivo** (recomendado para máquina con red pública): limitá
> a la subnet WSL2:
>
> ```powershell
> New-NetFirewallRule -DisplayName 'PostgreSQL WSL2' `
>     -Direction Inbound -Protocol TCP -LocalPort 5432 `
>     -Action Allow -Profile Any -RemoteAddress 172.16.0.0/12
> ```

---

## Paso 5 — Re-probar desde WSL

```bash
bash scripts/b1_test_postgres.sh
```

Debería imprimir:
```
  Probando localhost ...     FAIL  (esperado — WSL no tiene Postgres local)
  Probando 172.25.144.1 ...  OK
    PostgreSQL 18.x on x86_64-pc-mingw64...
```

Y al final:
```
HOST_BLOQUE_0=172.25.144.1
```

---

## Si TODAVÍA falla después de todo eso

Pegame el output del diagnóstico + el output del test post-fix.
Causas más exóticas:
- Hyper-V firewall interno (separado del firewall regular).
- Antivirus de terceros (Norton, McAfee) bloqueando.
- WSL2 con configuración de red `mirrored` en `.wslconfig` (algunos
  usuarios lo tienen y cambia el comportamiento).

---

## PLAN B — Postgres dentro de WSL (si todo lo anterior es mucho trabajo)

Si preferís **no tocar la instalación de Windows** y mover Postgres
dentro de WSL2 (para este sprint únicamente), vale la pena considerarlo:

```bash
# Dentro de WSL (Ubuntu 24.04)
sudo apt install -y postgresql-16
sudo service postgresql start

# Crear el usuario y db con la misma config que tu .env
sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'tu_password_actual';"
sudo -u postgres createdb borsenhirn_dev
```

Después restaurás el dump de producción acá. La ventaja: localhost
funciona directo, cero firewall, cero pg_hba. La desventaja: tu
producción sigue en Windows; estaríamos trabajando en una copia
totalmente separada.

**Decisión:** te recomiendo intentar primero el fix de Windows
(pasos 1-4). Es el approach correcto a largo plazo (te sirve para
todos los sprints futuros). El plan B es escape hatch si tenés un
problema raro de red Hyper-V que no logramos diagnosticar.
