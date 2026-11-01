"""Rebuild the DuckDB warehouse (data/marts/rice_market.duckdb) from whatever files exist in data/raw."""

from __future__ import annotations

import json
import sys

from rice_market import config
from rice_market.transformation.build import build


def main() -> int:
    print(json.dumps(build(manifest=config.DOWNLOAD_MANIFEST), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
