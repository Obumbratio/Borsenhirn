# scripts/b1_diagnose_postgres.ps1
#
# Read-only diagnostic of Postgres-on-Windows for Sprint B1.
# Does NOT modify any file. Only reads and reports.
#
# Run from PowerShell as ADMINISTRATOR:
#   1. Right-click PowerShell -> "Run as Administrator"
#   2. cd C:\Users\Uriel\PyCharmMiscProject\proyecto_trading
#   3. powershell -ExecutionPolicy Bypass -File scripts\b1_diagnose_postgres.ps1
#
# Paste the entire output back to Claude.
#
# This file is pure ASCII (no accents, no unicode) so PowerShell parses
# it correctly regardless of source encoding.

$ErrorActionPreference = "Continue"

function Section($title) {
    Write-Host ""
    Write-Host ("=" * 64)
    Write-Host "  $title"
    Write-Host ("=" * 64)
}

# ----- 1. Postgres service -----
Section "[1] PostgreSQL service"
$svcs = Get-Service -Name "postgresql*" -ErrorAction SilentlyContinue
if ($svcs) {
    foreach ($s in $svcs) {
        Write-Host ("  Service:    " + $s.Name)
        Write-Host ("    Status:    " + $s.Status)
        Write-Host ("    StartType: " + $s.StartType)
    }
} else {
    Write-Host "  No postgresql* service found."
    Write-Host "  Possibilities:"
    Write-Host "    - Postgres not installed on Windows (maybe in WSL?)"
    Write-Host "    - Service has a different name"
    Write-Host "  List ALL services with: Get-Service | Where Name -like '*postgres*'"
}

# ----- 2. Process listening on 5432 -----
Section "[2] Process listening on port 5432 (Windows)"
try {
    $tcp = Get-NetTCPConnection -LocalPort 5432 -State Listen -ErrorAction SilentlyContinue
    if ($tcp) {
        foreach ($c in $tcp) {
            $proc = Get-Process -Id $c.OwningProcess -ErrorAction SilentlyContinue
            Write-Host ("  LocalAddress: " + $c.LocalAddress + "  Port: " + $c.LocalPort)
            Write-Host ("    PID:  " + $c.OwningProcess)
            Write-Host ("    Name: " + $proc.ProcessName)
        }
        Write-Host ""
        Write-Host "  KEY: if LocalAddress is only 127.0.0.1 or ::1, Postgres does NOT"
        Write-Host "  accept connections from WSL. Need to change listen_addresses."
        Write-Host "  If LocalAddress is 0.0.0.0 or *, Postgres accepts from any IP."
    } else {
        Write-Host "  Nothing listening on port 5432. Postgres not running or on another port."
    }
} catch {
    Write-Host ("  Get-NetTCPConnection failed: " + $_)
}

# ----- 3. Locate postgresql.conf -----
Section "[3] Searching postgresql.conf"
$candidatePaths = @(
    "C:\Program Files\PostgreSQL\18\data\postgresql.conf",
    "C:\Program Files\PostgreSQL\17\data\postgresql.conf",
    "C:\Program Files\PostgreSQL\16\data\postgresql.conf",
    "C:\Program Files\PostgreSQL\15\data\postgresql.conf"
)
$confPath = $null
foreach ($p in $candidatePaths) {
    if (Test-Path $p) {
        $confPath = $p
        Write-Host ("  FOUND:     " + $p)
        break
    } else {
        Write-Host ("  not exist: " + $p)
    }
}
if (-not $confPath) {
    Write-Host ""
    Write-Host "  postgresql.conf not found in typical paths."
    Write-Host "  Search manually with:"
    Write-Host "    Get-ChildItem 'C:\Program Files\PostgreSQL' -Recurse -Filter postgresql.conf -ErrorAction SilentlyContinue"
}

