"""Optional connectors: the World Bank Pink Sheet workbook and the Comtrade code lists.

There is deliberately no connector for the Cambodia Data EF / MEF portal. MEF files are imported manually from local
copies (`ingestion/manual_import.py`). Everything here is user-initiated; nothing runs at import time.
"""

from __future__ import annotations

from rice_market import config
from rice_market.ingestion.http import get_with_retry, record_download

COMTRADE_REFERENCE = {
    "partnerAreas.json": "https://comtradeapi.un.org/files/v1/app/reference/partnerAreas.json",
    "HS.json": "https://comtradeapi.un.org/files/v1/app/reference/HS.json",
}


def fetch_pink_sheet(force: bool = False) -> bool:
    """Download the Pink Sheet monthly workbook once (cached). Attribution and terms: docs/DATA_PROVENANCE.md."""
    path = config.RAW / "worldbank" / "CMO-Historical-Data-Monthly.xlsx"
    if path.exists() and not force:
        return False
    resp = get_with_retry(config.PINK_SHEET_URL)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    record_download("worldbank_pink_sheet", config.PINK_SHEET_URL, path, resp.content, note="monthly prices xlsx")
    return True


def fetch_comtrade_reference(force: bool = False) -> dict[str, bool]:
    """Official Comtrade code lists (partner areas, HS commodities); rows from the API carry codes only."""
    out = {}
    for name, url in COMTRADE_REFERENCE.items():
        path = config.RAW / "comtrade" / "reference" / name
        if path.exists() and not force:
            out[name] = False
            continue
        resp = get_with_retry(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(resp.content)
        record_download("comtrade_reference", url, path, resp.content)
        out[name] = True
    return out
