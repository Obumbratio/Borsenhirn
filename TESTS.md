# Plan de tests — Gap 8

**Objetivo:** >70% coverage en lógica crítica, >90% en los módulos de safety
(kill switches, sanity, alerts). El código de trading puede destruir
capital — sin tests es irresponsable tocarlo.

---

## Estado actual

### Archivos de test creados en esta iteración

| Archivo | Tests | Módulo cubierto |
|---|---|---|
| `tests/conftest.py` | — (fixtures) | Fixtures comunes |
| `tests/test_safety_alerts.py` | 13 | `borsenhirn/safety/alerts.py` |
| `tests/test_safety_killswitch.py` | 14 | `borsenhirn/safety/killswitch.py` |
| `tests/test_safety_sanity.py` | 17 | `borsenhirn/safety/sanity.py` |
| `tests/test_circuit_breaker.py` | 12 | `circuit_breaker.py` |
| `tests/test_risk_manager.py` | 16 | `risk_manager.py` |
| `tests/test_ml_validation.py` | 11 | `borsenhirn/ml/validation.py` |
| `tests/test_ml_labeling.py` | 13 | `borsenhirn/ml/labeling.py` |

**Total nuevos**: ~96 tests sobre los componentes que escribimos.

### Archivos de test pre-existentes (ya había)

- `tests/test_core.py` — ~10 tests sobre `TradingStrategy`, `RiskEngine`
  (m3_risk heurístico) y `regime_detector._classify`.

**Total combinado**: ~106 tests.

### Módulos con tests completos ✅

- `borsenhirn/safety/alerts.py` (AlertManager + DiscordChannel)
- `borsenhirn/safety/killswitch.py` (todas las reglas + store + manual halt)
- `borsenhirn/safety/sanity.py` (los 7 checks)
- `borsenhirn/ml/validation.py` y `borsenhirn/ml/labeling.py`
- `circuit_breaker.py`
- `risk_manager.py`
- `strategy.py` y `m3_risk.py` (parcial, del test_core.py original)

### Módulos sin tests todavía ❌

| Módulo | Razón / prioridad |
|---|---|
| `borsenhirn/safety/health.py` | P2 — función simple, baja superficie |
| `borsenhirn/safety/bootstrap.py` | P2 — es cableado, cubrir con integración |
| `borsenhirn/safety/state_store_pg.py` | P3 — requiere Postgres real, usar `pytest.mark.integration` |
| `borsenhirn/ml/metrics.py` | P2 — AUC/PR-AUC/log-loss son sklearn, confianza alta |
| `borsenhirn/ml/audit.py` | P2 — PSI y label_leakage, testear con sintéticos |
| `borsenhirn/ml/meta_model.py` | P2 |
| `borsenhirn/ml/features.py` | P2 |
| `execution.py` | P1 — requiere mock extenso de Alpaca |
| `regime_detector.py` | P1 — cubrir más casos (SIDEWAYS, BEAR, hysteresis completo) |
| `scanner.py` | P2 |
| `data_fetcher.py` | P3 — requiere mock Alpaca |
| `bot_memory_pg.py` | P3 — integración con Postgres |
| `main.py` | P3 — el loop principal, difícil sin e2e |

---

## Cómo correr los tests

### Instalar dependencias de test

Si compilaste con `pip-tools` del Gap 7:

```powershell
pip-sync requirements.txt requirements-dev.txt
```

Si no, instalación directa:

```powershell
pip install pytest pytest-cov hypothesis
```

### Correr todos los tests

```powershell
pytest
```

La config en `pyproject.toml` aplica automáticamente:
- `testpaths = ["tests"]`
- `-ra --strict-markers --tb=short`
- Filtra FutureWarning / DeprecationWarning.

### Solo los tests nuevos de esta iteración

```powershell
pytest tests/test_safety_alerts.py tests/test_safety_sanity.py tests/test_safety_killswitch.py tests/test_circuit_breaker.py tests/test_risk_manager.py tests/test_ml_validation.py tests/test_ml_labeling.py
```

### Con coverage

```powershell
pytest --cov --cov-report=term-missing --cov-report=html
```

Esto genera:
- **Terminal**: resumen con líneas faltantes.
- **HTML**: abrí `htmlcov/index.html` en el navegador — tiene highlight por línea de qué se cubre y qué no.

El target configurado es >70% en `borsenhirn/`, `strategy.py`, `risk_manager.py`,
`circuit_breaker.py`, `ml_model.py`, `regime_detector.py`, `m3_risk.py`.

