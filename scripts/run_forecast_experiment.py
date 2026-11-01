"""Run the rolling-origin forecast experiment on the built warehouse (settings: configs/experiments.yaml)."""

from __future__ import annotations

import sys

from rice_market import config
from rice_market.forecasting.experiment import run


def main() -> int:
    rec = run(out_dir=config.LOCAL_REPORTS / "experiments")
    for sid, info in rec["series"].items():
        print(sid, info.get("status"), info.get("n_months"), "months;", info.get("n_origins"), "origins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
