"""Startup verification. Exit code 0 only if the warehouse exists, every required table is non-empty and the pages import.

Use before launching the dashboard:  python scripts/health_check.py && streamlit run app/Home.py
The running Streamlit server also answers http://127.0.0.1:8501/_stcore/health.
"""

from __future__ import annotations

import json
import sys

from rice_market import data_access as da


def main() -> int:
    try:
        con = da.connect()
    except da.WarehouseMissing as exc:
        print(f"FAIL: {exc}")
        return 2
    report = da.health(con)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
