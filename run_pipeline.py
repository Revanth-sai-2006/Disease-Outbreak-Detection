from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from outbreak_detection.pipeline import run_pipeline


if __name__ == "__main__":
    summary = run_pipeline(str(ROOT / "config.yaml"))
    print(summary)
