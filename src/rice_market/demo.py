"""SYNTHETIC demonstration data. Every number produced here is invented by a seeded random generator.

Purpose: let the dashboard and the pipeline be tried without any real data. Nothing here is derived from, or resembles
on purpose, any provider's data: the years are fictional (2030 onward), the exporter code and partner names are made up,
and volumes are on an arbitrary small scale. Files are written in the same formats the parsers read for real data.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import openpyxl

from rice_market import config

SEED = 20300101
FIRST_YEAR = 2030
N_YEARS = 5
EXPORTER_CODE = 9000  # fictional reporter
PARTNER_CODES = list(range(9001, 9013))
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
BANNER = "SYNTHETIC DEMONSTRATION DATA: invented by a random generator; not real trade statistics."


def _monthly_volumes(rng: np.random.Generator) -> np.ndarray:
    t = np.arange(12 * N_YEARS)
    season = 1 + 0.45 * np.sin(2 * np.pi * (t % 12 - 2) / 12)
    trend = 1 + 0.002 * t
    noise = rng.lognormal(0, 0.10, size=t.size)
    return 5000.0 * season * trend * noise  # tonnes, arbitrary scale


def _partner_shares(rng: np.random.Generator) -> np.ndarray:
    """Shares per year (N_YEARS x partners): a drifting mix so that concentration changes over time."""
    base = rng.dirichlet(np.linspace(3.0, 0.4, len(PARTNER_CODES)))
    shares = []
    for y in range(N_YEARS):
        w = base ** (1.0 - 0.12 * y)  # flatter mix in later years
        shares.append(w / w.sum())
    return np.array(shares)


def _row(year, month, cmd, reporter, partner, kg, price_per_kg, flow):
    value = kg * price_per_kg
    return {
        "refYear": year,
        "refMonth": month,
        "cmdCode": cmd,
        "reporterCode": reporter,
        "partnerCode": partner,
        "netWgt": float(kg),
        "qty": float(kg),
        "qtyUnitCode": 8,
        "fobvalue": float(value) if flow == "X" else None,
        "cifvalue": float(value * 1.08) if flow == "M" else None,
        "primaryValue": float(value if flow == "X" else value * 1.08),
        "isNetWgtEstimated": False,
        "isAggregate": True,
        "classificationCode": "H6",
    }


def write_synthetic_raw(raw_dir: Path, seed: int = SEED) -> dict:
    """Write synthetic MEF-style CSVs, Comtrade-style JSON (exports and mirror), code lists and a price workbook."""
    rng = np.random.default_rng(seed)
    raw_dir = Path(raw_dir)
    for sub in ("mef", "worldbank", "comtrade/exports", "comtrade/mirror", "comtrade/reference"):
        (raw_dir / sub).mkdir(parents=True, exist_ok=True)
    milled = _monthly_volumes(rng)
    shares = _partner_shares(rng)

    # --- MEF-style CSV (long layout over all years) and a wide single-year file that agrees with it
    lines = ["month,year,export_metric_tons"]
    blank_from = 12 * N_YEARS - 4  # last four months blank = "not yet reported"
    for k in range(12 * N_YEARS):
        y, m = FIRST_YEAR + k // 12, k % 12
        lines.append(f"{MONTHS[m]},{y},{'' if k >= blank_from else f'{milled[k]:.1f}'}")
    (raw_dir / "mef" / "mef_synthetic_all_years.csv").write_text("\r\n".join(lines), encoding="utf-8")
    y0 = FIRST_YEAR
    wide = [f"﻿Monthly,{y0}"] + [f"{MONTHS[m].title()},{milled[m]:.1f}" for m in range(12)]
    wide.append(f"Yearly Export,{sum(round(float(f'{milled[m]:.1f}'), 1) for m in range(12)):.1f}")
    (raw_dir / "mef" / "mef_synthetic_first_year.csv").write_bytes("\r\n".join(wide).encode("utf-8"))

    # --- Comtrade-style JSON
    names = [{"PartnerCode": 0, "PartnerDesc": "World", "PartnerCodeIsoAlpha3": "WLD", "isGroup": True}]
    for i, code in enumerate(PARTNER_CODES):
        names.append(
            {
                "PartnerCode": code,
                "PartnerDesc": f"Synthetic Partner {chr(65 + i)}",
                "PartnerCodeIsoAlpha3": f"S{chr(65 + i)}X",
                "isGroup": False,
            }
        )
    names.append(
        {
            "PartnerCode": EXPORTER_CODE,
            "PartnerDesc": "Synthetic Exporter",
            "PartnerCodeIsoAlpha3": "SEX",
            "isGroup": False,
        }
    )
    (raw_dir / "comtrade" / "reference" / "partnerAreas.json").write_text(
        json.dumps({"results": names}), encoding="utf-8"
    )
    price = 0.6
    for k in range(12 * N_YEARS):
        y, m = FIRST_YEAR + k // 12, k % 12 + 1
        tonnes = {"100630": milled[k], "100620": milled[k] * 0.03, "100640": milled[k] * 0.04}
        if k >= 12 * (N_YEARS - 2):  # paddy appears only in the last two synthetic years, and only in some months
            if k % 3 != 0:
                tonnes["100610"] = milled[k] * 0.15
        share = shares[k // 12]
        exports, mirror = [], []
        for cmd, t in tonnes.items():
            kg_total = t * 1000.0
            exports.append(_row(y, m, cmd, EXPORTER_CODE, 0, kg_total, price, "X"))
            for code, sh in zip(PARTNER_CODES, share, strict=True):
                exports.append(_row(y, m, cmd, EXPORTER_CODE, code, kg_total * sh, price, "X"))
                if cmd in ("100630", "100610") and not (code == PARTNER_CODES[-1] and k % 5 == 0):
                    kg_imp = kg_total * sh * rng.uniform(0.88, 1.04)
                    mirror.append(_row(y, m, cmd, code, EXPORTER_CODE, kg_imp, price, "M"))
        children = [r for r in exports if r["partnerCode"] == 0]
        total_kg = sum(r["netWgt"] for r in children)
        exports.append(_row(y, m, "1006", EXPORTER_CODE, 0, total_kg, price, "X"))
        for code in PARTNER_CODES:
            part_kg = sum(r["netWgt"] for r in exports if r["partnerCode"] == code and r["cmdCode"] != "1006")
            exports.append(_row(y, m, "1006", EXPORTER_CODE, code, part_kg, price, "X"))
        for view, rows in (("exports", exports), ("mirror", mirror)):
            payload = {"elapsedTime": "synthetic", "count": len(rows), "data": rows, "error": ""}
            (raw_dir / "comtrade" / view / f"{y}{m:02d}.json").write_text(json.dumps(payload), encoding="utf-8")

    # --- price workbook in the layout the parser reads (header row 5, units row 6, data from row 7)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Monthly Prices"
    ws.append(["Synthetic price workbook (not a World Bank file)"])
    ws.append(["synthetic monthly prices in nominal US dollars"])
    ws.append([""])
    ws.append(["Synthetic data, generated by rice_market.demo"])
    ws.append([None, "Rice, Thai 5% ", "Rice, Thai 25% ", "Rice, Thai A.1", "Rice, Viet Namese 5%"])
    ws.append([None, "($/mt)", "($/mt)", "($/mt)", "($/mt)"])
    walk = np.cumsum(rng.normal(0, 8, 12 * N_YEARS)) + 400.0
    for k in range(12 * N_YEARS):
        y, m = FIRST_YEAR + k // 12, k % 12 + 1
        ws.append(
            [f"{y}M{m:02d}", round(walk[k], 1), round(walk[k] - 25, 1), round(walk[k] - 60, 1), round(walk[k] - 10, 1)]
        )
    wb.save(raw_dir / "worldbank" / "CMO-Historical-Data-Monthly.xlsx")
    (raw_dir / "SYNTHETIC_DATA.txt").write_text(BANNER + "\n", encoding="utf-8")
    return {"months": 12 * N_YEARS, "partners": len(PARTNER_CODES), "first_year": FIRST_YEAR}


def build_demo(raw_dir: Path | None = None, db_path: Path | None = None) -> dict:
    """Generate synthetic raw files and build the demonstration warehouse (including the forecast backtests)."""
    from rice_market.forecasting.experiment import load_config, run
    from rice_market.transformation.build import build

    raw_dir = Path(raw_dir or config.DEMO_RAW)
    db_path = Path(db_path or config.DEMO_DB_PATH)
    info = write_synthetic_raw(raw_dir)
    summary = build(raw=raw_dir, db_path=db_path, manifest=None)
    cfg = load_config()
    cfg["min_months"] = 36
    run(db_path=db_path, out_dir=None, cfg=cfg)
    return info | summary
