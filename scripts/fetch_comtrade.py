"""OPTIONAL connector: download monthly UN Comtrade rice data through the official API into data/raw (git-ignored).

Read the provider's terms first (docs/DATA_PROVENANCE.md). Opt-in is explicit: the script refuses to run unless
--accept-comtrade-terms is given. Behaviour: sequential requests with a pause, cached months are never re-requested,
a per-run call budget (--max-calls), and a clean stop when the provider reports that a quota is used up.
Works without a key via the free preview endpoint; an optional key can be provided in COMTRADE_API_KEY (never in code).

    python scripts/fetch_comtrade.py --accept-comtrade-terms --view exports --start 202001 --end 202412 --max-calls 60
"""

from __future__ import annotations

import argparse
import sys

from rice_market.ingestion.comtrade import fetch_range
from rice_market.ingestion.http import QuotaExceeded


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument(
        "--accept-comtrade-terms", action="store_true", help="confirm that you have read the provider's terms"
    )
    ap.add_argument("--view", choices=["exports", "mirror"], default="exports")
    ap.add_argument("--start", required=True, help="first month, YYYYMM")
    ap.add_argument("--end", required=True, help="last month, YYYYMM")
    ap.add_argument("--max-calls", type=int, default=60, help="network calls allowed in this run (default 60)")
    args = ap.parse_args()
    if not args.accept_comtrade_terms:
        print(
            "REFUSED: pass --accept-comtrade-terms after reading the UN Comtrade terms (see docs/DATA_PROVENANCE.md)."
        )
        return 2
    try:
        stats = fetch_range(args.view, args.start, args.end, max_calls=args.max_calls)
    except QuotaExceeded as exc:
        print(f"STOPPED: {exc}")
        return 3
    print(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
