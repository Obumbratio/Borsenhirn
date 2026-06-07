# Checklist de validación — Gaps 2, 6, 7, 8

Antes de abrir otro frente, correr todo lo siguiente desde PowerShell
en `C:\Users\Uriel\PyCharmMiscProject\proyecto_trading\` con el venv
activado.

---

## Bloque 0 — Sanidad básica

```powershell
# Confirmá Python y venv
python --version
where python
# Debería ser una ruta dentro de tu .venv

# Variables de entorno cargadas
python -c "import config; print('Discord:', bool(config.DISCORD_WEBHOOK_URL)); print('SMTP:', bool(config.SMTP_USER)); print('DB:', config.DB_NAME)"
```

Si todo OK seguir; si falta algo en `.env`, completar primero.

---

## Bloque 1 — Gap 7: Reproducibilidad y dependencias

```powershell
# 1a. Instalar pip-tools si no lo tenés
pip install pip-tools

# 1b. IMPORTANTE: si tu requirements.in salió raro (encoding UTF-16 o
#     un pip freeze pegado), reescribilo asegurando UTF-8.
#     PowerShell lo hace bien con Set-Content -Encoding utf8 desde un
#     here-string, o simplemente abrí el archivo en VS Code / PyCharm,
#     guardá como "UTF-8 sin BOM" y pegá las top-level deps que te
#     dejé en el repo.

# 1c. Compilar lockfile con hashes
pip-compile --generate-hashes --output-file=requirements.txt requirements.in
pip-compile --generate-hashes --output-file=requirements-dev.txt requirements-dev.in

# 1d. Sincronizar venv
pip-sync requirements.txt requirements-dev.txt

# 1e. Verificar versión exacta de Python y ajustar .python-version
python --version
# si imprime "Python 3.14.1", abrí .python-version y dejá "3.14.1"

# 1f. Test de reproducibilidad bit-exacta
python scripts/verify_reproducibility.py
# Esperado: "OK — Modelo BIT-IDENTICO entre runs."
```

Si el verify falla con diferentes hashes, leer el output — te dice
posibles causas (n_jobs, sklearn version, etc.).

---

## Bloque 2 — Gap 8: Tests y coverage

```powershell
# 2a. Asegurate que pytest + cov + hypothesis están instalados
pip list | Select-String "pytest|hypothesis"

# 2b. Limpiar cache (importante si veniste tocando archivos)
pytest --cache-clear

# 2c. Correr todos los tests
pytest

# 2d. Con coverage
pytest --cov --cov-report=term-missing --cov-report=html

# 2e. Abrí el reporte
Invoke-Item htmlcov/index.html
# o navegá manual a htmlcov/index.html

# 2f. Resultados esperados (~):
#   - 100+ tests pasando
#   - Coverage en borsenhirn/safety/* > 90%
#   - Coverage en risk_manager + circuit_breaker > 90%
#   - Coverage en strategy + m3_risk ~ 60% (de test_core.py)
#   - Coverage TOTAL > 60% (sin contar UI/scripts)
```

Si algún test falla en tu Windows que no falló en mi smoke test:
copiá el output completo y arreglamos.

---

## Bloque 3 — Gap 2: Safety stack en vivo

```powershell
# 3a. Confirmar que las tablas existen
psql -U postgres -d borsenhirn -c "\dt killswitch_state"
psql -U postgres -d borsenhirn -c "\dt alerts_log"

# 3b. Smoke test de canales (Discord + Email + Dashboard)
python scripts/test_alerts.py

# Esperado:
#   discord:   OK
#   email:     OK (si configuraste SMTP)
#   dashboard: OK

# 3c. Verificar que main.py importa con safety integrado
python -c "import main; print('OK')"

# 3d. Smoke del bot un solo ciclo
python main.py --once
# Esperado:
#   - Log "[SAFETY] stack listo | canales: ['discord', 'email', 'dashboard']"
#   - Mensaje "Bot iniciado" llega a Discord (vía send_alert hookeado)
#   - Si no hay HALT, corre un ciclo normal y termina
#   - Si hay HALT preexistente, log warning + alerta CRITICAL

# 3e. Probar manual halt + clear
# (todavía no escribimos scripts/ks_admin.py — lo agregamos en la próxima
#  sesión si querés. Por ahora podés usar SQL directo:)
psql -U postgres -d borsenhirn -c @"
INSERT INTO killswitch_state (key, triggered, reason, triggered_at, updated_at)
VALUES ('manual_halt', true, 'test manual', now(), now())
ON CONFLICT (key) DO UPDATE SET triggered=true, reason='test manual',
                                triggered_at=now(), updated_at=now();
