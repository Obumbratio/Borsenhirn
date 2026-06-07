# scripts/b1_env_check.ps1
# Verificación de entorno antes del Sprint B1 (Multi-tenancy fase B).
# Corré desde PowerShell EN LA RAÍZ DEL REPO:
#   powershell -ExecutionPolicy Bypass -File scripts/b1_env_check.ps1
#
# No modifica nada. Solo lee y reporta. Pegale el output entero a Claude.

$ErrorActionPreference = "Continue"
$out = @()

function Section($title) {
    $script:out += ""
    $script:out += "=" * 64
    $script:out += "  $title"
    $script:out += "=" * 64
}

function Add-Line($txt) { $script:out += $txt }

# ── 1. Postgres client ────────────────────────────────────
Section "[1] psql client (Windows)"
try {
    $v = & psql --version 2>&1
    Add-Line "psql found: $v"
} catch {
    Add-Line "psql NOT in PATH on Windows. Install Postgres tools or use WSL."
}

# ── 2. Postgres server detection ──────────────────────────
Section "[2] PostgreSQL service status"
$svc = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
if ($svc) {
    foreach ($s in $svc) {
        Add-Line "Service: $($s.Name) - Status: $($s.Status)"
    }
} else {
    Add-Line "No 'postgresql*' service found on Windows."
    Add-Line "Probably running in WSL. Check with: wsl -d Ubuntu service postgresql status"
}

# ── 3. Probar conexión a borsenhirn ──────────────────────
Section "[3] Conexión a DB borsenhirn"
$envFile = ".env"
if (Test-Path $envFile) {
    $envContent = Get-Content $envFile -Raw
    $dbHost = if ($envContent -match "DB_HOST=([^\r\n]+)") { $matches[1].Trim() } else { "localhost" }
    $dbPort = if ($envContent -match "DB_PORT=([^\r\n]+)") { $matches[1].Trim() } else { "5432" }
    $dbName = if ($envContent -match "DB_NAME=([^\r\n]+)") { $matches[1].Trim() } else { "borsenhirn" }
    $dbUser = if ($envContent -match "DB_USER=([^\r\n]+)") { $matches[1].Trim() } else { "postgres" }
    Add-Line "From .env: host=$dbHost port=$dbPort db=$dbName user=$dbUser"
    Add-Line "Probando conexión (te va a pedir password)..."
    $testCmd = "psql -h $dbHost -p $dbPort -U $dbUser -d $dbName -c `"SELECT version();`""
    Add-Line "Comando: $testCmd"
    Add-Line ""
    Add-Line "Corré ESTE comando manualmente en PowerShell y pegá el output:"
    Add-Line "  $testCmd"
} else {
    Add-Line "FAIL: no encontré .env en la raíz del repo."
}

# ── 4. Procesos Python relacionados ──────────────────────
Section "[4] Procesos Python corriendo (potencial bot activo)"
$pyProcs = Get-Process python, python3, pythonw -ErrorAction SilentlyContinue
if ($pyProcs) {
    foreach ($p in $pyProcs) {
        Add-Line "PID=$($p.Id) Name=$($p.ProcessName) Mem=$([Math]::Round($p.WorkingSet/1MB,1))MB Started=$($p.StartTime)"
    }
} else {
    Add-Line "Sin procesos python.exe corriendo."
}

# ── 5. Streamlit ─────────────────────────────────────────
Section "[5] Procesos Streamlit"
$st = Get-Process -Name streamlit -ErrorAction SilentlyContinue
if ($st) {
    foreach ($s in $st) {
        Add-Line "PID=$($s.Id) Name=$($s.ProcessName)"
    }
} else {
    Add-Line "Sin streamlit corriendo."
}

# ── 6. Carpeta backups/ ──────────────────────────────────
Section "[6] Carpeta backups/"
if (Test-Path "backups") {
    Add-Line "OK: backups/ existe."
    $files = Get-ChildItem backups -ErrorAction SilentlyContinue
    if ($files) {
        Add-Line "Contenido actual:"
        foreach ($f in $files) {
            Add-Line "  $($f.Name) ($([Math]::Round($f.Length/1KB,1)) KB)"
        }
    } else {
        Add-Line "(vacía — esperado)"
    }
} else {
    Add-Line "FAIL: backups/ no existe. Creala con: mkdir backups"
}

# ── 7. Git status ────────────────────────────────────────
Section "[7] git status"
try {
    $gitBranch = & git rev-parse --abbrev-ref HEAD 2>$null
    Add-Line "Branch actual: $gitBranch"
    $gitStatus = & git status --short 2>$null
    if ($gitStatus) {
        Add-Line "Cambios pendientes:"
        $gitStatus | ForEach-Object { Add-Line "  $_" }
    } else {
        Add-Line "Working tree limpio."
    }
} catch {
    Add-Line "Error leyendo git: $_"
}

# ── 8. Resumen final ─────────────────────────────────────
Section "[8] RESUMEN PARA CLAUDE"
Add-Line "Pegá todo este output a Claude. Si algo falla:"
Add-Line "  - psql no en PATH → 'sudo apt install postgresql-client' en WSL, o agregar al PATH de Windows"
Add-Line "  - service postgres detenido → 'sudo service postgresql start' en WSL"
Add-Line "  - conexión rechazada → revisar pg_hba.conf y postgresql.conf listen_addresses"
Add-Line "  - procesos corriendo → detenelos manualmente antes de seguir"

# Output final
$out | ForEach-Object { Write-Host $_ }
