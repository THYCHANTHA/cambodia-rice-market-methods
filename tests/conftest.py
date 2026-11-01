"""SYNTHETIC raw-data fixture. Every value is INVENTED for software testing only and resembles nothing real."""

import json

import openpyxl
import pandas as pd
import pytest


def _comtrade_row(year, month, cmd, partner, kg, fob, reporter=116, cls="H6"):
    return {
        "refYear": year,
        "refMonth": month,
        "cmdCode": cmd,
        "reporterCode": reporter,
        "partnerCode": partner,
        "netWgt": kg,
        "qty": kg,
        "qtyUnitCode": 8,
        "fobvalue": fob,
        "cifvalue": None,
        "primaryValue": fob,
        "isNetWgtEstimated": False,
        "isAggregate": True,
        "classificationCode": cls,
    }


@pytest.fixture
def synthetic_raw(tmp_path):
    raw = tmp_path / "raw"
    (raw / "mef").mkdir(parents=True)
    (raw / "worldbank").mkdir()
    (raw / "comtrade" / "exports").mkdir(parents=True)
    (raw / "comtrade" / "reference").mkdir()
    # MEF: multi-year long file (2 years, last 2 months of year 2 blank) + year-specific wide file for year 1
    rows = ["month,year,export_metric_tons"]
    mons = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    for y, base in ((2030, 100), (2031, 200)):
        for i, m in enumerate(mons):
            blank = y == 2031 and i >= 10
            rows.append(f"{m},{y},{'' if blank else float(base + i)}")
    (raw / "mef" / "mef_synthetic_multi_year.csv").write_text("\r\n".join(rows), encoding="utf-8")
    wide = ["﻿Monthly,2030"] + [f"{m.title()},{100 + i}" for i, m in enumerate(mons)]
    wide.append(f"Yearly Export,{sum(100 + i for i in range(12))}")
    (raw / "mef" / "mef_synthetic_first_year.csv").write_bytes("\r\n".join(wide).encode("utf-8"))
    # Comtrade: 24 months; milled with 2 partners + world; paddy only in the last 3 months
    for k in range(24):
        y, m = 2030 + k // 12, k % 12 + 1
        recs = []
        for cmd, w, a, b in (("100630", 100_000, 60_000, 40_000), ("100620", 1_000, 1_000, 0), ("100640", 500, 500, 0)):
            recs += [_comtrade_row(y, m, cmd, 0, w, w * 0.5)]
            recs += [_comtrade_row(y, m, cmd, 1, a, a * 0.5)]
            if b:
                recs += [_comtrade_row(y, m, cmd, 2, b, b * 0.5)]
        total = 101_500
        if k >= 21:
            recs += [_comtrade_row(y, m, "100610", 0, 50_000, 10_000), _comtrade_row(y, m, "100610", 2, 50_000, 10_000)]
            total += 50_000
        recs += [_comtrade_row(y, m, "1006", 0, total, total * 0.5)]
        for part, kg in ((1, total - 40_000 - (50_000 if k >= 21 else 0)), (2, 40_000 + (50_000 if k >= 21 else 0))):
            recs += [_comtrade_row(y, m, "1006", part, kg, kg * 0.5)]
        (raw / "comtrade" / "exports" / f"{y}{m:02d}.json").write_text(
            json.dumps({"count": len(recs), "data": recs, "error": ""}), encoding="utf-8"
        )
    (raw / "comtrade" / "reference" / "partnerAreas.json").write_text(
        json.dumps(
            {
                "results": [
                    {"PartnerCode": 0, "PartnerDesc": "World", "PartnerCodeIsoAlpha3": "WLD", "isGroup": True},
                    {"PartnerCode": 1, "PartnerDesc": "Testland", "PartnerCodeIsoAlpha3": "TST", "isGroup": False},
                    {"PartnerCode": 2, "PartnerDesc": "Fakeria", "PartnerCodeIsoAlpha3": "FAK", "isGroup": False},
                ]
            }
        ),
        encoding="utf-8",
    )
    # Pink Sheet: header row 4, units row 5, data from row 6
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Monthly Prices"
    ws.append(["Synthetic Pink Sheet"])
    ws.append(["monthly prices"])
    ws.append([""])
    ws.append(["Updated on January 01, 2031"])
    ws.append([None, "Rice, Thai 5% ", "Rice, Thai 25% ", "Rice, Thai A.1", "Rice, Viet Namese 5%"])
    ws.append([None, "($/mt)", "($/mt)", "($/mt)", "($/mt)"])
    for k in range(24):
        y, m = 2030 + k // 12, k % 12 + 1
        ws.append([f"{y}M{m:02d}", 400.0 + k, "#VALUE!" if k == 3 else 380.0 + k, "..", 390.0 + k])
    wb.save(raw / "worldbank" / "CMO-Historical-Data-Monthly.xlsx")
    return raw


@pytest.fixture
def built_db(synthetic_raw, tmp_path):
    from rice_market.transformation.build import build

    db = tmp_path / "marts" / "t.duckdb"
    summary = build(raw=synthetic_raw, db_path=db)
    return db, summary


@pytest.fixture
def monthly_frame():
    p = pd.date_range("2030-01-01", periods=24, freq="MS")
    return pd.DataFrame({"period": p, "tonnes": range(100, 124)})