"@

# Verificar que el bot ahora skipea trading
python main.py --once
# Esperado: "[SAFETY] HALT activo: ['manual_halt'] — bot en modo seguro"

# Limpiar el halt
psql -U postgres -d borsenhirn -c "UPDATE killswitch_state SET triggered=false, cleared_at=now() WHERE key='manual_halt';"
```

---

## Bloque 4 — Gap 6: Disclaimers y dashboard

```powershell
# 4a. Confirmar que los archivos legales existen
ls legal/
# Esperado: README.md, DISCLAIMER.md, TERMS.md, PRIVACY.md

# 4b. Editar placeholders en los .md
#   - "your-repo" → tu URL real de GitHub
#   - "author"    → tu nombre / handle
#   - jurisdicción si hace falta

# 4c. Audit de lenguaje
python scripts/audit_language.py
# Esperado: solo "Sin riesgo de gap" en gen_daily_report.py (falso positivo OK)

python scripts/audit_language.py --strict
# Esperado: 12-15 matches MEDIUM, todos en campos de datos (no UI)

# 4d. Levantar dashboard y ver el banner
streamlit run dashboard.py
# Verificar:
#   - Banner naranja arriba con "EDUCATIONAL TOOL — NOT FINANCIAL ADVICE"
#   - Footer abajo con links a Disclaimer/Terms/Privacy
#   - Subtítulo cambió a "educational research platform"
```

---

## Bloque 5 — Higiene de seguridad

```powershell
# 5a. Confirmar .env en .gitignore
Get-Content .gitignore | Select-String "^\.env$"
# Si no devuelve nada:
Add-Content .gitignore "`n.env"

# 5b. Confirmar que .env.example NO tenga secretos reales
Get-Content .env.example | Select-String "DISCORD_WEBHOOK_URL"
# Esperado: línea con DISCORD_WEBHOOK_URL=  (vacío, solo placeholder)
# Si tiene un URL real → reemplazá por placeholder y rotá el webhook
# desde Discord settings.

# 5c. Lo que SÍ debería ir a git
git status legal/ borsenhirn/ tests/ scripts/ pyproject.toml \
    requirements.in requirements-dev.in .python-version \
    PLAN_PRODUCCION.md REPRODUCIBILIDAD.md TESTS.md \
    CHECKLIST_VALIDACION.md

# Lo que NO debe ir nunca
git status .env *.pkl logs/ models/ results/
# Si aparece alguno como "untracked" o "modified", agregalos al .gitignore
```

---

## Si todo el checklist queda ✓

Entonces tenés cerrados:

- ✅ Gap 1 — ML validation (con honest finding: AUC marginal)
- ✅ Gap 2 — Circuit breakers + alertas
- ✅ Gap 6 — Disclaimers (templates listos, falta revisión legal pre-cobro)
- ✅ Gap 7 — Reproducibilidad bit-exacta
- 🟡 Gap 8 — Tests core hechos, falta hypothesis + CI

Quedan:

- ❌ Gap 3 — Secrets encryption (cryptography.fernet + tabla)
- ❌ Gap 4 — Multi-tenancy (tenant_id + RLS)
- ❌ Gap 5 — Rate limiting + Redis cache

---

## Si algo falla

Pegá el output del comando que falla. No intentes "arreglarlo" sin
diagnóstico — la mayoría de los errores son configuración de entorno
(PATH, encoding, .env, Postgres conexión) y se resuelven en 1-2
intercambios.

Errores comunes y sus causas:

| Error | Causa probable | Fix |
|---|---|---|
| `pip-compile` no encuentra requirements.in | Encoding UTF-16 | Reescribir UTF-8 sin BOM |
| `psql: command not found` | PATH no permanente | Ver REPRODUCIBILIDAD.md / setup PATH |
| `connection refused` Postgres | servicio detenido | `services.msc` → arrancar PostgreSQL 18 |
| `discord webhook 401` | webhook rotado/borrado | crear nuevo en Discord, actualizar .env |
| `pytest cache reuses old test names` | pytest-cache | `pytest --cache-clear` |
| `python main.py --once` cuelga | no hay datos en horario US | esperar ventana 9:30am-4pm ET |
| `[SAFETY] HALT activo` al arrancar | killswitch_state tiene triggered=true | UPDATE killswitch_state SET triggered=false |
