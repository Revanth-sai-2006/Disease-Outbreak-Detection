from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List

import yaml

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from outbreak_detection.pipeline import run_pipeline
from outbreak_detection.utils import load_config


def _parse_regions(raw: str) -> List[str]:
    regions = [item.strip() for item in raw.split(",") if item.strip()]
    deduped: List[str] = []
    for region in regions:
        if region not in deduped:
            deduped.append(region)
    if not deduped:
        raise ValueError("No valid regions provided. Use comma-separated city/region names.")
    return deduped


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run outbreak pipeline for user-requested city/region list."
    )
    parser.add_argument(
        "--regions",
        required=True,
        help='Comma-separated cities/regions. Example: "Pune, Hyderabad, Chennai"',
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Base config path. Default: config.yaml",
    )

    args = parser.parse_args()
    regions = _parse_regions(args.regions)

    config = load_config(args.config)
    config.setdefault("web", {})
    config["web"]["regions"] = regions

    runtime_config_path = ROOT / "outputs" / "runtime_config_custom.yaml"
    runtime_config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(runtime_config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, sort_keys=False)

    summary = run_pipeline(str(runtime_config_path))
    print("Generated report for regions:")
    print(", ".join(regions))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
