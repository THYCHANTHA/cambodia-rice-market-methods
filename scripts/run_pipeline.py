"""Pipeline: (optional downloads) -> build warehouse from data/raw -> forecast experiment.

By default nothing is downloaded: put your own files in data/raw (MEF files via scripts/import_mef.py) or use the
optional connectors explicitly:

    python scripts/run_pipeline.py                         # build from whatever is already in data/raw
    python scripts/run_pipeline.py --pink-sheet            # also download the Pink Sheet workbook
    python scripts/run_pipeline.py --comtrade --accept-comtrade-terms --start 202001 --end 202412 --max-calls 60
"""

from __future__ import annotations

import argparse
import sys

from rice_market import config
from rice_market.forecasting.experiment import run as run_experiment
from rice_market.ingestion.comtrade import fetch_range
from rice_market.ingestion.http import QuotaExceeded
from rice_market.ingestion.sources import fetch_comtrade_reference, fetch_pink_sheet
from rice_market.transformation.build import build


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pink-sheet", action="store_true", help="download the Pink Sheet workbook (optional connector)")
    ap.add_argument("--comtrade", action="store_true", help="download Comtrade months (optional connector)")
    ap.add_argument("--accept-comtrade-terms", action="store_true")
    ap.add_argument("--start", help="first Comtrade month YYYYMM")
    ap.add_argument("--end", help="last Comtrade month YYYYMM")
    ap.add_argument("--max-calls", type=int, default=60)
    args = ap.parse_args()

    if args.pink_sheet:
        print("Pink Sheet downloaded:", fetch_pink_sheet())
    if args.comtrade:
        if not (args.accept_comtrade_terms and args.start and args.end):
            print("REFUSED: --comtrade needs --accept-comtrade-terms, --start and --end (see docs/DATA_PROVENANCE.md).")
            return 2
        print("Comtrade code lists:", fetch_comtrade_reference())
        try:
            for view in ("exports", "mirror"):
                print(f"Comtrade {view}:", fetch_range(view, args.start, args.end, max_calls=args.max_calls))
        except QuotaExceeded as exc:
            print(f"STOPPED: {exc}")
            return 3
    print("Build:", build(manifest=config.DOWNLOAD_MANIFEST))
    rec = run_experiment(out_dir=config.LOCAL_REPORTS / "experiments")
    for sid, info in rec["series"].items():
        print("Forecast", sid, info.get("status"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
