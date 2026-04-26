"""Tests de borsenhirn.ml.metrics."""

from __future__ import annotations

import numpy as np
import pytest
from sklearn.ensemble import RandomForestClassifier

from borsenhirn.ml.metrics import (
    baseline_comparisons,
    evaluate_binary,
    permutation_importance_on_test,
)


# ── evaluate_binary ──────────────────────────────────────────


def test_evaluate_binary_returns_all_keys():
    y = np.array([0, 1, 1, 0, 1, 0, 1, 0])
    p = np.array([0.1, 0.9, 0.8, 0.2, 0.7, 0.3, 0.6, 0.4])
    m = evaluate_binary(y, p)
    for k in ("auc", "pr_auc", "log_loss", "brier",
              "accuracy", "precision", "recall", "f1",
              "base_rate", "n_samples"):
        assert k in m


def test_evaluate_binary_perfect_classifier_auc_one():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.1, 0.2, 0.9, 0.95])
    m = evaluate_binary(y, p)
    assert m["auc"] == 1.0
    assert m["accuracy"] == 1.0


def test_evaluate_binary_random_auc_near_half():
    rng = np.random.default_rng(42)
    y = rng.integers(0, 2, 1000)
    p = rng.random(1000)
    m = evaluate_binary(y, p)
    # Random => AUC cercano a 0.5
    assert 0.4 < m["auc"] < 0.6


def test_evaluate_binary_single_class_returns_error():
    y = np.zeros(50, dtype=int)
    p = np.random.rand(50)
    m = evaluate_binary(y, p)
    assert m.get("error") == "single_class_in_test"
    assert m["n_samples"] == 50


def test_evaluate_binary_threshold_changes_predictions():
    y = np.array([0, 0, 1, 1])
    p = np.array([0.4, 0.6, 0.45, 0.55])
    m_low = evaluate_binary(y, p, threshold=0.3)   # casi todo positivo
    m_high = evaluate_binary(y, p, threshold=0.7)  # casi todo negativo
    # Los y_pred derivados varían; AUC y log_loss no dependen del threshold
    assert m_low["auc"] == m_high["auc"]


def test_evaluate_binary_handles_explicit_y_pred():
    y = np.array([0, 1, 1, 0])
    p = np.array([0.2, 0.8, 0.7, 0.3])
    pred = np.array([0, 1, 1, 0])
    m = evaluate_binary(y, p, y_pred=pred)
    assert m["accuracy"] == 1.0


# ── baseline_comparisons ─────────────────────────────────────


def test_baseline_comparisons_all_keys_present():
    y = np.array([0, 1, 1, 0, 1])
    X = np.random.default_rng(0).standard_normal((5, 3))
    out = baseline_comparisons(y, X, momentum_col_idx=0)
    for k in ("always_positive_acc", "always_majority_acc",
              "momentum_naive_acc", "random_same_rate_acc"):
        assert k in out


def test_baseline_comparisons_empty_returns_empty_dict():
    y = np.array([], dtype=int)
    X = np.zeros((0, 3))
    assert baseline_comparisons(y, X) == {}


def test_baseline_comparisons_skip_momentum_when_no_idx():
    y = np.array([0, 1, 0])
    X = np.zeros((3, 3))
    out = baseline_comparisons(y, X, momentum_col_idx=None)
    assert "momentum_naive_acc" not in out


def test_baseline_always_positive_matches_base_rate():
    y = np.array([0, 0, 0, 1, 1])
    X = np.zeros((5, 2))
    out = baseline_comparisons(y, X)
    # always_positive acierta solo en clase 1
    assert out["always_positive_acc"] == pytest.approx(0.4)


# ── permutation_importance_on_test ───────────────────────────


def test_permutation_importance_returns_sorted_list():
    rng = np.random.default_rng(0)
    X_tr = rng.standard_normal((300, 4))
    y_tr = (X_tr[:, 0] + rng.standard_normal(300) * 0.3 > 0).astype(int)
    X_te = rng.standard_normal((100, 4))
    y_te = (X_te[:, 0] + rng.standard_normal(100) * 0.3 > 0).astype(int)
    m = RandomForestClassifier(n_estimators=20, random_state=42, n_jobs=1)
    m.fit(X_tr, y_tr)
    imp = permutation_importance_on_test(
        m, X_te, y_te, ["f0", "f1", "f2", "f3"], n_repeats=3,
    )
    assert len(imp) == 4
    # Sorted descending
    means = [r["importance_mean"] for r in imp]
    assert means == sorted(means, reverse=True)
    # f0 debe ser top (es la única feature con señal)
    assert imp[0]["feature"] == "f0"


def test_permutation_importance_single_class_returns_empty(caplog):
    """Si y_test tiene una sola clase, devuelve []."""
    X_te = np.zeros((20, 3))
    y_te = np.zeros(20, dtype=int)

    class FakeModel:
        def predict(self, X): return np.zeros(len(X))
        def predict_proba(self, X): return np.zeros((len(X), 2))

    out = permutation_importance_on_test(
        FakeModel(), X_te, y_te, ["a", "b", "c"], n_repeats=2,
    )
    assert out == []
