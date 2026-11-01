"""Parse rice benchmark columns from the World Bank Pink Sheet (sheet 'Monthly Prices')."""

from __future__ import annotations

import re
from pathlib import Path

import openpyxl
import pandas as pd

from rice_market import config

PERIOD_RE = re.compile(r"^(\d{4})M(\d{2})$")
MISSING_MARKERS = {"..", "…", "...", "", "n/a"}


def parse_period(label: str) -> pd.Timestamp:
    m = PERIOD_RE.match(str(label).strip())
    if not m:
        raise ValueError(f"not a Pink Sheet period: {label!r}")
    return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)


def parse_value(cell: object) -> float | None:
    if cell is None:
        return None
    if isinstance(cell, (int, float)):
        return float(cell)
    s = str(cell).strip()
    if s.lower() in MISSING_MARKERS or s.startswith("#"):  # '#VALUE!' etc. are spreadsheet errors, not prices
        return None
    return float(s)


def is_error_cell(cell: object) -> bool:
    return isinstance(cell, str) and cell.strip().startswith("#")


def load_rice_prices(path: Path) -> tuple[pd.DataFrame, dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = list(wb["Monthly Prices"].iter_rows(values_only=True))
    header, units = rows[4], rows[5]
    cols = {i: config.PINK_SHEET_RICE_COLUMNS[h] for i, h in enumerate(header) if h in config.PINK_SHEET_RICE_COLUMNS}
    if len(cols) != len(config.PINK_SHEET_RICE_COLUMNS):
        raise ValueError(f"expected rice columns not all found: {sorted(cols.values())}")
    meta = {"updated_note": str(rows[3][0]), "units": {cols[i]: str(units[i]) for i in cols}}
    out, error_cells = [], []
    for r in rows[6:]:
        if r[0] is None or not PERIOD_RE.match(str(r[0]).strip()):
            continue
        period = parse_period(r[0])
        for i, name in cols.items():
            if is_error_cell(r[i]):
                error_cells.append({"period": str(period.date()), "series": name, "value": str(r[i]).strip()})
            out.append({"period": period, "series": name, "usd_per_tonne": parse_value(r[i])})
    meta["error_cells"] = error_cells
    return pd.DataFrame(out), meta
