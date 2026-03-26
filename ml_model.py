import os, logging, joblib
import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report, confusion_matrix
import config

logger = logging.getLogger(__name__)

# REEMPLAZA el bloque FEATURE_COLS en ml_model.py por este:

FEATURE_COLS = [
    "open", "high", "low", "close", "volume",
    f"sma_{config.MA_SHORT_WINDOW}",
    f"sma_{config.MA_LONG_WINDOW}",
    "rsi", "atr",
    "MACD_12_26_9", "MACDs_12_26_9", "MACDh_12_26_9",
    f"BBL_{config.BB_WINDOW}_{float(config.BB_STD)}",
    f"BBM_{config.BB_WINDOW}_{float(config.BB_STD)}",
    f"BBU_{config.BB_WINDOW}_{float(config.BB_STD)}",
]

class TradingModel:
    def __init__(self, model_path=config.MODEL_PATH, scaler_path=config.SCALER_PATH):
        self.model_path  = model_path
        self.scaler_path = scaler_path
        self.model       = None
        self.scaler      = None

    def _avail(self, df):
        return [c for c in FEATURE_COLS if c in df.columns]

    def prepare_features(self, df):
        fc = self._avail(df)
        X  = df[fc].values
        sc = StandardScaler()
        return sc.fit_transform(X), sc, fc

    def create_labels(self, df, horizon=config.ML_HORIZON, threshold=config.ML_THRESHOLD):
        fut = df["close"].shift(-horizon)
        return ((fut - df["close"]) / df["close"] >= threshold).astype(int)

    def train(self, df):
        labels   = self.create_labels(df)
        fc       = self._avail(df)
        valid    = labels.dropna().index
        X_raw    = df.loc[valid, fc].values
        y        = labels.loc[valid].values
        self.scaler = StandardScaler()
        X        = self.scaler.fit_transform(X_raw)
        split    = int(len(X) * 0.8)
        Xtr,Xte  = X[:split], X[split:]
        ytr,yte  = y[:split], y[split:]
        logger.info(f"Entrenando RF con {len(Xtr)} muestras...")
        self.model = RandomForestClassifier(
            n_estimators=config.RF_N_ESTIMATORS,
            max_depth=config.RF_MAX_DEPTH,
            random_state=config.RF_RANDOM_STATE, n_jobs=-1)
        self.model.fit(Xtr, ytr)
        yp  = self.model.predict(Xte)
        acc = (yp == yte).mean()
        logger.info(f"Accuracy test: {acc:.4f}")
        logger.info("\n" + classification_report(yte, yp))
        self.save_model()
        return {"accuracy": acc, "confusion_matrix": confusion_matrix(yte, yp).tolist()}

    def save_model(self):
        os.makedirs(os.path.dirname(self.model_path), exist_ok=True)
        joblib.dump(self.model,  self.model_path)
        joblib.dump(self.scaler, self.scaler_path)
        logger.info(f"Modelo guardado en {self.model_path}")

    def load_model(self):
        try:
            self.model  = joblib.load(self.model_path)
            self.scaler = joblib.load(self.scaler_path)
            logger.info("Modelo cargado.")
            return True
        except FileNotFoundError:
            logger.warning("Modelo no encontrado. Entrena primero.")
            return False

    def predict_prob(self, df):
        if self.model is None or self.scaler is None:
            return 0.5
        fc = self._avail(df)
        if not fc:
            return 0.5
        last_row = df[fc].iloc[[-1]]
        if last_row.isnull().values.any():
            logger.warning("predict_prob: NaN en última fila, retornando 0.5")
            return 0.5
        try:
            X   = self.scaler.transform(last_row.values)
            prb = self.model.predict_proba(X)[0]
            cls = list(self.model.classes_)
            return float(prb[cls.index(1)]) if 1 in cls else 0.5
        except Exception as e:
            logger.error(f"predict_prob: {e}")
            return 0.5
