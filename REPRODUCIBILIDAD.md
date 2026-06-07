# Reproducibilidad — Gap 7

**Objetivo:** que `pip install -r requirements.txt` produzca el mismo
ambiente bit-a-bit, y que entrenar el modelo dos veces con la misma
semilla genere artefactos idénticos. Defendible en un CV o ante un
auditor.

---

## Estado del audit

### `random_state` en modelos críticos

| Archivo | Modelo | Seed |
|---|---|---|
| `ml_model.py:57` | RandomForestClassifier | `config.RF_RANDOM_STATE=42` ✅ |
| `setup_proyecto.py:296` | RandomForestClassifier (scaffold) | `config.RF_RANDOM_STATE=42` ✅ |
| `scripts/validate_model.py:157` | RandomForestClassifier | `config.RF_RANDOM_STATE=42` ✅ |
| `scripts/validate_meta_model.py:163` | RandomForestClassifier | `config.RF_RANDOM_STATE=42` ✅ |
| `borsenhirn/ml/metrics.py:109` | baseline RNG | `np.random.default_rng(random_state)` ✅ |
| `m2_analyst.py:448` | Prophet | sin `random_state` (ver nota abajo) ⚠️ |
| `tests/test_core.py:19` | generador sintético | `np.random.seed(42)` (global, OK para test) ⚠️ |

**Nota Prophet:** la librería no expone `random_state`. Cuando usa MAP
(default) es prácticamente determinista. Si añades `mcmc_samples > 0`
pierdes reproducibilidad. Workaround: fijar `np.random.seed(N)` antes
del `Prophet(...).fit(df)`. Esto se puede envolver en un helper si
empieza a importarte.

**Nota tests:** `np.random.seed(42)` global funciona dentro de un
proceso. Si corres tests en paralelo (`pytest -n auto`) podés tener
carreras no deterministas. Migración recomendada (NO bloqueante):

```python
# Antes
np.random.seed(42)
close = 100 + np.cumsum(np.random.randn(rows) * 0.3)

# Después
rng = np.random.default_rng(42)
close = 100 + np.cumsum(rng.standard_normal(rows) * 0.3)
```

---

## pip-tools: instalación determinista

### Primera vez (setup)

```powershell
# 1. Instalar pip-tools en el venv
pip install pip-tools

# 2. Compilar requirements.txt con hashes
pip-compile --generate-hashes --output-file=requirements.txt requirements.in
pip-compile --generate-hashes --output-file=requirements-dev.txt requirements-dev.in

# 3. Commitear los 4 archivos a git
#    requirements.in, requirements-dev.in, requirements.txt, requirements-dev.txt
```

### Día a día

```powershell
# Instalar / sincronizar ambiente exacto (idempotente):
pip-sync requirements.txt requirements-dev.txt

# Agregar una dependencia nueva:
# 1. Editar requirements.in (añadir la línea)
# 2. Recompilar
pip-compile --generate-hashes --output-file=requirements.txt requirements.in
# 3. Sincronizar
pip-sync requirements.txt requirements-dev.txt
# 4. Commitear requirements.in Y requirements.txt

# Upgrade controlado de UNA dep:
pip-compile --upgrade-package "scikit-learn" --generate-hashes requirements.in

# Upgrade total (trimestral, con cuidado):
pip-compile --upgrade --generate-hashes requirements.in
```

### Qué ganas con los hashes

Cada línea del `requirements.txt` generado tiene un SHA256 del wheel
exacto. Si alguien intenta instalar un paquete modificado (supply-chain
attack tipo `pip install --index-url ...`), pip se niega. También
garantiza que tu build de CI y tu Docker image instalen los mismos
bytes.

Ejemplo de línea generada:

```
scikit-learn==1.5.0 \
    --hash=sha256:abc123... \
    --hash=sha256:def456...
```

---

## `.python-version`

Archivo en la raíz con la versión exacta de Python. Si usás **pyenv**,
`pyenv local` respeta este archivo. Si usás PyCharm, podés configurar
el interpreter a esa versión.

Contenido actual:

```
3.14.0
```

**Acción**: ajustar al valor exacto de tu instalación. Ver con:

```powershell
python --version
# si imprime Python 3.14.1 → editar .python-version a "3.14.1"
```

---

## Verificar reproducibilidad del modelo

```powershell
python scripts/verify_reproducibility.py
```

Entrena el RandomForest dos veces con la misma semilla sobre datos
sintéticos deterministas y compara el hash SHA-256 de los bytes
serializados. Si el modelo no es reproducible, el script imprime las
causas probables y sale con `exit 1`.

Output esperado en caso OK:

```
Verificando reproducibilidad con rows=2000, seed=42
Python: 3.14.0
sklearn: 1.5.0
numpy: 1.26.0
joblib: 1.3.2

--- Run 1 ---
hash A: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

--- Run 2 ---
hash B: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

================================================================
OK — Modelo BIT-IDENTICO entre runs. Reproducibilidad verificada.
================================================================
```

### Si falla

Causas típicas, en orden de probabilidad:

1. **`n_jobs=-1` con scheduler no determinista.** Probar con `n_jobs=1`
   en `config.RF_RANDOM_STATE`-asociadas. Si con 1 es idéntico y con -1
   no, documentalo pero no es bloqueante para el modelo (solo pierdes
   speedup).
2. **Feature con `np.random` sin seed.** Grep por `np.random` en
   `indicators.py`, `features.py` y archivos custom.
3. **sklearn / joblib sin pin.** Si corres `scripts/verify_reproducibility.py`
   en dos máquinas con versiones distintas de sklearn, da diferente.
   Solución: pip-sync sobre `requirements.txt` generado con hashes.

---

## Checklist Gap 7

- [ ] `pip install pip-tools` en el venv.
- [ ] `pip-compile --generate-hashes --output-file=requirements.txt requirements.in`
- [ ] `pip-compile --generate-hashes --output-file=requirements-dev.txt requirements-dev.in`
- [ ] Commitear `.in` y `.txt` a git.
- [ ] Ajustar `.python-version` al valor exacto (`python --version`).
- [ ] `python scripts/verify_reproducibility.py` devuelve exit 0.
- [ ] (Opcional) Migrar `tests/test_core.py` de `np.random.seed` global
      a `np.random.default_rng`.
- [ ] (Opcional) `.github/workflows/ci.yml` corre el verify en cada push.

Cuando estén todos los checks ✔️, Gap 7 cerrado.

---

## CI snippet sugerido (cuando armes GitHub Actions)

```yaml
# .github/workflows/reproducibility.yml
name: reproducibility

on: [push, pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version-file: '.python-version'
      - run: pip install -r requirements.txt -r requirements-dev.txt
      - run: python scripts/verify_reproducibility.py
```

Esto te da un badge verde que defendés en el CV: "CI verifies model
reproducibility bit-by-bit on every commit".
