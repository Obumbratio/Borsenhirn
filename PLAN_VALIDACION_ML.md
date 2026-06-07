# Plan de validación del modelo ML — Börsenhirn

**Fecha:** 2026-04-24
**Alcance:** Validar si el modelo `RandomForestClassifier` en `ml_model.py` tiene señal real o está sobreentrenado / con data leakage. Reconstruir toda la metodología de evaluación usando walk-forward con purging y embargo (López de Prado, *Advances in Financial Machine Learning*).

---

## 1. Diagnóstico del estado actual

### 1.1. Lo que se reportó vs lo que hay

| Reportado | Realidad en el código |
|---|---|
| M3 = XGBoost AUC=0.98 + SHAP | `m3_risk.py` es un scoring heurístico con pesos fijos. Los "shap_factors" son contribuciones de reglas, no SHAP. No hay XGBoost en el repo. |
| AUC=0.98 | `ml_model.py` nunca calcula AUC. Solo accuracy, precision, recall, F1. |
| Walk-forward en backtest | `backtest.py:29` entrena con todo el df y luego `backtest.py:47` evalúa sobre el mismo df. Leakage total. |
| Validación robusta | Split 80/20 temporal simple, sin purging, sin embargo, sin CV. |

### 1.2. Problemas concretos por archivo

**`ml_model.py`**
- Línea 50: `split = int(len(X_raw) * 0.8)` — un único split, no hay cross-validation.
- Línea 42: `((fut - df["close"]) / df["close"] >= threshold).astype(int)` — label con ventana `horizon=5` sin purging.
- Líneas 62–67: métricas sin AUC, sin PR-AUC, sin log-loss, sin Brier.
- `prepare_features` (líneas 34–38): hace `StandardScaler().fit_transform(X)` sobre TODO el df. No se usa en `train()`, pero si alguien lo llama desde fuera para validación, introduce leakage del scaler. Eliminar o marcar como privado.

**`backtest.py`**
- Línea 29: `model.train(df)` — entrena con el dataset completo.
- Línea 47: `for i in range(min_w, len(df))` — evalúa sobre el mismo dataset.
- Resultado: el "backtest" mide ajuste en muestra, no generalización. Cualquier Sharpe/win-rate que reporte es mentira.

**`config.py`**
- `DB_PASSWORD = os.getenv("DB_PASSWORD", "uriel")` — fallback con contraseña real. Arréglalo antes de público/SaaS. Aparte del tema ML, anótalo.

### 1.3. Lo que SÍ está bien (no tocar)

- `indicators.py`: todos los rolling windows son right-aligned, no hay lookahead bias en features.
- `ml_model.py` líneas 53–55: el `StandardScaler` se fit solo sobre train y luego transforma test. Correcto.
- `RF_RANDOM_STATE=42` fijo. Bien para reproducibilidad.
- Circuit breaker en `data_fetcher.py`. Bien.

---

## 2. Arquitectura correcta de validación

### 2.1. Concepto: por qué el split 80/20 miente en series temporales

Con label `y[t] = f(close[t+5])`, la muestra en `t=split-1` tiene target en `t=split+4`. La primera muestra de test está en `t=split`, pero su target está en `t=split+5`. Si entrenas en `[0, split-1]` y testeas en `[split, N]`, los targets de train cubren `[5, split+4]` y los de test cubren `[split+5, N+4]`. **Solapan en `[split, split+4]`**. El modelo memoriza microestructura del solape.

Solución: **purging + embargo**.

- **Purging:** quitar del training las muestras cuyo label solapa temporalmente con la ventana de test.
- **Embargo:** además, quitar un buffer extra de `h` barras después del test para que el próximo fold no vea información próxima.

### 2.2. Esquema que vamos a implementar

Tres niveles de validación, ordenados de más estricto a más útil:

1. **Purged walk-forward expanding window**: el test se mueve hacia adelante; train siempre es todo lo anterior al test menos el purge. Simula el mundo real.
2. **Purged K-Fold (López de Prado)**: K=5 bloques temporales contiguos. Para cada fold, train = resto con purging. Sirve para CV robusto de hiperparámetros.
3. **Combinatorial Purged CV (opcional v2)**: genera múltiples paths, sirve para intervalos de confianza de Sharpe. Más costoso.

