"""Manual local-file import for MEF / Data EF rice-export CSV files. **No network access.**

Why this exists instead of a downloader: the portal's terms prohibit "data mining" of the site and state no
redistribution conditions, so automated retrieval is disabled in this release until the publisher confirms in
writing that it is acceptable (docs/RELEASE_LIMITATIONS.md). The user downloads the files in a browser under the
portal's terms and imports them here. The import validates each file with the same strict parser used by the
pipeline before copying it, so a wrong or modified file is refused rather than silently accepted.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from rice_market import config
from rice_market.ingestion.http import record_download
from rice_market.transformation import mef

SAFE_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


class ImportRefused(ValueError):
    """The file is not a recognisable MEF rice-export CSV; nothing was copied."""


def validate_file(path: Path) -> dict:
    """Parse the file strictly and return a small summary. Raises ImportRefused with the reason otherwise."""
    if not path.is_file():
        raise ImportRefused(f"{path}: not a file")
    try:
        monthly, annual = mef.parse_file(path, path.stem)
    except Exception as exc:  # parser errors are the validation result
        raise ImportRefused(f"{path.name}: {type(exc).__name__}: {exc}") from exc
    if monthly.empty:
        raise ImportRefused(f"{path.name}: no monthly rows")
    if (monthly["tonnes"].dropna() < 0).any():
        raise ImportRefused(f"{path.name}: negative quantities")
    if monthly.duplicated(["period"]).any():
        raise ImportRefused(f"{path.name}: duplicate months")
    return {
        "rows": int(len(monthly)),
        "reported": int(monthly["tonnes"].notna().sum()),
        "first": str(monthly["period"].min().date()),
        "last_reported": str(monthly.loc[monthly["tonnes"].notna(), "period"].max().date())
        if monthly["tonnes"].notna().any()
        else None,
        "annual_rows": int(len(annual)),
    }


def import_files(paths: list[Path], raw_dir: Path | None = None) -> list[dict]:
    """Validate every file first; copy to data/raw/mef/mef_<name>.csv only if ALL pass (all-or-nothing)."""
    target = (raw_dir or config.RAW) / "mef"
    summaries = [validate_file(Path(p)) | {"source_file": Path(p).name} for p in paths]
    target.mkdir(parents=True, exist_ok=True)
    for src, summary in zip(paths, summaries, strict=True):
        name = SAFE_NAME.sub("_", Path(src).stem).strip("_")
        stem = name if name.startswith("mef_") else f"mef_{name}"
        dest = target / f"{stem}.csv"
        shutil.copyfile(src, dest)  # byte-for-byte; the user's file is never modified
        record_download(
            "mef_manual_import",
            f"local-file:{Path(src).name}",
            dest,
            dest.read_bytes(),
            note="imported manually by the user; no network access",
        )
        summary["stored_as"] = dest.name
    return summaries
