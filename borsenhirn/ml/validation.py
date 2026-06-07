"""
Purged walk-forward validation para series temporales financieras.

Elimina el data leakage entre folds causado por labels que miran al futuro
(por ejemplo close.shift(-horizon)). El label de la muestra en t=i cubre la
ventana [i, i+horizon], por lo que las muestras t=split-horizon..split-1
deben quitarse del train cuando el test empieza en t=split.

Referencia:
    López de Prado, M. (2018). Advances in Financial Machine Learning.
    Wiley. Cap. 7 — Cross-Validation in Finance.
"""

from __future__ import annotations

import logging
from typing import Iterator, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class PurgedKFold:
    """
    K-Fold temporal con purging y embargo.

    Los folds son bloques contiguos en el tiempo (no aleatorios). Para cada
    fold de test, el train se toma del resto del dataset pero se purgan las
    muestras cuyo label [t, t+label_horizon] solape con el test, y además
    se embarga un buffer post-test para evitar filtrado lento de información.

    Parameters
    ----------
    n_splits : int
        Número de folds. 5 es razonable.
    label_horizon : int
        Cuántas barras hacia adelante mira el label. Debe coincidir con
        config.ML_HORIZON.
    embargo_pct : float
        Fracción del dataset total a embargar tras cada test. 0.01 = 1%.

    Yields
    ------
    (train_idx, test_idx) : tuple[np.ndarray, np.ndarray]
    """

    def __init__(
        self,
        n_splits: int = 5,
        label_horizon: int = 5,
        embargo_pct: float = 0.01,
    ) -> None:
        if n_splits < 2:
            raise ValueError("n_splits debe ser >= 2")
        if label_horizon < 0:
            raise ValueError("label_horizon debe ser >= 0")
        if not (0.0 <= embargo_pct < 1.0):
            raise ValueError("embargo_pct debe estar en [0, 1)")
        self.n_splits = n_splits
        self.label_horizon = label_horizon
        self.embargo_pct = embargo_pct

    def split(self, X) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
        n = len(X)
        if n < self.n_splits * 2:
            raise ValueError(
                f"Dataset demasiado pequeño ({n} filas) para {self.n_splits} folds"
            )
        indices = np.arange(n)
        fold_size = n // self.n_splits
        embargo = int(n * self.embargo_pct)

        for k in range(self.n_splits):
            test_start = k * fold_size
            test_end = test_start + fold_size if k < self.n_splits - 1 else n
            test_idx = indices[test_start:test_end]

            # Ventanas a purgar del train:
            #   - antes del test: las muestras cuyo label [t, t+h] solapa con test
            #   - después del test: las primeras `h + embargo` barras post-test
            left_purge_start = max(0, test_start - self.label_horizon)
            right_purge_end = min(n, test_end + self.label_horizon + embargo)

            train_mask = np.ones(n, dtype=bool)
            train_mask[left_purge_start:right_purge_end] = False
            train_idx = indices[train_mask]

            if len(train_idx) == 0:
                logger.warning(
                    "Fold %d descartado: train vacío tras purging.", k
                )
                continue
            yield train_idx, test_idx

    def get_n_splits(self) -> int:
        return self.n_splits


def walk_forward_split(
    X,
    n_splits: int = 5,
    label_horizon: int = 5,
    embargo_pct: float = 0.01,
    min_train_size: int = 500,
) -> Iterator[Tuple[np.ndarray, np.ndarray]]:
    """
    Walk-forward expanding window con purging.

    El test avanza hacia adelante a lo largo del tiempo; el train es todo
    lo anterior al test menos un buffer de `label_horizon + embargo` barras.
    Simula la realidad: en producción nunca ves el futuro.

    Parameters
    ----------
    X : array-like
        Solo se usa su longitud.
    n_splits : int
        Número de folds hacia adelante (no debe exceder lo que quepa después
        de `min_train_size`).
    label_horizon : int
        Horizonte del label (purge a la izquierda del test).
    embargo_pct : float
        Buffer adicional entre train y test, como fracción del dataset.
    min_train_size : int
        Tamaño mínimo del primer bloque de train.

    Yields
    ------
    (train_idx, test_idx)
    """
    n = len(X)
    if n <= min_train_size + n_splits:
        raise ValueError(
            f"Dataset ({n}) insuficiente para min_train_size={min_train_size} "
            f"y n_splits={n_splits}."
        )
    available = n - min_train_size
    fold_size = max(1, available // n_splits)
    embargo = int(n * embargo_pct)

    for k in range(n_splits):
        test_start = min_train_size + k * fold_size
        test_end = test_start + fold_size if k < n_splits - 1 else n
        train_end = test_start - label_horizon - embargo

        if train_end <= max(50, min_train_size // 2):
            logger.warning(
                "Fold %d saltado: train_end=%d demasiado pequeño.", k, train_end
            )
            continue
        if test_start >= test_end:
            continue

        train_idx = np.arange(0, train_end)
        test_idx = np.arange(test_start, test_end)
        yield train_idx, test_idx