### 2.3. Métricas a calcular (TODAS)

- `roc_auc_score`
- `average_precision_score` (PR-AUC, más relevante si la clase positiva es minoritaria)
- `log_loss`
- `brier_score_loss` (calibración)
- `accuracy`, `precision`, `recall`, `f1` (por compatibilidad)
- **Permutation importance** sobre test: qué features aportan de verdad.
- **Feature importance gini** del RF: para comparar con la permutation.
- **PSI (Population Stability Index)** entre train y test por feature: detecta drift.

### 2.4. Criterios de aceptación honestos

Después del walk-forward purged con embargo:

| AUC test promedio | Interpretación |
|---|---|
| < 0.52 | Ruido. Tirar el modelo, cambiar labeling/features. |
| 0.52 – 0.55 | Señal débil. Probar meta-labeling (López de Prado cap. 3) o triple-barrier. |
| 0.55 – 0.62 | **Rango realista** para equities 1h con features técnicas. Usable. |
| 0.62 – 0.70 | Sospechoso. Auditar leakage residual (ventanas, news, earnings). |
| > 0.70 | Casi seguro leakage. Auditoría completa obligatoria. |

Adicional: el modelo debe batir una baseline trivial (predecir la clase mayoritaria, o la dirección del último retorno). Si no bate baseline, es ruido aunque AUC sea 0.60.

---

## 3. Plan de implementación por archivos

### 3.1. Nuevos archivos a crear

```
borsenhirn/
  ml/
    __init__.py
    validation.py        # PurgedKFold, walk_forward_split, embargo
    metrics.py           # AUC, PR-AUC, log-loss, Brier, permutation importance
    audit.py             # Leakage checks, PSI, feature importance diff
    labeling.py          # Labels: fixed-horizon (actual) + triple-barrier (futuro)
scripts/
  validate_model.py      # Entry point: corre el audit completo
  compare_baselines.py   # Modelo vs baselines triviales
results/
  validation/
    walk_forward_aucs.csv
    permutation_importance.csv
    leakage_audit.json
    report.html
```

### 3.2. Archivos a modificar

- **`ml_model.py`**
  - Añadir método `train_walk_forward(df, n_splits=5, embargo_pct=0.01)` que usa el `PurgedKFold` nuevo.
  - Añadir `evaluate(df)` que devuelve todas las métricas (AUC incluido).
  - Dejar `train(df)` actual pero marcado como `# legacy: produce leaky metrics`.

- **`backtest.py`**
  - Refactor del loop: dentro del `for i in range(min_w, len(df))`, reentrenar el modelo **solo con datos `df.iloc[:i - horizon - embargo]`** cada N barras (retrain cadence). Cachear el modelo entre retrains.
  - Añadir walk-forward retraining cadence como param CLI.

- **`config.py`**
  - Añadir `VALIDATION_N_SPLITS = 5`, `VALIDATION_EMBARGO_PCT = 0.01`, `RETRAIN_CADENCE_BARS = 500`.
  - Quitar fallback `DB_PASSWORD="uriel"` — dejar vacío y fallar duro si no hay env.

### 3.3. Orden de trabajo (estimado en días)

| # | Tarea | Archivos | Tiempo | Bloquea a |
|---|---|---|---|---|
| 1 | Crear `borsenhirn/ml/validation.py` con `PurgedKFold` y `walk_forward_split` | nuevo | 0.5d | 2, 3, 4 |
| 2 | Crear `borsenhirn/ml/metrics.py` con AUC, PR-AUC, log-loss, Brier, permutation importance | nuevo | 0.3d | 4 |
| 3 | Crear `borsenhirn/ml/audit.py` con PSI y check de leakage (overlap de ventanas) | nuevo | 0.5d | 4 |
| 4 | Crear `scripts/validate_model.py` que entrena RF con walk-forward purged y genera report | nuevo | 0.5d | decisión GO/NO-GO |
| 5 | **Correr validación y leer métricas** | — | 0.2d | 6 |
| 6 | Si AUC < 0.55: probar triple-barrier labeling en `borsenhirn/ml/labeling.py` | nuevo | 1d | — |
| 7 | Si AUC >= 0.55: fix `backtest.py` para retraining cadence sin leakage | modificar | 1d | — |
| 8 | Integrar `evaluate()` a `ml_model.py` y correr antes de cada deploy | modificar | 0.3d | — |

