"""
Métricas completas para clasificación binaria de trading.

A diferencia de ml_model.py actual (accuracy/precision/recall/F1), aquí se
calcula AUC, PR-AUC, log-loss y Brier score — imprescindibles para decidir
si un modelo financiero tiene señal real. También expone baselines triviales
y permutation importance sobre test (no sobre train).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import numpy as np
from sklearn.inspection import permutation_importance
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)

logger = logging.getLogger(__name__)


def evaluate_binary(
    y_true: np.ndarray,
    y_pred_proba: np.ndarray,
    y_pred: np.ndarray | None = None,
    threshold: float = 0.5,
) -> Dict[str, Any]:
    """
    Calcula el set completo de métricas para clasificación binaria.

    Devuelve dict con AUC, PR-AUC, log-loss, Brier, accuracy, precision,
    recall, f1, base_rate y n_samples. Si y_true tiene una sola clase,
    devuelve {"error": "single_class_in_test", ...}.
    """
    y_true = np.asarray(y_true).astype(int)
    y_pred_proba = np.asarray(y_pred_proba).astype(float)

    if len(np.unique(y_true)) < 2:
        return {
            "error": "single_class_in_test",
            "n_samples": int(len(y_true)),
            "base_rate": float(y_true.mean()) if len(y_true) else 0.0,
        }
    if y_pred is None:
        y_pred = (y_pred_proba >= threshold).astype(int)

    return {
        "auc": float(roc_auc_score(y_true, y_pred_proba)),
        "pr_auc": float(average_precision_score(y_true, y_pred_proba)),
        "log_loss": float(log_loss(y_true, y_pred_proba, labels=[0, 1])),
        "brier": float(brier_score_loss(y_true, y_pred_proba)),
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "base_rate": float(y_true.mean()),
        "n_samples": int(len(y_true)),
    }


def baseline_comparisons(
    y_true: np.ndarray,
    X_test: np.ndarray,
    momentum_col_idx: int | None = None,
    random_state: int = 42,
) -> Dict[str, float]:
    """
    Accuracy de baselines triviales. Tu modelo debería batir al menos tres.

      - always_positive_acc:  predecir siempre 1.
      - always_majority_acc:  predecir la clase mayoritaria.
      - momentum_naive_acc:   predecir 1 si la última feature de "retorno" es > 0.
      - random_same_rate_acc: coin flip con la misma tasa base que y.

    `momentum_col_idx` es el índice de la feature que mejor aproxime el
    retorno reciente (p.ej. 'close' o un retorno). Si es None, se omite
    el baseline momentum.
    """
    y_true = np.asarray(y_true).astype(int)
    X_test = np.asarray(X_test)
    n = len(y_true)
    if n == 0:
        return {}

    base_rate = float(y_true.mean())
    majority = int(base_rate >= 0.5)

    result: Dict[str, float] = {
        "always_positive_acc": float((np.ones(n) == y_true).mean()),
        "always_majority_acc": float((np.full(n, majority) == y_true).mean()),
    }

    if momentum_col_idx is not None and 0 <= momentum_col_idx < X_test.shape[1]:
        # Proxy muy crudo: diff hacia atrás de la columna indicada.
        col = X_test[:, momentum_col_idx]
        # Usamos signo de la diferencia respecto al promedio como proxy direccional
        momentum = (col > np.median(col)).astype(int)
        result["momentum_naive_acc"] = float((momentum == y_true).mean())

    rng = np.random.default_rng(random_state)
    coin = rng.binomial(1, base_rate, size=n)
    result["random_same_rate_acc"] = float((coin == y_true).mean())

    return result


def permutation_importance_on_test(
    model,
    X_test: np.ndarray,
    y_test: np.ndarray,
    feature_names: List[str],
    n_repeats: int = 10,
    scoring: str = "roc_auc",
    random_state: int = 42,
) -> List[Dict[str, Any]]:
    """
    Permutation importance SOBRE TEST, no sobre train.

    La importancia gini del RandomForest se calcula sobre train y
    sobre-estima features que sobreajustan. Permutation importance sobre
    test mide degradación real de AUC al barajar cada feature. Es la
    única importancia defendible.

    Devuelve lista ordenada por importance_mean descendente.
    """
    y_test = np.asarray(y_test).astype(int)
    if len(np.unique(y_test)) < 2:
        logger.warning(
            "permutation_importance_on_test: y_test tiene una sola clase."
        )
        return []

    result = permutation_importance(
        model,
        X_test,
        y_test,
        scoring=scoring,
        n_repeats=n_repeats,
        random_state=random_state,
        n_jobs=-1,
    )
    rows = [
        {
            "feature": f,
            "importance_mean": float(m),
            "importance_std": float(s),
        }
        for f, m, s in zip(
            feature_names, result.importances_mean, result.importances_std
        )
    ]
    rows.sort(key=lambda r: r["importance_mean"], reverse=True)
    return rows
