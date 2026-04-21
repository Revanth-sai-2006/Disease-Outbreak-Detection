from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

from outbreak_detection.utils import write_json
from outbreak_detection.web_data import fetch_web_surveillance_bundle


def load_or_create_raw_data(config: Dict[str, Any]) -> pd.DataFrame:
    df, _ctx = load_or_create_raw_data_with_context(config)
    return df


def load_or_create_raw_data_with_context(config: Dict[str, Any]) -> tuple[pd.DataFrame, Dict[str, Any]]:
    data_cfg = config["data"]
    raw_path = Path(data_cfg["raw_path"])
    date_col = data_cfg["date_column"]
    source = str(data_cfg.get("source", "file_or_synthetic"))
    allow_fallback = bool(data_cfg.get("fallback_to_synthetic_on_web_failure", True))
    context: Dict[str, Any] = {}

    if source == "web":
        try:
            df, web_context = fetch_web_surveillance_bundle(config)
            context.update(web_context)
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(raw_path, index=False)
            write_json(
                {
                    "status": "ok",
                    "source": "web",
                    "rows": int(len(df)),
                    "regions": sorted(df["region"].astype(str).unique().tolist()),
                    "term_profiles": web_context.get("term_profiles", {}),
                },
                "outputs/data_source_status.json",
            )
            return df, context
        except Exception as exc:
            write_json(
                {
                    "status": "fallback",
                    "source": "web",
                    "reason": str(exc),
                },
                "outputs/data_source_status.json",
            )
            if not allow_fallback:
                raise

    if raw_path.exists():
        df = pd.read_csv(raw_path)
        df = _normalize_schema(df, config)
        df[date_col] = pd.to_datetime(df[date_col])
        return df, context

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    df = _generate_synthetic_surveillance_data(config)
    df.to_csv(raw_path, index=False)
    return df, context


def _normalize_schema(df: pd.DataFrame, config: Dict[str, Any]) -> pd.DataFrame:
    data_cfg = config["data"]
    mapping = dict(data_cfg.get("schema_mapping", {}))

    canonical = {
        "date": data_cfg["date_column"],
        "region": data_cfg["region_column"],
        "hospital_cases": "hospital_cases",
        "social_signal_index": "social_signal_index",
        "weather_risk_index": "weather_risk_index",
        "target": data_cfg["target_column"],
    }

    rename_map: Dict[str, str] = {}
    for logical_name, canonical_name in canonical.items():
        source_name = mapping.get(logical_name)
        if source_name and source_name in df.columns and source_name != canonical_name:
            rename_map[source_name] = canonical_name

    if rename_map:
        df = df.rename(columns=rename_map)

    required = [
        data_cfg["date_column"],
        data_cfg["region_column"],
        "hospital_cases",
        "social_signal_index",
        "weather_risk_index",
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Missing required columns after schema mapping: {joined}")

    return df


def _generate_synthetic_surveillance_data(config: Dict[str, Any]) -> pd.DataFrame:
    seed = int(config["project"].get("random_state", 42))
    rng = np.random.default_rng(seed)

    date_col = config["data"]["date_column"]
    region_col = config["data"]["region_column"]

    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=540, freq="D")
    regions = ["north", "south", "east", "west"]

    frames = []
    for region_ix, region in enumerate(regions):
        phase = region_ix * np.pi / 6.0
        t = np.arange(len(dates), dtype=float)

        seasonal = 12.0 + 4.5 * np.sin((2.0 * np.pi * t / 30.0) + phase)
        drift = 0.005 * t
        weather_risk = np.clip(0.45 + 0.2 * np.sin((2.0 * np.pi * t / 18.0) + phase) + rng.normal(0, 0.07, len(t)), 0, 1)
        social_signal = np.clip(0.4 + 0.35 * weather_risk + rng.normal(0, 0.08, len(t)), 0, 1)

        random_spikes = np.zeros(len(t))
        spike_days = rng.choice(len(t) - 21, size=8, replace=False)
        for day in spike_days:
            width = rng.integers(3, 7)
            amp = rng.uniform(6, 15)
            random_spikes[day : day + width] += amp

        hospital_cases = np.maximum(
            0,
            seasonal + drift + (weather_risk * 10.0) + (social_signal * 7.0) + random_spikes + rng.normal(0, 1.8, len(t)),
        )

        frame = pd.DataFrame(
            {
                date_col: dates,
                region_col: region,
                "hospital_cases": hospital_cases.round(2),
                "social_signal_index": social_signal.round(4),
                "weather_risk_index": weather_risk.round(4),
            }
        )
        frames.append(frame)

    out = pd.concat(frames, ignore_index=True)
    out.sort_values([region_col, date_col], inplace=True)
    out.reset_index(drop=True, inplace=True)
    return out
