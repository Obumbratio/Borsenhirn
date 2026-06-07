"""
borsenhirn.ml — utilidades de validación ML sin data leakage.

Componentes:
  - validation: PurgedKFold y walk_forward_split (López de Prado).
  - metrics:    AUC, PR-AUC, Brier, log-loss, permutation importance, baselines.
  - audit:      PSI (drift) y check heurístico de label leakage.
"""

from borsenhirn.ml.validation import PurgedKFold, walk_forward_split
from borsenhirn.ml.metrics import (
    evaluate_binary,
    baseline_comparisons,
    permutation_importance_on_test,
)
from borsenhirn.ml.audit import (
    population_stability_index,
    check_label_leakage,
)

__all__ = [
    "PurgedKFold",
    "walk_forward_split",
    "evaluate_binary",
    "baseline_comparisons",
    "permutation_importance_on_test",
    "population_stability_index",
    "check_label_leakage",
]
