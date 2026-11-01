"""Paths, classification constants and optional-connector endpoints. No secrets live here.

The optional Comtrade key is read from the environment and is never printed or stored. There is deliberately **no**
endpoint or dataset identifier for the Cambodia Data EF / MEF portal: MEF files are imported manually from local copies
(see docs/RELEASE_LIMITATIONS.md for why automated retrieval is disabled).
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("RICE_MARKET_ROOT", Path(__file__).resolve().parents[3]))
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
MARTS = ROOT / "data" / "marts"
MANIFESTS = ROOT / "data" / "manifests"
DB_PATH = MARTS / "rice_market.duckdb"  # the user's own warehouse, built from data the user supplied or downloaded
DEMO_RAW = ROOT / "data" / "demo" / "raw"  # SYNTHETIC files written by scripts/make_demo.py
DEMO_DB_PATH = ROOT / "data" / "demo" / "demo.duckdb"  # SYNTHETIC demonstration warehouse
DOWNLOAD_MANIFEST = MANIFESTS / "downloads.jsonl"
LOCAL_REPORTS = ROOT / "reports" / "local"  # git-ignored output of local analysis scripts
EXPERIMENT_CONFIG = ROOT / "configs" / "experiments.yaml"

CAMBODIA_COMTRADE_CODE = 116  # UN Comtrade reporter code used by the optional connector
# HS 6-digit rice codes (HS 1006). 1006 is the 4-digit heading; the others are its children.
HS_RICE = {
    "1006": "Rice (heading total, all categories)",
    "100610": "Rice in the husk (paddy or rough)",
    "100620": "Husked (brown) rice",
    "100630": "Semi-milled or wholly milled rice",
    "100640": "Broken rice",
}
HS_CHILDREN = ["100610", "100620", "100630", "100640"]

# Optional connectors (user-initiated only; see docs/DATA_PROVENANCE.md for terms)
COMTRADE_PREVIEW_URL = "https://comtradeapi.un.org/public/v1/preview/C/M/HS"
COMTRADE_KEYED_URL = "https://comtradeapi.un.org/data/v1/get/C/M/HS"
PINK_SHEET_URL = (
    "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)
PINK_SHEET_RICE_COLUMNS = {
    "Rice, Thai 5% ": "rice_thai_5",
    "Rice, Thai 25% ": "rice_thai_25",
    "Rice, Thai A.1": "rice_thai_a1",
    "Rice, Viet Namese 5%": "rice_viet_5",
}


def comtrade_key() -> str | None:
    """Optional subscription key. Never printed or stored; the toolkit works without it."""
    return os.environ.get("COMTRADE_API_KEY") or None
