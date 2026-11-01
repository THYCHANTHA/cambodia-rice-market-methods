"""OPTIONAL: download the World Bank Pink Sheet workbook and the Comtrade code lists into data/raw (git-ignored).

    python scripts/fetch_optional_sources.py --pink-sheet --comtrade-reference

Nothing is downloaded unless a flag is given. (There is deliberately no MEF downloader: use scripts/import_mef.py.)
"""

from __future__ import annotations

import argparse
import sys

from rice_market.ingestion.sources import fetch_comtrade_reference, fetch_pink_sheet


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pink-sheet", action="store_true")
    ap.add_argument("--comtrade-reference", action="store_true")
    args = ap.parse_args()
    if not (args.pink_sheet or args.comtrade_reference):
        ap.print_help()
        return 0
    if args.pink_sheet:
        print("Pink Sheet downloaded:", fetch_pink_sheet())
    if args.comtrade_reference:
        print("Comtrade code lists:", fetch_comtrade_reference())
    return 0


if __name__ == "__main__":
    sys.exit(main())
