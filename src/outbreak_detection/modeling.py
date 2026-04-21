from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score


def train_and_evaluate(
    features_df: pd.DataFrame,
    feature_columns: List[str],
    config: Dict[str, Any],
) -> Tuple[RandomForestClassifier, pd.DataFrame, Dict[str, float]]:
    data_cfg = config["data"]
    model_cfg = config["model"]

    date_col = data_cfg["date_column"]
    target_col = data_cfg["target_column"]

    test_size = float(model_cfg.get("test_size", 0.25))

    split_date = features_df[date_col].quantile(1.0 - test_size)
    train_df = features_df[features_df[date_col] < split_date].copy()
    test_df = features_df[features_df[date_col] >= split_date].copy()

    X_train = train_df[feature_columns]
    y_train = train_df[target_col].astype(int)
    X_test = test_df[feature_columns]
    y_test = test_df[target_col].astype(int)

    clf = RandomForestClassifier(
        n_estimators=int(model_cfg.get("n_estimators", 300)),
        max_depth=int(model_cfg.get("max_depth", 8)),
        min_samples_leaf=int(model_cfg.get("min_samples_leaf", 5)),
        class_weight=model_cfg.get("class_weight", "balanced"),
        random_state=int(config["project"].get("random_state", 42)),
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)

    y_prob = clf.predict_proba(X_test)[:, 1]
    y_pred = (y_prob >= 0.5).astype(int)

    tn, fp, fn, tp = confusion_matrix(y_test, y_pred, labels=[0, 1]).ravel()
    metrics = {
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, y_prob)) if len(np.unique(y_test)) > 1 else 0.0,
        "false_alarm_rate": float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0,
    }

    scored = test_df[[date_col, data_cfg["region_column"], target_col]].copy()
    scored["predicted_probability"] = y_prob

    model_path = Path("models/outbreak_model.joblib")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, model_path)

    return clf, scored, metrics