Archivos excluidos (no suman al % por ser scripts, UI, o scaffolding):
`setup_proyecto.py`, `setup_borsenhirn.py`, `dashboard*.py`, `scripts/*`,
`my_plan.py`, `reporter.py`, `menu.py`, etc.

### Solo un archivo o un test específico

```powershell
pytest tests/test_safety_killswitch.py
pytest tests/test_safety_killswitch.py::test_daily_loss_triggers_when_pnl_exceeds_limit
pytest -k "daily_loss"    # matchea nombre por substring
```

### Por marker

```powershell
pytest -m "not integration"     # skipea tests que tocan DB/Alpaca
pytest -m slow                  # solo los lentos
```

### Parallel (cuando el proyecto crezca)

```powershell
pip install pytest-xdist
pytest -n auto
```

---

## Property-based tests con hypothesis (pendiente, P1)

Hypothesis genera inputs aleatorios que buscan casos que rompen tus
asserts. Es brutalmente eficiente encontrando edge cases.

Ejemplo para `sanity.validate`:

```python
from hypothesis import given, strategies as st
from borsenhirn.safety.sanity import SanityChecker, SanityConfig, OrderContext

@given(
    qty=st.integers(min_value=-100, max_value=100_000),
    price=st.floats(allow_nan=True, allow_infinity=True,
                     min_value=-1000, max_value=1_000_000),
)
def test_property_never_crashes_on_arbitrary_input(qty, price):
    sc = SanityChecker(SanityConfig())
    ctx = OrderContext(
        symbol="AAPL", action="buy", qty=qty, price=price,
        portfolio_value=100_000, watchlist=["AAPL"],
        current_positions={},
    )
    result = sc.validate(ctx)
    # Invariante: siempre devuelve un SanityResult válido
    assert result.ok in (True, False)
    if qty <= 0:
        assert not result.ok
```

Meter 3-5 property-based tests sobre los invariantes más fuertes subiría
la confianza del módulo sin mucho código.

---

## CI sugerido

Crear `.github/workflows/ci.yml`:

```yaml
name: ci

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version-file: '.python-version'
      - name: Install deps
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt
      - name: Lint
        run: ruff check .
      - name: Tests con coverage
        run: pytest --cov --cov-fail-under=70 --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: coverage.xml
```

`--cov-fail-under=70` hace que el CI falle si el coverage total cae por
debajo del 70%. Subí el número a medida que escribas más tests.

---

## Checklist Gap 8

- [ ] `pip install pytest pytest-cov hypothesis`
- [ ] `pytest` — los 106 tests pasan (pueden haber colisiones de cache,
      probá `pytest --cache-clear`).
- [ ] `pytest --cov --cov-report=html` → abrí `htmlcov/index.html`
      y revisá que los módulos de safety están por encima de 90%.
- [ ] (Opcional P1) Escribir 3-5 property-based tests con hypothesis
      para `sanity.validate`, `killswitch.check_all`, `strategy.generate_signal`.
- [ ] (Opcional P1) Tests para `regime_detector` cubriendo BEAR, SIDEWAYS,
      hysteresis completa (3 ciclos para confirmar cambio).
- [ ] (Opcional P2) Mock de `Executor` con mock de `alpaca.trading.client`
      para cubrir `submit_order`, `close_position`, `get_account`.
- [ ] `.github/workflows/ci.yml` con pytest + coverage gate >=70%.

Cuando el target de coverage supere 70% y el CI esté verde, Gap 8 cerrado.

---

## Lo que estos tests te dan, en concreto

1. **Puedes refactorizar con confianza.** Si mañana reescribes
   `strategy.generate_signal` o cambias el flujo de kill switches, los
   tests te avisan si rompiste algo.
2. **Documentación ejecutable.** Los tests son la mejor doc de qué hace
   cada módulo y cómo llamarlo — son ejemplos que compilan.
3. **Defensa en entrevistas.** Un proyecto con tests al 70%+ y CI
   verde es significativamente más creíble para ML Engineer / Data
   Engineer que uno "funciona en mi máquina".
4. **Base para property-based y fuzzing.** Con el esqueleto armado,
   agregar hypothesis es trivial — y eso es senior-level testing.

---

## Lo que NO cubren estos tests (conocer limitaciones)

- **Integración end-to-end.** No testean que `main.py --once` corra un
  ciclo completo sin crashes. Para eso necesitás mocks de Alpaca y
  Postgres muy elaborados, o un ambiente de testing con contenedores.
- **Performance.** No miden latencia ni memoria. Pytest-benchmark sería
  otro sprint.
- **Concurrencia.** El bot es single-threaded; no hay tests de
  threading/asyncio. Cuando metas el AlertManager a un loop async, vas
  a querer tests específicos.
