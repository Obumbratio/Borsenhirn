"""
Verifica reproducibilidad bit-exacta del pipeline de entrenamiento.

Entrena el Random Forest DOS veces con la misma semilla sobre datos
sintéticos deterministas y compara el hash SHA-256 de los modelos
serializados. Si los bytes difieren, el modelo NO es reproducible y hay
que auditar qué introduce no-determinismo.

Uso:
    python scripts/verify_reproducibility.py
    python scripts/verify_reproducibility.py --rows 2000 --seed 42

Salida:
    Exit 0 → modelos bit-idénticos (reproducibilidad OK).
    Exit 1 → hashes distintos (algo introduce non-determinism).

Notas:
    - Usa datos sintéticos para no depender de Alpaca / internet.
    - Si falla, las causas típicas son:
        * Paralelismo (n_jobs=-1 con scheduler distinto por run).
        * Alguna feature pre-calculada con np.random sin seed.
        * Versión de scikit-learn no pinned.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def make_synthetic_df(rows: int, seed: int) -> pd.DataFrame:
    """Dataset sintético determinista para entrenar el modelo."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01 09:30", periods=rows, freq="1h")
    close = 100 + np.cumsum(rng.standard_normal(rows) * 0.3)
    df = pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.003,
        "low": close * 0.997,
        "close": close,
        "volume": rng.integers(1000, 10000, rows).astype(float),
    }, index=dates)
    return df


def add_minimal_indicators(df: pd.DataFrame, ma_short: int, ma_long: int,
                            bb_window: int, bb_std: float) -> pd.DataFrame:
    """Replica los indicadores que ml_model.FEATURE_COLS necesita,
    pero sin depender de la librería `ta` (más reproducible)."""
    out = df.copy()
    out[f"sma_{ma_short}"] = out["close"].rolling(ma_short).mean()
    out[f"sma_{ma_long}"] = out["close"].rolling(ma_long).mean()

    delta = out["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi"] = (100 - 100 / (1 + rs)).fillna(50.0)

    tr = pd.concat([
        out["high"] - out["low"],
        (out["high"] - out["close"].shift()).abs(),
        (out["low"] - out["close"].shift()).abs(),
    ], axis=1).max(axis=1)
    out["atr"] = tr.rolling(14).mean()

    ema12 = out["close"].ewm(span=12, adjust=False).mean()
    ema26 = out["close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macds = macd.ewm(span=9, adjust=False).mean()
    out["MACD_12_26_9"] = macd
    out["MACDs_12_26_9"] = macds
    out["MACDh_12_26_9"] = macd - macds

    mid = out["close"].rolling(bb_window).mean()
    std = out["close"].rolling(bb_window).std()
    bbl_col = f"BBL_{bb_window}_{float(bb_std)}"
    bbm_col = f"BBM_{bb_window}_{float(bb_std)}"
    bbu_col = f"BBU_{bb_window}_{float(bb_std)}"
    out[bbl_col] = mid - bb_std * std
    out[bbm_col] = mid
    out[bbu_col] = mid + bb_std * std

    return out.dropna().reset_index(drop=True)


def train_once(rows: int, seed: int) -> bytes:
    """Entrena una vez y devuelve el modelo serializado en bytes."""
    # Import tardío y reseteo de seeds globales
    np.random.seed(seed)

    import config  # noqa: E402
    from ml_model import TradingModel, FEATURE_COLS  # noqa: E402

    df_raw = make_synthetic_df(rows, seed)
    df = add_minimal_indicators(
        df_raw,
        ma_short=config.MA_SHORT_WINDOW,
        ma_long=config.MA_LONG_WINDOW,
        bb_window=config.BB_WINDOW,
        bb_std=config.BB_STD,
    )

    avail = [c for c in FEATURE_COLS if c in df.columns]
    if len(avail) < 5:
        print(f"FAIL: solo {len(avail)} features disponibles "
              f"(esperaba al menos 5). FEATURE_COLS={FEATURE_COLS}")
        sys.exit(2)

    # Entrenar usando el pipeline real
    model = TradingModel(
        model_path=os.path.join(tempfile.gettempdir(),
                                f"rf_repro_{seed}.pkl"),
        scaler_path=os.path.join(tempfile.gettempdir(),
                                 f"scaler_repro_{seed}.pkl"),
    )
    model.train(df)

    # Serializar a bytes en memoria (no depender del disco)
    import joblib
    buf_model = io.BytesIO()
    buf_scaler = io.BytesIO()
    joblib.dump(model.model, buf_model)
    joblib.dump(model.scaler, buf_scaler)
    return buf_model.getvalue() + b"||SEP||" + buf_scaler.getvalue()


def hash_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rows", type=int, default=2000,
                   help="tamaño del dataset sintético (default 2000)")
    p.add_argument("--seed", type=int, default=42,
                   help="semilla para data + modelo (default 42)")
    args = p.parse_args()

    print(f"Verificando reproducibilidad con rows={args.rows}, seed={args.seed}")
    print(f"Python: {sys.version.split()[0]}")
    try:
        import sklearn
        print(f"sklearn: {sklearn.__version__}")
        import numpy as _np
        print(f"numpy: {_np.__version__}")
        import joblib as _jl
        print(f"joblib: {_jl.__version__}")
    except Exception:
        pass

    print("\n--- Run 1 ---")
    bytes_a = train_once(args.rows, args.seed)
    hash_a = hash_bytes(bytes_a)
    print(f"hash A: {hash_a}")

    print("\n--- Run 2 ---")
    bytes_b = train_once(args.rows, args.seed)
    hash_b = hash_bytes(bytes_b)
    print(f"hash B: {hash_b}")

    print("\n" + "=" * 64)
    if hash_a == hash_b:
        print("OK — Modelo BIT-IDENTICO entre runs. Reproducibilidad verificada.")
        print("=" * 64)
        sys.exit(0)
    else:
        print("FAIL — Hashes distintos. El modelo NO es reproducible.")
        print(f"Diff bytes: modelo A={len(bytes_a)}, modelo B={len(bytes_b)}")
        print("\nPosibles causas:")
        print("  1. Paralelismo con scheduler no determinista (n_jobs=-1).")
        print("     → probar n_jobs=1 temporalmente y ver si da identico.")
        print("  2. Alguna feature con np.random sin seed.")
        print("     → grep por 'np.random' en features/indicators.")
        print("  3. sklearn o joblib no pinned — versiones distintas entre runs.")
        print("     → usar pip-sync con requirements.txt generado por pip-compile.")
        print("=" * 64)
        sys.exit(1)


if __name__ == "__main__":
    main()