**Total estimado: 3–5 días hábiles** para decidir si el modelo sirve.

---

## 4. Snippets de código clave

### 4.1. `borsenhirn/ml/validation.py`

```python
"""
Purged walk-forward validation para series temporales financieras.
Referencia: López de Prado, "Advances in Financial ML", cap. 7.
"""
import numpy as np
import pandas as pd
from typing import Iterator, Tuple


class PurgedKFold:
    """
    K-Fold temporal con purging: elimina del train las muestras cuyo label
    solape temporalmente con el test. Opcionalmente aplica embargo post-test.

    Args:
        n_splits: número de folds (default 5).
        label_horizon: cuántas barras hacia adelante mira el label.
                       Iguale a config.ML_HORIZON.
        embargo_pct: fracción del dataset a embargar después de cada test.
                     0.01 = 1% extra de barras purgadas tras test.
    """
    def __init__(self, n_splits: int = 5, label_horizon: int = 5,
                 embargo_pct: float = 0.01):
        self.n_splits = n_splits
        self.label_horizon = label_horizon
        self.embargo_pct = embargo_pct

    def split(self, X: np.ndarray) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        n = len(X)
        indices = np.arange(n)
        fold_size = n // self.n_splits
        embargo = int(n * self.embargo_pct)

        for k in range(self.n_splits):
            test_start = k * fold_size
            test_end = test_start + fold_size if k < self.n_splits - 1 else n
            test_idx = indices[test_start:test_end]

            # Purging: quitar muestras de train cuyo label [t, t+h] solape con test
            left_purge_end = test_start
            left_purge_start = max(0, test_start - self.label_horizon)
            right_purge_start = test_end
            right_purge_end = min(n, test_end + self.label_horizon + embargo)

            train_mask = np.ones(n, dtype=bool)
            train_mask[left_purge_start:right_purge_end] = False
            train_idx = indices[train_mask]

            yield train_idx, test_idx


def walk_forward_split(X: np.ndarray, n_splits: int = 5,
                       label_horizon: int = 5, embargo_pct: float = 0.01,
                       min_train_size: int = 500):
    """
    Walk-forward expanding window con purging.
    Test siempre es hacia adelante; train crece con el tiempo.
    """
    n = len(X)
    fold_size = (n - min_train_size) // n_splits
    embargo = int(n * embargo_pct)

    for k in range(n_splits):
        test_start = min_train_size + k * fold_size
        test_end = test_start + fold_size if k < n_splits - 1 else n
        train_end = test_start - label_horizon - embargo  # purge
        if train_end < min_train_size // 2:
            continue
        train_idx = np.arange(0, train_end)
        test_idx = np.arange(test_start, test_end)
        yield train_idx, test_idx
```

### 4.2. `borsenhirn/ml/metrics.py`

```python
import numpy as np
from sklearn.metrics import (roc_auc_score, average_precision_score,
                              log_loss, brier_score_loss,
                              accuracy_score, precision_score,
                              recall_score, f1_score)
from sklearn.inspection import permutation_importance


def evaluate_binary(y_true, y_pred_proba, y_pred=None, threshold=0.5):
    """Métricas completas para clasificación binaria."""
    if y_pred is None:
        y_pred = (y_pred_proba >= threshold).astype(int)
    # Guard: necesitamos ambas clases en y_true para AUC
    if len(np.unique(y_true)) < 2:
        return {"error": "single_class_in_test", "n_samples": len(y_true)}
    return {
        "auc": roc_auc_score(y_true, y_pred_proba),
        "pr_auc": average_precision_score(y_true, y_pred_proba),
        "log_loss": log_loss(y_true, y_pred_proba, labels=[0, 1]),
        "brier": brier_score_loss(y_true, y_pred_proba),
        "accuracy": accuracy_score(y_true, y_pred),
        "precision": precision_score(y_true, y_pred, zero_division=0),
        "recall": recall_score(y_true, y_pred, zero_division=0),
        "f1": f1_score(y_true, y_pred, zero_division=0),
        "base_rate": float(y_true.mean()),
        "n_samples": len(y_true),
    }


def baseline_comparisons(y_true, X_test, last_return_col_idx):
    """Baselines triviales que TU modelo debe batir."""
    n = len(y_true)
    # 1. Always-positive
    always_pos = np.ones(n)
    # 2. Always-majority
    majority = int(y_true.mean() >= 0.5)
    always_maj = np.full(n, majority)
    # 3. Follow last return (momentum naive)
    last_ret = X_test[:, last_return_col_idx]
    momentum = (last_ret > 0).astype(int)
    # 4. Coin flip with same base rate
    rng = np.random.default_rng(42)
    coin = rng.binomial(1, y_true.mean(), size=n)
    return {
        "always_positive_acc": (always_pos == y_true).mean(),
        "always_majority_acc": (always_maj == y_true).mean(),
        "momentum_naive_acc": (momentum == y_true).mean(),
        "random_same_rate_acc": (coin == y_true).mean(),
    }


def permutation_importance_on_test(model, X_test, y_test, feature_names,
                                   n_repeats=10, random_state=42):
    """Permutation importance real sobre test (no train como el gini del RF)."""
    result = permutation_importance(model, X_test, y_test,
                                    scoring="roc_auc",
                                    n_repeats=n_repeats,
                                    random_state=random_state,
                                    n_jobs=-1)
    return [
        {"feature": f, "importance_mean": float(m), "importance_std": float(s)}
        for f, m, s in sorted(
            zip(feature_names, result.importances_mean, result.importances_std),
            key=lambda x: -x[1]
        )
    ]
```

