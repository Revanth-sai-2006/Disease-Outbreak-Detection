from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml
from flask import Flask, jsonify, request, send_from_directory

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from outbreak_detection.pipeline import run_pipeline
from outbreak_detection.utils import load_config

app = Flask(__name__, static_folder=str(ROOT / "outputs"), static_url_path="/outputs")


def _safe_slug(text: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return cleaned or "city"


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _dispatch_phc_alerts(mode: str = "manual") -> Dict[str, Any]:
    config = load_config(str(ROOT / "config.yaml"))
    outlook = _read_json(ROOT / "outputs" / "region_outlook.json")

    regions = outlook.get("regions", []) if isinstance(outlook, dict) else []
    contacts = config.get("notifications", {}).get("phc_contacts", {}) if isinstance(config, dict) else {}
    severity_trigger = {"high", "critical"}

    dispatched = []
    for item in regions:
        region = str(item.get("region", "Unknown Region"))
        severity = str(item.get("severity", "low")).lower()
        probability = float(item.get("outbreak_probability", 0) or 0)
        should_alert = bool(item.get("alert")) or severity in severity_trigger or probability >= 0.8
        if not should_alert:
            continue

        default_contact = {
            "phc_name": f"{region} PHC",
            "channel": "email",
            "destination": f"{_safe_slug(region)}@local-phc.gov.in",
        }
        configured_contact = contacts.get(region, {}) if isinstance(contacts, dict) else {}
        phc_contact = {**default_contact, **(configured_contact if isinstance(configured_contact, dict) else {})}

        dispatched.append(
            {
                "region": region,
                "severity": severity,
                "outbreak_probability": round(probability, 3),
                "message": (
                    f"Outbreak watch alert for {region}. "
                    f"Severity: {severity}. Probability: {probability:.3f}."
                ),
                "phc_contact": phc_contact,
            }
        )

    payload = {
        "mode": mode,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "outlook_generated_at_utc": outlook.get("generated_at_utc", ""),
        "alerts_dispatched": len(dispatched),
        "alerts": dispatched,
    }
    _write_json(ROOT / "outputs" / "phc_alert_dispatch_log.json", payload)
    return payload


@app.get("/")
def root() -> Any:
    return send_from_directory(str(ROOT / "outputs"), "index.html")


@app.get("/api/dashboard")
def api_dashboard() -> Any:
    summary = _read_json(ROOT / "outputs" / "pipeline_summary.json")
    outlook = _read_json(ROOT / "outputs" / "region_outlook.json")
    source_status = _read_json(ROOT / "outputs" / "data_source_status.json")

    if not summary or not outlook:
        run_pipeline(str(ROOT / "config.yaml"))
        summary = _read_json(ROOT / "outputs" / "pipeline_summary.json")
        outlook = _read_json(ROOT / "outputs" / "region_outlook.json")
        source_status = _read_json(ROOT / "outputs" / "data_source_status.json")

    return jsonify({"summary": summary, "outlook": outlook, "source_status": source_status})


@app.get("/api/city-report")
def api_city_report() -> Any:
    city = (request.args.get("city") or "").strip()
    if not city:
        return jsonify({"error": "Query parameter 'city' is required."}), 400

    if len(city) > 80:
        return jsonify({"error": "City name is too long."}), 400

    config = load_config(str(ROOT / "config.yaml"))
    config.setdefault("web", {})
    config["web"]["regions"] = [city]

    runtime_cfg = ROOT / "outputs" / f"runtime_config_{_safe_slug(city)}.yaml"
    runtime_cfg.parent.mkdir(parents=True, exist_ok=True)
    runtime_cfg.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    summary = run_pipeline(str(runtime_cfg))
    outlook = _read_json(ROOT / "outputs" / "region_outlook.json")
    source_status = _read_json(ROOT / "outputs" / "data_source_status.json")

    region = None
    for item in outlook.get("regions", []):
        if str(item.get("region", "")).lower() == city.lower():
            region = item
            break
    if region is None and outlook.get("regions"):
        region = outlook["regions"][0]

    return jsonify(
        {
            "city": city,
            "summary": summary,
            "region": region,
            "source_status": source_status,
            "headline": outlook.get("headline", ""),
            "generated_at_utc": outlook.get("generated_at_utc", ""),
        }
    )


@app.post("/api/phc-alert-dispatch")
def api_phc_alert_dispatch() -> Any:
    body = request.get_json(silent=True) or {}
    mode = str(body.get("mode", "manual"))
    if mode not in {"manual", "automatic"}:
        mode = "manual"
    payload = _dispatch_phc_alerts(mode=mode)
    return jsonify(payload)


@app.get("/api/phc-alert-dispatch")
def api_phc_alert_status() -> Any:
    log = _read_json(ROOT / "outputs" / "phc_alert_dispatch_log.json")
    if not log:
        return jsonify({"status": "idle", "alerts_dispatched": 0, "message": "No PHC alert dispatch yet."})
    return jsonify(log)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
