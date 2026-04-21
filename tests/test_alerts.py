from __future__ import annotations

import pandas as pd

from outbreak_detection.alerts import build_alert_output, choose_alert_threshold


def test_choose_alert_threshold_respects_policy_bounds() -> None:
    config = {
        "data": {"target_column": "outbreak_next_14d", "date_column": "report_date", "region_column": "region"},
        "alerts": {
            "probability_threshold": None,
            "minimum_recall": 0.6,
            "false_alarm_tolerance": 0.4,
            "severity_levels": {"medium": 0.5, "high": 0.7, "critical": 0.9},
        },
    }

    scored = pd.DataFrame(
        {
            "report_date": pd.date_range("2026-01-01", periods=10, freq="D"),
            "region": ["north"] * 10,
            "outbreak_next_14d": [0, 0, 0, 1, 1, 1, 0, 1, 0, 1],
            "predicted_probability": [0.1, 0.2, 0.35, 0.55, 0.62, 0.8, 0.3, 0.75, 0.4, 0.9],
        }
    )

    threshold = choose_alert_threshold(scored, config)
    out, summary = build_alert_output(scored, threshold, config)

    assert 0.2 <= threshold <= 0.95
    assert "severity" in out.columns
    assert summary["alert_count"] == int(out["is_alert"].sum())
