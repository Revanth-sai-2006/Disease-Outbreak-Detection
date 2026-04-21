from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

import pandas as pd


def build_region_outlook(
    alerts_df: pd.DataFrame,
    config: Dict[str, Any],
    data_context: Dict[str, Any] | None = None,
) -> Tuple[Dict[str, Any], pd.DataFrame]:
    data_cfg = config["data"]
    date_col = data_cfg["date_column"]
    region_col = data_cfg["region_column"]
    horizon_days = int(data_cfg.get("forecast_horizon_days", 14))

    ranked = alerts_df.sort_values([region_col, date_col]).copy()

    trend_by_region = ranked.groupby(region_col, group_keys=True)["predicted_probability"].apply(_trend_delta).to_dict()
    latest = ranked.groupby(region_col, as_index=False).tail(1).copy()

    regions: List[Dict[str, Any]] = []
    term_profiles = dict((data_context or {}).get("term_profiles", {}))
    for _, row in latest.sort_values("predicted_probability", ascending=False).iterrows():
        region = str(row[region_col])
        delta = float(trend_by_region.get(region, 0.0))
        disease_meta = _infer_disease_profile(term_profiles.get(region, {}))
        regions.append(
            {
                "region": region,
                "report_date": str(pd.to_datetime(row[date_col]).date()),
                "outbreak_probability": float(row["predicted_probability"]),
                "severity": str(row["severity"]),
                "alert": bool(int(row["is_alert"])),
                "trend": _trend_label(delta),
                "trend_delta": delta,
                "forecast_horizon_days": horizon_days,
                "likely_disease": disease_meta["likely_disease"],
                "disease_family": disease_meta["disease_family"],
                "outbreak_type": disease_meta["outbreak_type"],
                "key_symptoms": disease_meta["key_symptoms"],
            }
        )

    headline = "No immediate high-risk outbreaks detected."
    if regions:
        top = regions[0]
        if top["alert"]:
            headline = (
                f"High attention: {top['region']} shows {top['severity']} risk "
                f"for potential outbreak within {horizon_days} days."
            )
        else:
            headline = (
                f"Watchlist: {top['region']} has the highest current risk, "
                f"but is below the alert threshold."
            )

    outlook = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "headline": headline,
        "regions": regions,
    }
    return outlook, latest


def _trend_delta(series: pd.Series) -> float:
    clean = series.astype(float).dropna()
    if len(clean) < 6:
        return 0.0

    tail = clean.tail(7)
    head = clean.iloc[-14:-7] if len(clean) >= 14 else clean.head(max(1, len(clean) // 2))
    return float(tail.mean() - head.mean())


def _trend_label(delta: float) -> str:
    if delta > 0.03:
        return "rising"
    if delta < -0.03:
        return "falling"
    return "stable"


def _infer_disease_profile(term_counts: Dict[str, int]) -> Dict[str, Any]:
    weights = {
        "viral_flu": 0,
        "vector_viral": 0,
        "water_bacterial": 0,
        "generic": 0,
    }

    for raw_term, count in term_counts.items():
        term = raw_term.lower()
        c = int(count)
        if any(k in term for k in ["flu", "influenza", "covid", "respiratory"]):
            weights["viral_flu"] += c
        elif any(k in term for k in ["dengue", "chikungunya", "zika", "mosquito", "fever"]):
            weights["vector_viral"] += c
        elif any(k in term for k in ["cholera", "typhoid", "waterborne", "diarrhea"]):
            weights["water_bacterial"] += c
        else:
            weights["generic"] += c

    dominant = max(weights, key=weights.get) if weights else "generic"

    if dominant == "viral_flu":
        return {
            "likely_disease": "influenza-like viral illness",
            "disease_family": "viral",
            "outbreak_type": "epidemic-prone respiratory wave",
            "key_symptoms": ["fever", "cough", "sore throat", "body ache", "fatigue"],
        }
    if dominant == "vector_viral":
        return {
            "likely_disease": "dengue-like viral fever",
            "disease_family": "viral",
            "outbreak_type": "seasonal epidemic (vector-borne)",
            "key_symptoms": ["high fever", "headache", "joint pain", "rash", "nausea"],
        }
    if dominant == "water_bacterial":
        return {
            "likely_disease": "acute water-borne infection",
            "disease_family": "bacterial",
            "outbreak_type": "localized epidemic cluster",
            "key_symptoms": ["watery diarrhea", "vomiting", "dehydration", "abdominal pain"],
        }

    return {
        "likely_disease": "undifferentiated febrile illness",
        "disease_family": "mixed/uncertain",
        "outbreak_type": "monitoring watch",
        "key_symptoms": ["fever", "fatigue", "headache"],
    }
