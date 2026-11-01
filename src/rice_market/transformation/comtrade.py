"""Flatten cached Comtrade JSON into one row per (view, month, HS code, reporter, partner)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

WORLD = 0

COLUMNS = [
    "view",
    "period",
    "cmd_code",
    "reporter_code",
    "partner_code",
    "net_wgt_kg",
    "qty",
    "qty_unit_code",
    "fob_usd",
    "cif_usd",
    "primary_value_usd",
    "is_net_wgt_estimated",
    "is_aggregate",
    "classification_code",
]


def load_partner_names(reference_dir: Path) -> pd.DataFrame:
    if not (reference_dir / "partnerAreas.json").exists():
        return pd.DataFrame(columns=["partner_code", "partner_name", "iso3", "is_group"])
    data = json.loads((reference_dir / "partnerAreas.json").read_text(encoding="utf-8"))["results"]
    df = pd.DataFrame(data)[["PartnerCode", "PartnerDesc", "PartnerCodeIsoAlpha3", "isGroup"]]
    return df.rename(
        columns={
            "PartnerCode": "partner_code",
            "PartnerDesc": "partner_name",
            "PartnerCodeIsoAlpha3": "iso3",
            "isGroup": "is_group",
        }
    )


def parse_payload(view: str, payload: dict) -> list[dict]:
    rows = []
    for d in payload.get("data") or []:
        rows.append(
            {
                "view": view,
                "period": pd.Timestamp(year=int(d["refYear"]), month=int(d["refMonth"]), day=1),
                "cmd_code": str(d["cmdCode"]),
                "reporter_code": int(d["reporterCode"]),
                "partner_code": int(d["partnerCode"]),
                "net_wgt_kg": d.get("netWgt"),
                "qty": d.get("qty"),
                "qty_unit_code": d.get("qtyUnitCode"),
                "fob_usd": d.get("fobvalue"),
                "cif_usd": d.get("cifvalue"),
                "primary_value_usd": d.get("primaryValue"),
                "is_net_wgt_estimated": bool(d.get("isNetWgtEstimated")),
                "is_aggregate": bool(d.get("isAggregate")),
                "classification_code": d.get("classificationCode"),
            }
        )
    return rows


def load_view(raw_dir: Path, view: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (trade rows, month coverage). Coverage lists every cached month with its record count."""
    rows, cov = [], []
    for path in sorted((raw_dir / view).glob("??????.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        parsed = parse_payload(view, payload)
        rows.extend(parsed)
        cov.append(
            {
                "view": view,
                "period": pd.Timestamp(year=int(path.stem[:4]), month=int(path.stem[4:]), day=1),
                "records": len(parsed),
            }
        )
    df = pd.DataFrame(rows, columns=COLUMNS)
    return df, pd.DataFrame(cov, columns=["view", "period", "records"])
