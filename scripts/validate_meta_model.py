"""
Valida el pipeline de meta-labeling con walk-forward purged CV.

Uso:
    python scripts/validate_meta_model.py --symbol SPY --start 2020-01-01
    python scripts/validate_meta_model.py --symbol SPY --no_meta_features    # comparar
    python scripts/validate_meta_model.py --symbol SPY --debug

Salida:
    results/validation/<SYMBOL>_meta_walk_forward.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import warnings
from datetime import datetime, timezone

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

warnings.filterwarnings("ignore", category=FutureWarning)

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
    evaluate_binary, permutation_importance_on_test,
)
from borsenhirn.ml.meta_model import (  # noqa: E402
    MetaLabelingConfig, PrimaryRuleConfig, build_meta_dataset,
)
from borsenhirn.ml.labeling import TripleBarrierConfig  # noqa: E402
from borsenhirn.ml.features import add_meta_features, get_meta_feature_cols  # noqa: E402

setup_logging()
logger = logging.getLogger(__name__)


def pnl_summary(events, mask_take):
    if len(events) == 0 or mask_take.sum() == 0:
        return {"n_trades": 0, "total_ret": 0.0, "win_rate": 0.0,
                "avg_ret": 0.0, "sharpe_on_trades": 0.0}
    taken = events.loc[mask_take]
    rets = taken["ret"].values
    n = len(rets)
    wins = int((rets > 0).sum())
    total = float(rets.sum())
    avg = float(rets.mean())
    std = float(rets.std()) if n > 1 else 0.0
    sharpe = avg / std * np.sqrt(n) if std > 0 else 0.0
    return {"n_trades": int(n), "total_ret": total, "win_rate": float(wins/n),
            "avg_ret": avg, "sharpe_on_trades": float(sharpe)}


def verdict_meta(auc_mean, precision_mean, baseline_win_rate):
    if auc_mean is None:
        return "SIN DATOS"
    if auc_mean < 0.52:
        return "RUIDO - meta-modelo no filtra mejor que azar."
    if precision_mean is not None and precision_mean > baseline_win_rate + 0.05:
        return (f"UTIL - precision {precision_mean:.3f} supera baseline "
                f"{baseline_win_rate:.3f}. Meta-labeling aporta.")
    if auc_mean < 0.58:
        return "SENAL MARGINAL - revisar features y primary rule."
    return "PROMETEDOR - AUC > 0.58 pero precision no supera baseline; revisar umbral."


def main(args):
    start_dt = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end_dt = datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc)
    logger.info("Meta-labeling %s (%s..%s, tf=%s)", args.symbol, args.start,
                args.end, args.timeframe)

    df = DataFetcher().get_historical(args.symbol, start_dt, end_dt, args.timeframe)
    if df.empty:
        logger.error("Sin datos"); sys.exit(1)
    df = add_all_indicators(df)
    logger.info("Dataset: %d filas (con indicadores).", len(df))

    if args.use_meta_features:
        df = add_meta_features(df)
        meta_cols = [c for c in get_meta_feature_cols() if c in df.columns]
        logger.info("Meta-features anadidos: %d columnas.", len(meta_cols))
    else:
        meta_cols = []

    base_cols = [c for c in FEATURE_COLS if c in df.columns]
    feat_cols = base_cols + meta_cols
    logger.info("Features totales: %d (base=%d, meta=%d)",
                len(feat_cols), len(base_cols), len(meta_cols))

    cfg = MetaLabelingConfig(
        primary=PrimaryRuleConfig(
            rsi_oversold=float(args.rsi_oversold),
            sma_long_col=f"sma_{config.MA_LONG_WINDOW}",
            sma_short_col=f"sma_{config.MA_SHORT_WINDOW}",
            volume_min_ratio=float(args.volume_min_ratio),
            require_uptrend_long=bool(args.require_uptrend),
            require_above_short=bool(args.require_above_short),
            cooldown_bars=int(args.cooldown),
        ),
        barrier=TripleBarrierConfig(
            pt_mult=float(args.pt_mult),
            sl_mult=float(args.sl_mult),
            max_holding=int(args.max_holding),
        ),
        vol_span=20,
    )

    X, y, events = build_meta_dataset(df, feat_cols, cfg, debug=args.debug)
    if len(X) < 100:
        logger.error("Solo %d eventos primarios - muy pocos. Usa --debug.", len(X))
        sys.exit(1)

    base_rate = float(y.mean())
    logger.info("Meta dataset: n=%d | win_rate_base=%.3f | features=%d",
                len(X), base_rate, len(feat_cols))

    min_train = max(80, len(X) // 4)
    try:
        splits = list(walk_forward_split(
            X, n_splits=args.n_splits,
            label_horizon=cfg.barrier.max_holding,
            embargo_pct=args.embargo,
            min_train_size=min_train,
        ))
    except ValueError as exc:
        logger.error("walk_forward_split fallo: %s", exc); sys.exit(1)
    if not splits:
        logger.error("Sin folds validos"); sys.exit(1)

    fold_metrics = []
    pnl_strategies = {
        "primary_only": {"take": []},
        "meta_threshold_050": {"take": []},
        "meta_threshold_060": {"take": []},
    }
    last_model = last_Xte = last_yte = None

    for fold, (tr_idx, te_idx) in enumerate(splits):
        scaler = StandardScaler()
        Xtr = scaler.fit_transform(X[tr_idx])
        Xte = scaler.transform(X[te_idx])
        ytr, yte = y[tr_idx], y[te_idx]

        if len(np.unique(ytr)) < 2:
            logger.warning("Fold %d: train con una sola clase, skip.", fold)
            continue

        model = RandomForestClassifier(
            n_estimators=config.RF_N_ESTIMATORS,
            max_depth=config.RF_MAX_DEPTH,
            class_weight="balanced",
            random_state=config.RF_RANDOM_STATE,
            n_jobs=-1,
        )
        model.fit(Xtr, ytr)
        proba = model.predict_proba(Xte)
        if proba.shape[1] == 1:
            proba_1 = np.full(len(Xte), float(model.classes_[0]))
        else:
            ci = {int(c): i for i, c in enumerate(model.classes_)}
            proba_1 = proba[:, ci.get(1, 1)]

        m = evaluate_binary(yte, proba_1, threshold=0.5)
        m["fold"] = fold
        m["train_size"] = int(len(tr_idx))
        m["test_size"] = int(len(te_idx))

        for thr, key in [(0.5, "precision_thr050"), (0.6, "precision_thr060")]:
            pred = (proba_1 >= thr).astype(int)
            if pred.sum() == 0:
                m[key] = None
                m[f"n_trades_{key}"] = 0
            else:
                m[key] = float((pred & yte).sum() / pred.sum())
                m[f"n_trades_{key}"] = int(pred.sum())

        fold_metrics.append(m)
        last_model, last_Xte, last_yte = model, Xte, yte

        take_all = np.ones(len(te_idx), dtype=bool)
        pnl_strategies["primary_only"]["take"].append(
            pnl_summary(events.iloc[te_idx], take_all))
        for thr, key in [(0.5, "meta_threshold_050"), (0.6, "meta_threshold_060")]:
            take_mask = proba_1 >= thr
            pnl_strategies[key]["take"].append(
                pnl_summary(events.iloc[te_idx], take_mask))

        auc_str = f"{m.get('auc', float('nan')):.4f}" if "auc" in m else "N/A"
        p050 = f"{m['precision_thr050']:.3f}" if m.get("precision_thr050") is not None else "N/A"
        p060 = f"{m['precision_thr060']:.3f}" if m.get("precision_thr060") is not None else "N/A"
        logger.info("Fold %d: AUC=%s  prec@0.5=%s  prec@0.6=%s  n_test=%d",
                    fold, auc_str, p050, p060, m.get("n_samples", 0))

    aucs = [m["auc"] for m in fold_metrics if "auc" in m]
    precs_050 = [m["precision_thr050"] for m in fold_metrics
                 if m.get("precision_thr050") is not None]
    precs_060 = [m["precision_thr060"] for m in fold_metrics
                 if m.get("precision_thr060") is not None]

    perm_imp = []
    if last_model is not None and last_Xte is not None and last_yte is not None:
        try:
            perm_imp = permutation_importance_on_test(
                last_model, last_Xte, last_yte, feat_cols, n_repeats=8)
        except Exception as exc:
            logger.warning("permutation_importance fallo: %s", exc)

    def avg_strategy(key):
        rows = pnl_strategies[key]["take"]
        if not rows:
            return {}
        nz = [r for r in rows if r["n_trades"] > 0]
        return {
            "n_trades_total": int(sum(r["n_trades"] for r in rows)),
            "total_ret": float(sum(r["total_ret"] for r in rows)),
            "avg_win_rate": float(np.mean([r["win_rate"] for r in nz] or [0])),
            "avg_ret_per_trade": float(np.mean([r["avg_ret"] for r in nz] or [0])),
        }

    summary = {
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "period": {"start": args.start, "end": args.end},
        "n_events": int(len(X)),
        "base_win_rate": base_rate,
        "label_config": {
            "pt_mult": cfg.barrier.pt_mult,
            "sl_mult": cfg.barrier.sl_mult,
            "max_holding": cfg.barrier.max_holding,
        },
        "primary_config": {
            "rsi_oversold": cfg.primary.rsi_oversold,
            "volume_min_ratio": cfg.primary.volume_min_ratio,
            "require_uptrend_long": cfg.primary.require_uptrend_long,
            "require_above_short": cfg.primary.require_above_short,
            "cooldown_bars": cfg.primary.cooldown_bars,
        },
        "auc_mean": float(np.mean(aucs)) if aucs else None,
        "auc_std": float(np.std(aucs)) if aucs else None,
        "precision_050_mean": float(np.mean(precs_050)) if precs_050 else None,
        "precision_060_mean": float(np.mean(precs_060)) if precs_060 else None,
        "folds": fold_metrics,
        "pnl_comparison": {
            "primary_only": avg_strategy("primary_only"),
            "meta_threshold_050": avg_strategy("meta_threshold_050"),
            "meta_threshold_060": avg_strategy("meta_threshold_060"),
        },
        "features_used": feat_cols,
        "meta_features_enabled": args.use_meta_features,
        "permutation_importance_last_fold": perm_imp,
        "verdict": verdict_meta(
            float(np.mean(aucs)) if aucs else None,
            float(np.mean(precs_050)) if precs_050 else None,
            base_rate),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    os.makedirs("results/validation", exist_ok=True)
    out_path = f"results/validation/{args.symbol}_meta_walk_forward.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info("Reporte guardado: %s", out_path)

    bar = "=" * 72
    print(f"\n{bar}")
    print(f"  META-LABELING - {args.symbol} ({args.timeframe})  "
          f"[meta_features={'ON' if args.use_meta_features else 'OFF'}]")
    print(bar)
    print(f"  Eventos primarios      : {summary['n_events']}")
    print(f"  Win rate SIN filtro    : {base_rate:.3f}  (baseline)")
    if aucs:
        print(f"  AUC meta mean +/- std  : {summary['auc_mean']:.4f} +/- {summary['auc_std']:.4f}")
    if precs_050:
        print(f"  Precision @ 0.50 meta  : {summary['precision_050_mean']:.3f}")
    if precs_060:
        print(f"  Precision @ 0.60 meta  : {summary['precision_060_mean']:.3f}")

    print(f"\n  Comparativa PnL (test agregado, sin comisiones):")
    for name, label in [("primary_only", "primario solo"),
                        ("meta_threshold_050", "meta thr=0.5"),
                        ("meta_threshold_060", "meta thr=0.6")]:
        s = summary["pnl_comparison"][name]
        if s:
            print(f"    {label:>18}: trades={s['n_trades_total']:>4}  "
                  f"win_rate={s['avg_win_rate']:.3f}  "
                  f"avg_ret={s['avg_ret_per_trade']:+.4f}  "
                  f"total_ret={s['total_ret']:+.4f}")

    if perm_imp:
        print("\n  Top 10 features por permutation importance (ultimo fold):")
        for row in perm_imp[:10]:
            print(f"    {row['feature']:>25s}  "
                  f"delta_auc={row['importance_mean']:+.4f} +/- {row['importance_std']:.4f}")

    print(f"\n  VEREDICTO -> {summary['verdict']}")
    print(bar)
    print()


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", default=config.SYMBOL)
    p.add_argument("--start", default="2020-01-01")
    p.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    p.add_argument("--timeframe", default=config.TIMEFRAME)
    p.add_argument("--n_splits", type=int, default=5)
    p.add_argument("--embargo", type=float, default=0.01)
    p.add_argument("--pt_mult", type=float, default=2.0)
    p.add_argument("--sl_mult", type=float, default=1.0)
    p.add_argument("--max_holding", type=int, default=20)
    p.add_argument("--rsi_oversold", type=float, default=45.0)
    p.add_argument("--volume_min_ratio", type=float, default=0.6)
    p.add_argument("--require_uptrend", action="store_true")
    p.add_argument("--require_above_short", action="store_true")
    p.add_argument("--cooldown", type=int, default=5)
    p.add_argument("--debug", action="store_true")
    p.add_argument("--no_meta_features", dest="use_meta_features",
                   action="store_false")
    p.set_defaults(use_meta_features=True)
    return p.parse_args()


if __name__ == "__main__":
    main(parse_args())
