"""Import locally downloaded MEF / Data EF rice-export CSV files (manual import; no network access).

Download the CSV files yourself from the portal, under its terms of use, then:

    python scripts/import_mef.py path/to/file1.csv path/to/file2.csv

Every file is validated with the strict parser first; if any file is refused nothing is copied.
Why there is no downloader: docs/RELEASE_LIMITATIONS.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rice_market.ingestion.manual_import import ImportRefused, import_files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path, help="local MEF CSV files")
    args = ap.parse_args()
    try:
        summaries = import_files(args.files)
    except ImportRefused as exc:
        print(f"REFUSED: {exc}")
        return 2
    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
