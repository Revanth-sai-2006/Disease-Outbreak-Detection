from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import os
from typing import Any, Dict, List, Tuple
from urllib.parse import quote, quote_plus
from xml.etree import ElementTree

import numpy as np
import pandas as pd
import requests


def fetch_web_surveillance_data(config: Dict[str, Any]) -> pd.DataFrame:
    frame, _context = fetch_web_surveillance_bundle(config)
    return frame


def fetch_web_surveillance_bundle(config: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    web_cfg = config.get("web", {})
    regions: List[str] = list(web_cfg.get("regions", ["India", "United States", "Brazil", "Germany"]))
    terms: List[str] = list(web_cfg.get("live_search_terms", ["disease outbreak", "fever cases", "flu surge"]))
    history_days = int(web_cfg.get("history_days", 160))
    lookback_days = int(web_cfg.get("live_search_lookback_days", 3))
    timeout = int(web_cfg.get("request_timeout_seconds", 20))
    weather_cfg = config.get("apis", {}).get("weather", {})
    weather_key = _clean_optional_str(weather_cfg.get("api_key")) or _clean_optional_str(os.environ.get("OPENWEATHER_API_KEY"))
    weather_base_url = str(weather_cfg.get("base_url", "https://api.openweathermap.org/data/2.5/weather"))
    weather_units = str(weather_cfg.get("units", "metric"))
    data_gov_cfg = config.get("apis", {}).get("data_gov_in", {})
    data_gov_key = _clean_optional_str(data_gov_cfg.get("api_key")) or _clean_optional_str(os.environ.get("DATA_GOV_IN_API_KEY"))
    data_gov_resource_id = _clean_optional_str(os.environ.get("DATA_GOV_IN_RESOURCE_ID")) or _clean_optional_str(
        data_gov_cfg.get("resource_id")
    )
    if data_gov_resource_id:
        data_gov_cfg = {**data_gov_cfg, "resource_id": data_gov_resource_id}

    region_frames: List[pd.DataFrame] = []
    news_counts: Dict[str, int] = {}
    term_profiles: Dict[str, Dict[str, int]] = {}
    weather_profiles: Dict[str, Dict[str, Any]] = {}
    history_by_region: Dict[str, pd.DataFrame] = {}
    data_gov_status: Dict[str, Any] = {
        "configured": bool(data_gov_key and data_gov_resource_id),
        "resource_id": data_gov_resource_id,
        "error": None,
        "regions_covered": [],
    }

    if data_gov_status["configured"]:
        try:
            data_gov_df = _fetch_data_gov_history(
                regions=regions,
                data_gov_cfg=data_gov_cfg,
                api_key=data_gov_key,
                timeout=timeout,
            )
            if not data_gov_df.empty:
                for region in regions:
                    region_df = data_gov_df.loc[data_gov_df["region"] == region, ["report_date", "hospital_cases"]].copy()
                    if not region_df.empty:
                        history_by_region[region] = region_df
                data_gov_status["regions_covered"] = sorted(history_by_region.keys())
        except Exception as exc:
            data_gov_status["error"] = str(exc)

    for region in regions:
        history_df = history_by_region.get(region)
        if history_df is None or history_df.empty:
            history_df = _fetch_region_history_with_fallback(region=region, history_days=history_days, timeout=timeout)
        term_counts = _fetch_live_search_profile(region=region, terms=terms, lookback_days=lookback_days, timeout=timeout)
        news_counts[region] = int(sum(term_counts.values()))
        term_profiles[region] = term_counts
        weather_profiles[region] = _fetch_current_weather_profile(
            region=region,
            api_key=weather_key,
            base_url=weather_base_url,
            units=weather_units,
            timeout=timeout,
        )
        history_df["region"] = region
        region_frames.append(history_df)

    if not region_frames:
        raise ValueError("No web data could be downloaded for configured regions.")

    max_news = max(news_counts.values()) if news_counts else 1
    max_news = max(max_news, 1)

    out_frames: List[pd.DataFrame] = []
    for frame in region_frames:
        region = str(frame["region"].iloc[0])
        news_score = float(news_counts.get(region, 0) / max_news)
        weather_risk_scalar = float(weather_profiles.get(region, {}).get("risk", 0.0))

        trend = frame["hospital_cases"].rolling(window=7, min_periods=2).mean().pct_change().fillna(0.0)
        trend_norm = _minmax(trend)

        volatility = frame["hospital_cases"].rolling(window=14, min_periods=2).std().fillna(0.0)
        volatility_norm = _minmax(volatility)

        frame = frame.copy()
        frame["social_signal_index"] = np.clip((0.65 * trend_norm) + (0.35 * news_score), 0.0, 1.0)
        weather_component = np.clip((0.55 * volatility_norm) + (0.45 * weather_risk_scalar), 0.0, 1.0)
        frame["weather_risk_index"] = np.clip((0.45 * trend_norm) + (0.55 * weather_component), 0.0, 1.0)
        out_frames.append(frame)

    out = pd.concat(out_frames, ignore_index=True)
    out.sort_values(["region", "report_date"], inplace=True)
    out.reset_index(drop=True, inplace=True)
    context = {
        "term_profiles": term_profiles,
        "weather_profiles": weather_profiles,
        "regions": regions,
        "live_search_terms": terms,
        "live_search_lookback_days": lookback_days,
        "weather_api_configured": bool(weather_key),
        "data_gov_in": data_gov_status,
    }
    return out, context


def _fetch_data_gov_history(
    regions: List[str],
    data_gov_cfg: Dict[str, Any],
    api_key: str,
    timeout: int,
) -> pd.DataFrame:
    base_url = str(data_gov_cfg.get("base_url", "https://api.data.gov.in/resource")).rstrip("/")
    resource_id = _clean_optional_str(data_gov_cfg.get("resource_id"))
    date_field = str(data_gov_cfg.get("date_field", "report_date"))
    cases_field = str(data_gov_cfg.get("cases_field", "hospital_cases"))
    region_field = str(data_gov_cfg.get("region_field", "state"))
    page_size = int(data_gov_cfg.get("limit", 1000))
    max_pages = int(data_gov_cfg.get("max_pages", 10))
    extra_filters = dict(data_gov_cfg.get("filters", {}))

    if not resource_id:
        raise ValueError("apis.data_gov_in.resource_id is required when data.gov.in source is configured")

    url = f"{base_url}/{quote(resource_id)}"

    records: List[Dict[str, Any]] = []
    for page in range(max_pages):
        offset = page * page_size
        params: Dict[str, Any] = {
            "api-key": api_key,
            "format": "json",
            "limit": page_size,
            "offset": offset,
        }
        params.update(extra_filters)

        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()

        page_records = payload.get("records", [])
        if not page_records:
            break
        records.extend(page_records)

        if len(page_records) < page_size:
            break

    if not records:
        return pd.DataFrame(columns=["report_date", "region", "hospital_cases"])

    frame = pd.DataFrame(records)
    required = [date_field, cases_field]
    missing = [name for name in required if name not in frame.columns]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Configured data.gov.in fields missing from response: {joined}")

    if region_field not in frame.columns:
        frame[region_field] = "India"

    frame = frame.rename(
        columns={
            date_field: "report_date",
            region_field: "region",
            cases_field: "hospital_cases",
        }
    )
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce")
    frame["hospital_cases"] = pd.to_numeric(frame["hospital_cases"], errors="coerce")
    frame["region"] = frame["region"].astype(str).str.strip()
    frame = frame.dropna(subset=["report_date", "hospital_cases"])

    if frame.empty:
        return pd.DataFrame(columns=["report_date", "region", "hospital_cases"])

    requested = {_normalize_region_name(region): region for region in regions}
    frame["_region_key"] = frame["region"].map(_normalize_region_name)
    frame = frame[frame["_region_key"].isin(requested)]
    frame["region"] = frame["_region_key"].map(requested)
    frame = frame.drop(columns=["_region_key"])

    if frame.empty:
        return pd.DataFrame(columns=["report_date", "region", "hospital_cases"])

    grouped = (
        frame.groupby(["region", "report_date"], as_index=False)["hospital_cases"]
        .sum()
        .sort_values(["region", "report_date"])
        .reset_index(drop=True)
    )
    return grouped


def _normalize_region_name(value: str) -> str:
    return " ".join(str(value).strip().lower().split())


def _clean_optional_str(value: Any) -> str:
    text = str(value or "").strip()
    if text.lower() in {"", "none", "null"}:
        return ""
    return text


def _fetch_current_weather_profile(
    region: str,
    api_key: str,
    base_url: str,
    units: str,
    timeout: int,
) -> Dict[str, Any]:
    if not api_key:
        return {"risk": 0.0, "source": "fallback", "reason": "missing_api_key"}

    params = {"q": region, "appid": api_key, "units": units}
    try:
        response = requests.get(base_url, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json()

        main = payload.get("main", {})
        weather = payload.get("weather", [])
        temp = float(main.get("temp", 0.0) or 0.0)
        humidity = float(main.get("humidity", 0.0) or 0.0)
        condition = str(weather[0].get("main", "")) if weather else ""

        temp_risk = np.clip((temp - 20.0) / 20.0, 0.0, 1.0)
        humidity_risk = np.clip((humidity - 50.0) / 50.0, 0.0, 1.0)
        condition_risk = 0.2 if condition.lower() in {"rain", "thunderstorm", "drizzle", "mist", "haze"} else 0.0
        risk = float(np.clip((0.4 * temp_risk) + (0.4 * humidity_risk) + condition_risk, 0.0, 1.0))

        return {
            "risk": round(risk, 4),
            "source": "openweather",
            "temp": temp,
            "humidity": humidity,
            "condition": condition,
        }
    except Exception as exc:
        return {"risk": 0.0, "source": "fallback", "reason": str(exc)}


def _fetch_region_history_with_fallback(region: str, history_days: int, timeout: int) -> pd.DataFrame:
    try:
        return _fetch_country_history(region=region, history_days=history_days, timeout=timeout)
    except Exception:
        # Region-level APIs are inconsistent by country; use a smooth baseline and let live search volume
        # drive near-term signal when direct historical series is unavailable.
        return _build_fallback_history(region=region, history_days=history_days)


def _fetch_country_history(region: str, history_days: int, timeout: int) -> pd.DataFrame:
    region_slug = quote(region)
    url = f"https://disease.sh/v3/covid-19/historical/{region_slug}?lastdays={history_days}"

    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()

    timeline = payload.get("timeline", {})
    cases = timeline.get("cases", {})
    if not cases:
        raise ValueError(f"Historical report payload for region '{region}' has no case timeline.")

    raw = pd.Series(cases, dtype="float64")
    raw.index = pd.to_datetime(raw.index, format="%m/%d/%y", errors="coerce")
    raw = raw[~raw.index.isna()].sort_index()

    daily_new = raw.diff().fillna(0.0).clip(lower=0.0)
    smoothed = daily_new.rolling(window=3, min_periods=1).mean()

    return pd.DataFrame(
        {
            "report_date": smoothed.index,
            "hospital_cases": smoothed.values,
        }
    )


def _build_fallback_history(region: str, history_days: int) -> pd.DataFrame:
    seed = abs(hash(region)) % (2**32)
    rng = np.random.default_rng(seed)

    dates = pd.date_range(end=pd.Timestamp.today().normalize(), periods=history_days, freq="D")
    t = np.arange(history_days, dtype=float)

    baseline = 8.0 + 2.0 * np.sin((2.0 * np.pi * t / 30.0) + (seed % 11))
    noise = rng.normal(0.0, 0.8, history_days)
    series = np.clip(baseline + noise, 0.0, None)

    return pd.DataFrame({"report_date": dates, "hospital_cases": series})


def _fetch_live_search_profile(region: str, terms: List[str], lookback_days: int, timeout: int) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for term in terms:
        query = quote_plus(f"{term} {region}")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

        response = requests.get(url, timeout=timeout)
        response.raise_for_status()

        root = ElementTree.fromstring(response.content)
        items = root.findall("./channel/item")

        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        count = 0
        for item in items:
            pub_date_elem = item.find("pubDate")
            if pub_date_elem is None or not pub_date_elem.text:
                continue
            try:
                published_at = parsedate_to_datetime(pub_date_elem.text)
            except (TypeError, ValueError):
                continue

            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=timezone.utc)

            if published_at >= cutoff:
                count += 1

        counts[term] = count

    return counts


def _minmax(series: pd.Series) -> pd.Series:
    minimum = float(series.min())
    maximum = float(series.max())
    if np.isclose(maximum, minimum):
        return pd.Series(np.zeros(len(series), dtype=float), index=series.index)
    return (series - minimum) / (maximum - minimum)
