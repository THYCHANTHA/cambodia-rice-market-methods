"""Generate SYNTHETIC demonstration data and build the demo warehouse (data/demo/, git-ignored).

    python scripts/make_demo.py && streamlit run app/Home.py

The numbers are invented by a seeded random generator; they are not trade statistics.
"""

from __future__ import annotations

import json
import sys

from rice_market.demo import BANNER, build_demo


def main() -> int:
    print(BANNER)
    print(json.dumps(build_demo(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
