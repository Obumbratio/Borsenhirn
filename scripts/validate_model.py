"""
Valida el modelo de trading (Random Forest de ml_model.py) usando walk-forward
expanding con purging y embargo. Produce un reporte JSON con AUC, PR-AUC,
Brier, baselines triviales, permutation importance y PSI por feature.

Uso:
    python scripts/validate_model.py --symbol SPY --start 2020-01-01

Salida:
    results/validation/<SYMBOL>_walk_forward.json
    Veredicto en consola (RUIDO / SEÑAL DÉBIL / SEÑAL REAL / SOSPECHOSO / LEAKAGE)

Este script NO modifica ml_model.py ni backtest.py. Es un audit independiente.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

# Permitir ejecución desde la raíz del proyecto sin instalar como paquete
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config  # noqa: E402
from logger import setup_logging  # noqa: E402
from data_fetcher import DataFetcher  # noqa: E402
from indicators import add_all_indicators  # noqa: E402
from ml_model import FEATURE_COLS  # noqa: E402
from borsenhirn.ml.validation import walk_forward_split  # noqa: E402
from borsenhirn.ml.metrics import (  # noqa: E402
    baseline_comparisons,
    evaluate_binary,
    permutation_importance_on_test,
)
from borsenhirn.ml.audit import (  # noqa: E402
    check_label_leakage,
    population_stability_index,
)

setup_logging()
logger = logging.getLogger(__name__)


def create_labels(df, horizon: int, threshold: float):
    """Mismo labeling que ml_model.py para comparabilidad."""
    fut = df["close"].shift(-horizon)
    return ((fut - df["close"]) / df["close"] >= threshold).astype(int)


def verdict(auc_mean: float | None) -> str:
    if auc_mean is None:
        return "SIN DATOS (folds sin 2 clases o dataset muy pequeño)"
    if auc_mean < 0.52:
        return "RUIDO — el modelo no aprende. Cambiar features/labels."
    if auc_mean < 0.55:
        return "SEÑAL DÉBIL — probar triple-barrier o meta-labeling."
    if auc_mean < 0.62:
        return "SEÑAL REAL — usable con buen risk management."
    if auc_mean < 0.70:
        return "SOSPECHOSO — auditar leakage residual."
    return "CASI SEGURO LEAKAGE — NO usar en producción hasta auditar."


def main(args):
    logger.info(
        "Validando %s (%s..%s, tf=%s, n_splits=%d, embargo=%.3f)",
        args.symbol, args.start, args.end, args.timeframe,
        args.n_splits, args.embargo,
    )

    start_dt = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)

    df = DataFetcher().get_historical(args.symbol, start_dt, end_dt, args.timeframe)
    if df.empty:
        logger.error("Sin datos descargados para %s", args.symbol)
        sys.exit(1)
    df = add_all_indicators(df)
    logger.info("Dataset: %d filas con indicadores aplicados.", len(df))

    # ── Audit de leakage ANTES de entrenar ─────────────────────
    leakage = check_label_leakage(df, config.ML_HORIZON)
    if not leakage["clean"]:
        logger.warning("ALERTA label leakage:")
        for w in leakage["warnings"][:10]:
            logger.warning(
                "  feature=%s horizon=%d corr=%.3f",
                w["feature"], w["horizon"], w["corr_with_future_close"],
            )

    # ── Preparar X, y ─────────────────────────────────────────
    y_full = create_labels(df, config.ML_HORIZON, config.ML_THRESHOLD)
    feat_cols = [c for c in FEATURE_COLS if c in df.columns]
    if not feat_cols:
        logger.error("Ningún FEATURE_COLS presente en df. Abortando.")
        sys.exit(1)

    # Descartar filas finales donde el label es NaN por el shift
    valid = y_full.dropna().index
    df_v = df.loc[valid]
    y = y_full.loc[valid].values.astype(int)
    X = df_v[feat_cols].values.astype(float)

    logger.info(
        "X shape=%s, y base_rate=%.3f, features=%d",
        X.shape, float(y.mean()), len(feat_cols),
    )

    # Índice de columna para baseline momentum: preferimos una SMA corta
    momentum_idx = None
    for candidate in (f"sma_{config.MA_SHORT_WINDOW}", "close"):
        if candidate in feat_cols:
            momentum_idx = feat_cols.index(candidate)
            break

    # ── Walk-forward purged ───────────────────────────────────
    min_train = max(500, len(X) // 4)
    fold_metrics = []
    last_model = None
    last_Xte = None
    last_yte = None

    try:
        splits = list(
            walk_forward_split(
                X,
                n_splits=args.n_splits,
                label_horizon=config.ML_HORIZON,
                embargo_pct=args.embargo,
                min_train_size=min_train,
            )
        )
    except ValueError as exc:
        logger.error("walk_forward_split falló: %s", exc)
        sys.exit(1)

    if not splits:
        logger.error("No se generaron folds válidos. Dataset demasiado corto.")
        sys.exit(1)

    for fold, (tr_idx, te_idx) in enumerate(splits):
        scaler = StandardScaler()
        Xtr = scaler.fit_transform(X[tr_idx])
        Xte = scaler.transform(X[te_idx])
        ytr, yte = y[tr_idx], y[te_idx]

        model = RandomForestClassifier(
            n_estimators=config.RF_N_ESTIMATORS,
            max_depth=config.RF_MAX_DEPTH,
            random_state=config.RF_RANDOM_STATE,
            n_jobs=-1,
        )
        model.fit(Xtr, ytr)
        proba = model.predict_proba(Xte)
        # Si el modelo aprendió solo una clase en train, predict_proba devuelve 1 col
        if proba.shape[1] == 1:
            class_seen = int(model.classes_[0])
            proba_1 = np.full(len(Xte), float(class_seen))
        else:
            # columna correspondiente a clase 1
            class_to_col = {int(c): i for i, c in enumerate(model.classes_)}
            proba_1 = proba[:, class_to_col.get(1, 1)]

        m = evaluate_binary(yte, proba_1)
        m["fold"] = fold
        m["train_size"] = int(len(tr_idx))
        m["test_size"] = int(len(te_idx))
        m["train_range"] = [int(tr_idx[0]), int(tr_idx[-1])]
        m["test_range"] = [int(te_idx[0]), int(te_idx[-1])]

        if "error" not in m:
            m.update(baseline_comparisons(yte, Xte, momentum_idx))

        fold_metrics.append(m)
        last_model, last_Xte, last_yte = model, Xte, yte

        auc_str = f"{m.get('auc', float('nan')):.4f}" if "auc" in m else "N/A"
        logger.info(
            "Fold %d: AUC=%s  Brier=%.4f  n_test=%d  base=%.3f",
            fold, auc_str,
            m.get("brier", float("nan")),
            m.get("n_samples", 0),
            m.get("base_rate", 0.0),
        )

    # ── Permutation importance + PSI solo en el último fold ───
    perm_imp = []
    psi_by_feature = {}
    if last_model is not None and last_Xte is not None and last_yte is not None:
        perm_imp = permutation_importance_on_test(
            last_model, last_Xte, last_yte, feat_cols
        )
        # PSI entre train agregado (todos los folds previos) y último test
        # Usamos el último train como referencia práctica
        last_tr_idx = fold_metrics[-1]["train_range"]
        X_tr_last = X[last_tr_idx[0]: last_tr_idx[1] + 1]
        X_te_last = X[fold_metrics[-1]["test_range"][0]: fold_metrics[-1]["test_range"][1] + 1]
        for i, feat in enumerate(feat_cols):
            psi_by_feature[feat] = population_stability_index(
                X_tr_last[:, i], X_te_last[:, i]
            )

    # ── Resumen ───────────────────────────────────────────────
    aucs = [m["auc"] for m in fold_metrics if "auc" in m]
    summary = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "period": {"start": args.start, "end": args.end},
        "n_rows": int(len(df_v)),
        "n_features": len(feat_cols),
        "features": feat_cols,
        "base_rate": float(y.mean()),
        "label": {
            "horizon_bars": int(config.ML_HORIZON),
            "threshold_pct": float(config.ML_THRESHOLD),
        },
        "validation": {
            "scheme": "walk_forward_expanding_purged",
            "n_splits_requested": int(args.n_splits),
            "n_folds_valid": len(aucs),
            "embargo_pct": float(args.embargo),
            "min_train_size": int(min_train),
        },
        "auc_mean": float(np.mean(aucs)) if aucs else None,
        "auc_std": float(np.std(aucs)) if aucs else None,
        "auc_min": float(np.min(aucs)) if aucs else None,
        "auc_max": float(np.max(aucs)) if aucs else None,
        "leakage_audit": leakage,
        "folds": fold_metrics,
        "permutation_importance_last_fold": perm_imp,
        "psi_last_fold": psi_by_feature,
        "verdict": verdict(float(np.mean(aucs)) if aucs else None),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs("results/validation", exist_ok=True)
    out_path = f"results/validation/{args.symbol}_walk_forward.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info("Reporte guardado: %s", out_path)

    # ── Imprimir veredicto ────────────────────────────────────
    bar = "=" * 66
    print(f"\n{bar}")
    print(f"  VALIDACIÓN WALK-FORWARD PURGED — {args.symbol} ({args.timeframe})")
    print(bar)
    if aucs:
        print(f"  AUC mean ± std : {summary['auc_mean']:.4f} ± {summary['auc_std']:.4f}")
        print(f"  AUC rango      : [{summary['auc_min']:.4f}, {summary['auc_max']:.4f}]")
    else:
        print("  AUC            : N/A (ningún fold tenía las dos clases)")
    print(f"  Folds válidos  : {summary['validation']['n_folds_valid']}/{args.n_splits}")
    print(f"  Base rate y    : {summary['base_rate']:.3f}")
    print(f"  Filas dataset  : {summary['n_rows']}")
    print(f"  Leakage limpio : {leakage['clean']}")
    print(f"\n  VEREDICTO → {summary['verdict']}")
    print(bar)

    if perm_imp:
        print("\n  Top 5 features por permutation importance (último fold):")
        for row in perm_imp[:5]:
            print(
                f"    {row['feature']:>25s}  "
                f"Δauc={row['importance_mean']:+.4f} ± {row['importance_std']:.4f}"
            )

    # Comparación con baselines (promedio sobre folds válidos)
    base_keys = [
        "always_positive_acc",
        "always_majority_acc",
        "momentum_naive_acc",
        "random_same_rate_acc",
    ]
    print("\n  Baselines triviales (accuracy promedio sobre folds):")
    for k in base_keys:
        vals = [m[k] for m in fold_metrics if k in m]
        if vals:
            print(f"    {k:>25s}: {np.mean(vals):.4f}")

    # Tu modelo: accuracy promedio
    model_accs = [m["accuracy"] for m in fold_metrics if "accuracy" in m]
    if model_accs:
        print(f"    {'(modelo) accuracy':>25s}: {np.mean(model_accs):.4f}")

    print()


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default=config.SYMBOL)
    p.add_argument("--start", default="2020-01-01")
    p.add_argument(
        "--end",
        default=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    )
    p.add_argument("--timeframe", default=config.TIMEFRAME)
    p.add_argument("--n_splits", type=int, default=5)
    p.add_argument(
        "--embargo", type=float, default=0.01,
        help="Fracción del dataset a embargar tras cada test (default 0.01)",
    )
    return p.parse_args()


if __name__ == "__main__":
    main(parse_args())