### 4.3. `borsenhirn/ml/audit.py`

```python
import numpy as np
import pandas as pd


def population_stability_index(train: np.ndarray, test: np.ndarray,
                               n_bins: int = 10) -> float:
    """PSI > 0.25 = feature drift significativo entre train y test."""
    breakpoints = np.nanquantile(train, np.linspace(0, 1, n_bins + 1))
    breakpoints[0], breakpoints[-1] = -np.inf, np.inf
    train_pct = np.histogram(train, bins=breakpoints)[0] / len(train)
    test_pct = np.histogram(test, bins=breakpoints)[0] / len(test)
    # Evitar log(0)
    train_pct = np.where(train_pct == 0, 1e-6, train_pct)
    test_pct = np.where(test_pct == 0, 1e-6, test_pct)
    return float(np.sum((test_pct - train_pct) * np.log(test_pct / train_pct)))


def check_label_leakage(df: pd.DataFrame, label_horizon: int) -> dict:
    """Verifica que los features NO usen información posterior a la barra actual."""
    warnings = []
    # Heurística: si un feature tiene correlación > 0.95 con close.shift(-h) para h>0,
    # es probable lookahead.
    close = df["close"]
    for col in df.columns:
        if col in ("open", "high", "low", "close", "volume"):
            continue
        for h in range(1, label_horizon + 1):
            future = close.shift(-h)
            common = df[col].notna() & future.notna()
            if common.sum() < 30:
                continue
            corr = df.loc[common, col].corr(future.loc[common])
            if abs(corr) > 0.95:
                warnings.append({
                    "feature": col,
                    "horizon": h,
                    "corr_with_future_close": float(corr),
                })
    return {"warnings": warnings, "clean": len(warnings) == 0}
```

### 4.4. `scripts/validate_model.py`

