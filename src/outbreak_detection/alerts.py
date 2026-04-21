from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, recall_score


def choose_alert_threshold(scored_df: pd.DataFrame, config: Dict[str, Any]) -> float:
    alerts_cfg = config["alerts"]
    data_cfg = config["data"]
    target_col = data_cfg["target_column"]

    fixed = alerts_cfg.get("probability_threshold", None)
    if fixed is not None:
        return float(fixed)

    min_recall = float(alerts_cfg.get("minimum_recall", 0.7))
    max_false_alarm = float(alerts_cfg.get("false_alarm_tolerance", 0.15))

    y_true = scored_df[target_col].astype(int).to_numpy()
    y_prob = scored_df["predicted_probability"].to_numpy()

    best_t = 0.5
    best_score = -np.inf

    for t in np.linspace(0.2, 0.95, 76):
        y_pred = (y_prob >= t).astype(int)
        recall = recall_score(y_true, y_pred, zero_division=0)

        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
        false_alarm = float(fp / (fp + tn)) if (fp + tn) > 0 else 0.0

        feasible = recall >= min_recall and false_alarm <= max_false_alarm
        score = recall - false_alarm
        if feasible and score > best_score:
            best_t = float(t)
            best_score = score

    return best_t


def build_alert_output(scored_df: pd.DataFrame, threshold: float, config: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, float]]:
    data_cfg = config["data"]
    alerts_cfg = config["alerts"]

    date_col = data_cfg["date_column"]
    region_col = data_cfg["region_column"]
    target_col = data_cfg["target_column"]

    sev = alerts_cfg.get("severity_levels", {})
    medium = float(sev.get("medium", 0.65))
    high = float(sev.get("high", 0.8))
    critical = float(sev.get("critical", 0.9))

    out = scored_df[[date_col, region_col, target_col, "predicted_probability"]].copy()
    out["threshold"] = threshold
    out["is_alert"] = (out["predicted_probability"] >= threshold).astype(int)

    def label_severity(prob: float) -> str:
        if prob >= critical:
            return "critical"
        if prob >= high:
            return "high"
        if prob >= medium:
            return "medium"
        return "low"

    out["severity"] = out["predicted_probability"].apply(label_severity)

    alerts_path = Path("outputs/alerts.csv")
    alerts_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(alerts_path, index=False)

    summary = {
        "chosen_threshold": float(threshold),
        "alert_count": int(out["is_alert"].sum()),
        "alert_ratio": float(out["is_alert"].mean()),
    }
    return out, summary
