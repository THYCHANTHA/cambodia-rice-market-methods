"""Parse locally supplied MEF / Data EF rice-export CSV files into one tidy table WITHOUT merging or overwriting any.

Two layouts are supported (the layouts the portal's CSV downloads use):
  * long layout: columns month,year,export_metric_tons; month is an abbreviation such as "jan";
  * wide-by-year layout: header "Monthly,<year>", twelve "Mon,<value>" rows and a "Yearly Export,<total>" row, which may
    start with a UTF-8 byte-order mark.
A blank value is a missing month ('missing'), never zero. Files are imported manually (ingestion/manual_import.py).
"""

from __future__ import annotations

import io
from pathlib import Path

import pandas as pd

MONTHS = {
    m: i
    for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)
}


def month_number(label: str) -> int:
    key = str(label).strip().lower()[:3]
    if key not in MONTHS:
        raise ValueError(f"unrecognised month label: {label!r}")
    return MONTHS[key]


def _number(text: object) -> float | None:
    """Strict numeric parse. A plain number such as 1234.0 is metric tons; thousands separators are NOT guessed."""
    s = "" if text is None else str(text).strip()
    if s == "" or s.lower() == "nan":
        return None
    if "," in s:
        raise ValueError(f"thousands separator in MEF value {s!r}; handle explicitly")
    return float(s)


def parse_long(text: str, dataset: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    expected = ["month", "year", "export_metric_tons"]
    if list(df.columns) != expected:
        raise ValueError(f"{dataset}: unexpected columns {list(df.columns)}")
    rows = []
    for rec in df.itertuples(index=False):
        year = int(float(rec.year))
        value = _number(rec.export_metric_tons)
        rows.append({"dataset": dataset, "year": year, "month": month_number(rec.month), "tonnes": value})
    out = pd.DataFrame(rows)
    return _finish(out), pd.DataFrame(columns=["dataset", "year", "reported_total_t"])


def parse_wide(text: str, dataset: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    lines = [ln for ln in text.lstrip("﻿").splitlines() if ln.strip()]
    head = lines[0].split(",")
    if head[0].strip().lower() != "monthly":
        raise ValueError(f"{dataset}: unexpected header {lines[0]!r}")
    year = int(head[1])
    rows, annual = [], []
    for ln in lines[1:]:
        label, _, val = ln.partition(",")
        if label.strip().lower().startswith("yearly"):
            annual.append({"dataset": dataset, "year": year, "reported_total_t": _number(val)})
        else:
            rows.append({"dataset": dataset, "year": year, "month": month_number(label), "tonnes": _number(val)})
    return _finish(pd.DataFrame(rows)), pd.DataFrame(annual)


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["period"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))
    df["status"] = df["tonnes"].map(lambda v: "missing" if pd.isna(v) else "reported")
    return df[["dataset", "period", "year", "month", "tonnes", "status"]].reset_index(drop=True)


def parse_file(path: Path, dataset: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    text = path.read_bytes().decode("utf-8")
    first = text.lstrip("﻿").splitlines()[0].lower()
    return parse_wide(text, dataset) if first.startswith("monthly") else parse_long(text, dataset)


def empty_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    monthly = pd.DataFrame(
        {
            "dataset": pd.Series(dtype="object"),
            "period": pd.Series(dtype="datetime64[ns]"),
            "year": pd.Series(dtype="int64"),
            "month": pd.Series(dtype="int64"),
            "tonnes": pd.Series(dtype="float64"),
            "status": pd.Series(dtype="object"),
        }
    )
    return monthly, pd.DataFrame(columns=["dataset", "year", "reported_total_t"])


def load_all(raw_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse every imported file (mef_*.csv); an absent source yields empty, correctly typed tables."""
    files = sorted(raw_dir.glob("mef_*.csv")) if raw_dir.exists() else []
    if not files:
        return empty_tables()
    monthly, annual = [], []
    for path in files:
        m, a = parse_file(path, path.stem)
        monthly.append(m)
        annual.append(a)
    return pd.concat(monthly, ignore_index=True), pd.concat(annual, ignore_index=True)
