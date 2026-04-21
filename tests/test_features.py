from __future__ import annotations

import pandas as pd

from outbreak_detection.features import build_feature_table


def test_build_feature_table_creates_expected_columns() -> None:
    config = {
        "data": {
            "date_column": "report_date",
            "region_column": "region",
            "target_column": "outbreak_next_14d",
            "forecast_horizon_days": 3,
            "processed_path": "data/processed/test_features.csv",
        },
        "features": {
            "lag_days": [1],
            "rolling_windows": [2],
            "base_columns": ["hospital_cases", "social_signal_index", "weather_risk_index"],
        },
    }

    df = pd.DataFrame(
        {
            "report_date": pd.date_range("2026-01-01", periods=8, freq="D").tolist() * 2,
            "region": ["north"] * 8 + ["south"] * 8,
            "hospital_cases": [10, 12, 11, 13, 15, 16, 14, 18, 8, 9, 10, 11, 13, 12, 14, 15],
            "social_signal_index": [0.2, 0.25, 0.21, 0.28, 0.3, 0.31, 0.29, 0.35, 0.1, 0.12, 0.13, 0.16, 0.17, 0.18, 0.2, 0.22],
            "weather_risk_index": [0.4, 0.45, 0.43, 0.48, 0.52, 0.54, 0.5, 0.58, 0.3, 0.31, 0.34, 0.37, 0.4, 0.39, 0.41, 0.44],
        }
    )

    out, engineered = build_feature_table(df, config)

    assert len(engineered) == 9
    assert "hospital_cases_lag_1" in out.columns
    assert "social_signal_index_rollmean_2" in out.columns
    assert "weather_risk_index_rollstd_2" in out.columns
    assert "outbreak_next_14d" in out.columns
    assert out.isna().sum().sum() == 0