```python
"""
Valida el Random Forest con walk-forward purged CV + audit de leakage.
Uso: python scripts/validate_model.py --symbol SPY --start 2020-01-01
"""
import argparse, json, logging, os
from datetime import datetime, timezone
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

import config
from logger import setup_logging
from data_fetcher import DataFetcher
from indicators import add_all_indicators
from ml_model import FEATURE_COLS
from borsenhirn.ml.validation import PurgedKFold, walk_forward_split
from borsenhirn.ml.metrics import (evaluate_binary, baseline_comparisons,
                                    permutation_importance_on_test)
from borsenhirn.ml.audit import population_stability_index, check_label_leakage

setup_logging()
logger = logging.getLogger(__name__)


def create_labels(df, horizon=config.ML_HORIZON, threshold=config.ML_THRESHOLD):
    fut = df["close"].shift(-horizon)
    return ((fut - df["close"]) / df["close"] >= threshold).astype(int)


def main(symbol, start, end, timeframe, n_splits, embargo):
    df = DataFetcher().get_historical(symbol, start, end, timeframe)
    if df.empty:
        logger.error("Sin datos"); return
    df = add_all_indicators(df)

    # Audit de leakage PRIMERO
    leakage = check_label_leakage(df, config.ML_HORIZON)
    if not leakage["clean"]:
        logger.warning(f"ALERTA LEAKAGE: {leakage['warnings']}")

    y = create_labels(df)
    feat_cols = [c for c in FEATURE_COLS if c in df.columns]
    valid = y.dropna().index
    X = df.loc[valid, feat_cols].values
    y = y.loc[valid].values

    # ── Walk-forward expanding ─────────────────────────────────
    fold_metrics = []
    last_ret_idx = feat_cols.index("close")  # proxy para baseline momentum
    for fold, (tr_idx, te_idx) in enumerate(walk_forward_split(
            X, n_splits=n_splits, label_horizon=config.ML_HORIZON,
            embargo_pct=embargo, min_train_size=max(500, len(X) // 4))):
        scaler = StandardScaler()
        Xtr = scaler.fit_transform(X[tr_idx])
        Xte = scaler.transform(X[te_idx])
        ytr, yte = y[tr_idx], y[te_idx]

        model = RandomForestClassifier(
            n_estimators=config.RF_N_ESTIMATORS,
            max_depth=config.RF_MAX_DEPTH,
            random_state=config.RF_RANDOM_STATE, n_jobs=-1)
        model.fit(Xtr, ytr)

        proba = model.predict_proba(Xte)[:, 1]
        m = evaluate_binary(yte, proba)
        m["fold"] = fold
        m["train_size"], m["test_size"] = len(tr_idx), len(te_idx)

        if "error" not in m:
            base = baseline_comparisons(yte, Xte, last_ret_idx)
            m.update(base)
            # Permutation importance solo en último fold (costoso)
            if fold == n_splits - 1:
                m["perm_importance"] = permutation_importance_on_test(
                    model, Xte, yte, feat_cols)
                # PSI por feature
                m["psi"] = {feat_cols[i]: population_stability_index(
                    X[tr_idx][:, i], X[te_idx][:, i]) for i in range(X.shape[1])}
        fold_metrics.append(m)
        logger.info(f"Fold {fold}: AUC={m.get('auc', 'N/A'):.4f} "
                    f"Brier={m.get('brier', 0):.4f} n_test={m.get('n_samples', 0)}")

    # Resumen
    aucs = [m["auc"] for m in fold_metrics if "auc" in m]
    summary = {
        "symbol": symbol,
        "timeframe": timeframe,
        "n_folds_valid": len(aucs),
        "auc_mean": float(np.mean(aucs)) if aucs else None,
        "auc_std": float(np.std(aucs)) if aucs else None,
        "auc_min": float(np.min(aucs)) if aucs else None,
        "auc_max": float(np.max(aucs)) if aucs else None,
        "leakage_audit": leakage,
        "folds": fold_metrics,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs("results/validation", exist_ok=True)
    out = f"results/validation/{symbol}_walk_forward.json"
    with open(out, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Reporte guardado: {out}")

    print("\n" + "=" * 60)
    print(f"RESULTADOS WALK-FORWARD PURGED — {symbol}")
    print("=" * 60)
    print(f"AUC mean ± std: {summary['auc_mean']:.4f} ± {summary['auc_std']:.4f}")
    print(f"AUC rango:      [{summary['auc_min']:.4f}, {summary['auc_max']:.4f}]")
    print("Interpretación:")
    if summary["auc_mean"] is None:
        print("  → Sin datos suficientes")
    elif summary["auc_mean"] < 0.52:
        print("  → RUIDO. El modelo no aprende. Cambiar features/labels.")
    elif summary["auc_mean"] < 0.55:
        print("  → Señal muy débil. Probar triple-barrier o meta-labeling.")
    elif summary["auc_mean"] < 0.62:
        print("  → Señal real. Usable para trading con buen risk management.")
    elif summary["auc_mean"] < 0.70:
        print("  → SOSPECHOSO. Auditar leakage residual.")
    else:
        print("  → CASI SEGURO LEAKAGE. NO usar en producción hasta auditar.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--symbol", default=config.SYMBOL)
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    p.add_argument("--timeframe", default=config.TIMEFRAME)
    p.add_argument("--n_splits", type=int, default=5)
    p.add_argument("--embargo", type=float, default=0.01)
    a = p.parse_args()
    main(a.symbol,
         datetime.fromisoformat(a.start).replace(tzinfo=timezone.utc),
         datetime.fromisoformat(a.end).replace(tzinfo=timezone.utc),
         a.timeframe, a.n_splits, a.embargo)
```

