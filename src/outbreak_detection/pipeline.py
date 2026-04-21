from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from outbreak_detection.alerts import build_alert_output, choose_alert_threshold
from outbreak_detection.data import load_or_create_raw_data_with_context
from outbreak_detection.features import build_feature_table
from outbreak_detection.modeling import train_and_evaluate
from outbreak_detection.outlook import build_region_outlook
from outbreak_detection.utils import load_config, write_json


def run_pipeline(config_path: str = "config.yaml") -> Dict[str, Any]:
    config = load_config(config_path)

    raw_df, data_context = load_or_create_raw_data_with_context(config)
    feature_df, feature_columns = build_feature_table(raw_df, config)

    _model, scored_df, model_metrics = train_and_evaluate(feature_df, feature_columns, config)
    threshold = choose_alert_threshold(scored_df, config)
    alerts_df, alert_summary = build_alert_output(scored_df, threshold, config)
    region_outlook, _ = build_region_outlook(alerts_df, config, data_context=data_context)

    result = {
        "rows_raw": int(len(raw_df)),
        "rows_features": int(len(feature_df)),
        "feature_count": int(len(feature_columns)),
        "data_source": str(config["data"].get("source", "file_or_synthetic")),
        "model_metrics": model_metrics,
        "alert_summary": alert_summary,
        "region_headline": region_outlook["headline"],
    }

    Path("outputs").mkdir(parents=True, exist_ok=True)
    write_json(result, "outputs/pipeline_summary.json")
    write_json(region_outlook, "outputs/region_outlook.json")
    return result


if __name__ == "__main__":
    summary = run_pipeline("config.yaml")
    print(summary)
