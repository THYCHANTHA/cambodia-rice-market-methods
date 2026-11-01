"""Startup verification. Exit code 0 only if a warehouse is resolved and every required table exists and is non-empty.

Uses the same resolution as the dashboard (your warehouse, else the synthetic demo, else none):

    python scripts/health_check.py && streamlit run app/Home.py

A running Streamlit server also answers http://127.0.0.1:8501/_stcore/health.
Exit codes: 0 healthy, 1 a table is empty or missing, 2 no warehouse.
"""

from __future__ import annotations

import json
import sys

from rice_market import data_access as da


def main() -> int:
    path, mode = da.resolve_database()
    if path is None:
        print(
            "FAIL: no warehouse found. Build synthetic demo data with `python scripts/make_demo.py`, or your own with "
            "`python scripts/run_pipeline.py`."
        )
        return 2
    report = da.health(da.connect(path))
    print(json.dumps({"mode": mode, **report}, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