# ----- 4. Current listen_addresses -----
Section "[4] Current listen_addresses"
if ($confPath) {
    try {
        $confLines = Get-Content $confPath -ErrorAction Stop
        $listenLine = $confLines | Where-Object { $_ -match "^\s*listen_addresses\s*=" } | Select-Object -First 1
        if ($listenLine) {
            Write-Host ("  Current line: " + $listenLine)
            if ($listenLine -match "localhost") {
                Write-Host ""
                Write-Host "  PROBLEM CONFIRMED: listen_addresses is set to localhost only."
                Write-Host "  That is why WSL cannot connect. Change to:"
                Write-Host "    listen_addresses = '*'"
                Write-Host "  Or specifically:"
                Write-Host "    listen_addresses = 'localhost,172.25.144.1'"
            } elseif ($listenLine -match "\*") {
                Write-Host ""
                Write-Host "  listen_addresses = * - OK, should accept from all IPs."
                Write-Host "  If still failing, problem is pg_hba.conf or firewall."
            }
        } else {
            Write-Host "  No uncommented listen_addresses line found."
            Write-Host "  By default Postgres uses localhost - that is the problem."
            Write-Host "  Showing first 5 lines mentioning listen:"
            $confLines | Select-String -Pattern "listen" | Select-Object -First 5 | ForEach-Object {
                Write-Host ("    " + $_)
            }
        }
    } catch {
        Write-Host ("  Error reading " + $confPath + " : " + $_)
        Write-Host "  You probably need to run this script AS ADMIN."
    }
}

# ----- 5. pg_hba.conf relevant rules -----
Section "[5] pg_hba.conf - TCP/IP rules"
if ($confPath) {
    $hbaPath = $confPath.Replace("postgresql.conf", "pg_hba.conf")
    if (Test-Path $hbaPath) {
        try {
            Write-Host ("  Path: " + $hbaPath)
            Write-Host ""
            $hbaLines = Get-Content $hbaPath -ErrorAction Stop
            $relevant = $hbaLines | Where-Object {
                ($_ -notmatch "^\s*#") -and
                ($_ -match "^\s*host\s") -and
                ($_.Trim() -ne "")
            }
            if ($relevant) {
                Write-Host "  Active host rules:"
                foreach ($l in $relevant) {
                    Write-Host ("    " + $l)
                }
                Write-Host ""
                $wslOk = $relevant | Where-Object { $_ -match "172\.16|172\.25|all\s+all" }
                if ($wslOk) {
                    Write-Host "  Looks like there is a rule covering WSL2 subnet (172.x)."
                } else {
                    Write-Host "  WARNING: NO rule found covering WSL2 subnet (172.16.0.0/12)."
                    Write-Host "  Need to add a line like:"
                    Write-Host "    host  all  all  172.16.0.0/12  scram-sha-256"
                }
            } else {
                Write-Host "  No active host rules. Only local connections (Unix socket)."
            }
        } catch {
            Write-Host ("  Error reading " + $hbaPath + " : " + $_)
        }
    } else {
        Write-Host ("  pg_hba.conf not found at " + $hbaPath)
    }
}

# ----- 6. Windows firewall: port 5432 -----
Section "[6] Firewall rules for port 5432"
try {
    $rules = Get-NetFirewallRule -Direction Inbound -Enabled True -ErrorAction SilentlyContinue |
             Where-Object {
                 $portFilter = $_ | Get-NetFirewallPortFilter -ErrorAction SilentlyContinue
                 $portFilter -and ($portFilter.LocalPort -eq "5432" -or $portFilter.LocalPort -contains "5432")
             }
    if ($rules) {
        foreach ($r in $rules) {
            Write-Host ("  Rule:     " + $r.DisplayName)
            Write-Host ("    Action:  " + $r.Action)
            Write-Host ("    Profile: " + $r.Profile)
            Write-Host ("    Enabled: " + $r.Enabled)
        }
    } else {
        Write-Host "  WARNING: no explicit inbound rule for port 5432."
        Write-Host "  Postgres install sometimes does not create one. To add (admin):"
        Write-Host "    New-NetFirewallRule -DisplayName 'PostgreSQL WSL2' ``"
        Write-Host "      -Direction Inbound -Protocol TCP -LocalPort 5432 ``"
        Write-Host "      -Action Allow -Profile Any"
    }
} catch {
    Write-Host ("  Get-NetFirewallRule failed: " + $_)
    Write-Host "  Probably not running as admin."
}

# ----- 7. WSL2 to Windows host IP -----
Section "[7] WSL2 to Windows host IP"
Write-Host "  From WSL, the Windows host is typically the default gateway."
Write-Host "  Previous test detected: 172.25.144.1"
Write-Host ""
Write-Host "  Verify manually inside WSL:"
Write-Host "    ip route show default"
Write-Host "    cat /etc/resolv.conf | grep nameserver"

# ----- 8. Summary -----
Section "[8] SUMMARY FOR CLAUDE"
Write-Host "Paste all output back to Claude."
Write-Host ""
Write-Host "Expected diagnosis: listen_addresses is set to localhost (Postgres default)."
Write-Host "Step-by-step fix in: docs/B1_POSTGRES_FIX.md"
