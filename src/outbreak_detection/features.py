from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd


KEY_COLUMNS = ["hospital_cases", "social_signal_index", "weather_risk_index"]


def build_feature_table(raw_df: pd.DataFrame, config: Dict[str, Any]) -> Tuple[pd.DataFrame, List[str]]:
    data_cfg = config["data"]
    features_cfg = config["features"]

    date_col = data_cfg["date_column"]
    region_col = data_cfg["region_column"]
    target_col = data_cfg["target_column"]
    horizon = int(data_cfg["forecast_horizon_days"])

    base_cols = list(features_cfg.get("base_columns", KEY_COLUMNS))
    lag_days = [int(x) for x in features_cfg.get("lag_days", [1, 3, 7])]
    roll_windows = [int(x) for x in features_cfg.get("rolling_windows", [3, 7, 14])]

    df = raw_df.copy()
    df[date_col] = pd.to_datetime(df[date_col])
    df.sort_values([region_col, date_col], inplace=True)

    grouped = df.groupby(region_col, group_keys=False)
    created = []

    for col in base_cols:
        for lag in lag_days:
            name = f"{col}_lag_{lag}"
            df[name] = grouped[col].shift(lag)
            created.append(name)

        for window in roll_windows:
            mean_name = f"{col}_rollmean_{window}"
            std_name = f"{col}_rollstd_{window}"
            df[mean_name] = grouped[col].shift(1).rolling(window=window).mean()
            df[std_name] = grouped[col].shift(1).rolling(window=window).std()
            created.extend([mean_name, std_name])

    if target_col not in df.columns:
        # Define outbreak when near-future cases exceed region-specific high quantile.
        future_max = grouped["hospital_cases"].transform(
            lambda s: s.shift(-1).rolling(window=horizon, min_periods=1).max()
        )
        threshold = grouped["hospital_cases"].transform(lambda s: s.quantile(0.8))
        df[target_col] = (future_max > threshold).astype(int)

    keep_cols = [date_col, region_col, target_col] + base_cols + created
    result = df[keep_cols].dropna().reset_index(drop=True)

    processed_path = Path(data_cfg["processed_path"])
    processed_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(processed_path, index=False)

    return result, created
