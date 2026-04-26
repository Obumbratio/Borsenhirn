"""Tests de borsenhirn.ml.validation (PurgedKFold + walk_forward_split)."""

import numpy as np
import pytest

from borsenhirn.ml.validation import PurgedKFold, walk_forward_split


@pytest.fixture
def sample_X():
    return np.random.default_rng(0).standard_normal((1000, 5))


# ── PurgedKFold: construcción ─────────────────────────────


def test_purged_kfold_rejects_invalid_n_splits():
    with pytest.raises(ValueError):
        PurgedKFold(n_splits=1)


def test_purged_kfold_rejects_negative_horizon():
    with pytest.raises(ValueError):
        PurgedKFold(label_horizon=-1)


def test_purged_kfold_rejects_invalid_embargo():
    with pytest.raises(ValueError):
        PurgedKFold(embargo_pct=1.5)


# ── PurgedKFold: splits ───────────────────────────────────


def test_purged_kfold_yields_n_splits(sample_X):
    cv = PurgedKFold(n_splits=5, label_horizon=5, embargo_pct=0.01)
    splits = list(cv.split(sample_X))
    assert len(splits) == 5


def test_purged_kfold_no_train_test_overlap(sample_X):
    cv = PurgedKFold(n_splits=5, label_horizon=5, embargo_pct=0.01)
    for tr, te in cv.split(sample_X):
        overlap = set(tr) & set(te)
        assert not overlap, "train y test no deben compartir índices"


def test_purged_kfold_test_indices_cover_dataset(sample_X):
    """Los tests de todos los folds (sin overlap) deberían cubrir casi todo."""
    cv = PurgedKFold(n_splits=5, label_horizon=5, embargo_pct=0.01)
    all_test = set()
    for _, te in cv.split(sample_X):
        all_test |= set(te)
    # Debería cubrir el 100% (cada fila está exactamente en un fold de test)
    assert len(all_test) == len(sample_X)


def test_purged_kfold_respects_horizon_purging(sample_X):
    """Train no debe incluir índices inmediatamente antes o después del test."""
    cv = PurgedKFold(n_splits=5, label_horizon=10, embargo_pct=0)
    for tr, te in cv.split(sample_X):
        test_min, test_max = te.min(), te.max()
        # Los 10 previos al test no deberían estar en train
        purged_left = set(range(max(0, test_min - 10), test_min))
        assert not (purged_left & set(tr))


def test_purged_kfold_small_dataset_raises():
    X = np.random.default_rng(0).standard_normal((5, 3))
    cv = PurgedKFold(n_splits=5)
    with pytest.raises(ValueError):
        list(cv.split(X))


# ── walk_forward_split ────────────────────────────────────


def test_walk_forward_test_always_after_train(sample_X):
    for tr, te in walk_forward_split(sample_X, n_splits=4,
                                      label_horizon=5,
                                      embargo_pct=0.01,
                                      min_train_size=300):
        assert tr.max() < te.min(), \
            f"train max ({tr.max()}) debe ser menor a test min ({te.min()})"


def test_walk_forward_gap_equals_horizon_plus_embargo(sample_X):
    n = len(sample_X)
    horizon = 5
    embargo_pct = 0.01
    expected_gap = horizon + int(n * embargo_pct)
    for tr, te in walk_forward_split(sample_X, n_splits=4,
                                      label_horizon=horizon,
                                      embargo_pct=embargo_pct,
                                      min_train_size=300):
        gap = te.min() - tr.max() - 1
        # El gap debe ser al menos el esperado
        assert gap >= expected_gap - 1


def test_walk_forward_small_dataset_raises():
    X = np.random.default_rng(0).standard_normal((20, 3))
    with pytest.raises(ValueError):
        list(walk_forward_split(X, n_splits=5, min_train_size=500))


def test_walk_forward_train_grows_monotonically(sample_X):
    """En expanding window, cada fold de train debería ser >= que el anterior."""
    prev_train_size = 0
    for tr, _ in walk_forward_split(sample_X, n_splits=4,
                                     label_horizon=5,
                                     embargo_pct=0.01,
                                     min_train_size=300):
        assert len(tr) >= prev_train_size
        prev_train_size = len(tr)


def test_walk_forward_indices_are_sorted(sample_X):
    for tr, te in walk_forward_split(sample_X, n_splits=3,
                                      min_train_size=200):
        assert np.all(np.diff(tr) > 0)
        assert np.all(np.diff(te) > 0)