---

## 5. Fix de `backtest.py` (sin leakage) — pseudocódigo

```python
# Antes (LEAKY):
model.train(df)  # ve todo el futuro
for i in range(min_w, len(df)):
    sig = strategy.generate_signal(df.iloc[:i])  # modelo ya vio i+

# Después (WALK-FORWARD REAL):
RETRAIN_EVERY = config.RETRAIN_CADENCE_BARS  # p.ej. 500 barras
EMBARGO_BARS = config.ML_HORIZON + int(len(df) * 0.005)

last_trained_i = 0
model = TradingModel()

for i in range(min_w, len(df)):
    # Re-entrenar periódicamente, SOLO con datos previos - embargo
    if i - last_trained_i >= RETRAIN_EVERY:
        train_end = i - EMBARGO_BARS
        if train_end > min_w:
            model.train(df.iloc[:train_end])
            last_trained_i = i

    sig = strategy.generate_signal(df.iloc[:i])  # modelo solo vio [:train_end]
    # ... resto del loop igual
```

---

## 6. Qué hacer si el AUC walk-forward es malo (<0.55)

1. **Triple-barrier labeling** (López de Prado cap. 3): en vez de `close[t+5] / close[t] >= 0.005`, definir tres barreras (take-profit, stop-loss, tiempo máximo) y el label es qué barrera se toca primero. Mucho más cercano a la realidad del trade.

2. **Meta-labeling**: usa tu modelo primario (reglas técnicas de `strategy.py`) para decidir la dirección, y entrena el ML solo para decidir *cuánto apostar* (filtro de confianza). Reduce el espacio de búsqueda, suele mejorar Sharpe aunque no AUC.

3. **Features adicionales que estás ignorando**:
   - Volatilidad realizada intraday.
   - Orderflow imbalance (si consigues nivel 2).
   - VIX delta (tienes `market_context.py`, úsalo como feature).
   - Distancia a resistencia/soporte (rolling max/min).
   - Gap overnight (si pasas a 1D).
   - Seasonality (día de semana, hora).
   - Sector momentum relativo (SPY vs sector ETF del símbolo).

4. **Cambiar horizonte**: `ML_HORIZON=5` con `1Hour` = 5h. Prueba `1Day` con `ML_HORIZON=5` (5 días) — menor ratio señal/ruido pero labels menos ruidosos.

5. **Meta-modelo por régimen**: modelo distinto para BEAR / BULL / SIDEWAYS. Tu detector ya los tiene.

---

## 7. Checklist antes de declarar el modelo "listo"

- [ ] Walk-forward purged AUC mean >= 0.55 con std razonable.
- [ ] El modelo bate a los 4 baselines triviales en al menos 3 de 5 folds.
- [ ] Permutation importance: al menos 3 features con importance > 0.005.
- [ ] PSI < 0.25 para todos los features top-10 (no hay drift destructivo).
- [ ] `check_label_leakage` devuelve `clean=True`.
- [ ] Brier score < base_rate * (1 - base_rate) (modelo calibrado mejor que clase media).
- [ ] Backtest con retraining cadence — Sharpe > 0.5 neto de comisiones.
- [ ] Resultados documentados en `results/validation/` y commiteados.

---

## 8. Lo que NO voy a tocar en este sprint

- El M3 heurístico en `m3_risk.py`: funciona como filtro, no requiere validación ML.
- Prophet en M2: la validación de forecasts temporales es otro mundo (MAPE, MASE, Diebold-Mariano). Sprint aparte.
- Claude API / M1 / M4: no son modelos predictivos cuantitativos.

---

**Próximo paso cuando estés listo:** puedo crear los 4 archivos nuevos (`validation.py`, `metrics.py`, `audit.py`, `validate_model.py`) con el código completo en tu proyecto, para que solo corras:

```bash
python scripts/validate_model.py --symbol SPY --start 2020-01-01
```

y veas en pantalla el veredicto real del modelo. Dime cuando quieras que empuje el código.
