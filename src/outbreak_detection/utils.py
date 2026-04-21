from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def ensure_parent_dir(file_path: str) -> None:
    Path(file_path).parent.mkdir(parents=True, exist_ok=True)


def load_environment(env_path: str = ".env") -> None:
    if Path(env_path).exists():
        load_dotenv(env_path)


def get_env(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def write_json(data: Any, output_path: str) -> None:
    ensure_parent_dir(output_path)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
