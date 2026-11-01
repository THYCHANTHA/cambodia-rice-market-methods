"""Build the DuckDB warehouse from data/raw. Idempotent: the database file is recreated on every run.

Nothing is filled or interpolated. Every disagreement between sources becomes a row in dq_reconciliation, every
rule violation a row in dq_issue.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from rice_market import config
from rice_market.transformation import comtrade as ct
from rice_market.transformation import mef, pink_sheet
from rice_market.validation import checks as C

SQL_DIR = Path(__file__).resolve().parents[3] / "sql"
SOWS_SERIES = "sows_mef"
NON_PADDY = ["100620", "100630", "100640"]


# ------------------------------------------------------------------ helpers
def canonical_sows(monthly: pd.DataFrame) -> tuple[pd.DataFrame, list[dict], pd.DataFrame]:
    """One value per month from all imported MEF files, without overwriting anything.

    Rule: a month is 'reported' if any file reports it. If files disagree (beyond 0.5 t) the narrower file (the one
    covering fewer months, e.g. a single-year file over a multi-year file) wins, and every disagreement is documented
    in the issue list. Returns (canonical, issues, overlap table).
    """
    issues: list[dict] = []
    overlap = C.overlap_conflicts(monthly.assign(period=monthly["period"].astype(str)), "period", "tonnes", "dataset")
    bad = overlap[~overlap["agree"]] if not overlap.empty else overlap
    for r in bad.itertuples():
        issues.append(
            C.issue(
                "overlap_conflict",
                "warning",
                "mef",
                f"{r.period}: {r.min} vs {r.max} ({r.sources})",
                "document_discrepancy",
            )
        )
    ranked = monthly.assign(rank=-monthly.groupby("dataset")["period"].transform("size"))  # fewer months = higher rank
    rep = ranked[ranked["status"] == "reported"].sort_values(["period", "rank"]).drop_duplicates("period", keep="last")
    allp = ranked.groupby("period", as_index=False).size()[["period"]]
    out = allp.merge(rep[["period", "tonnes"]], on="period", how="left")
    out["status"] = np.where(out["tonnes"].isna(), "missing", "reported")
    return out, issues, overlap


def annual_from_monthly(series_id: str, df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["status"] == "reported"].copy()
    d["year"] = d["period"].dt.year
    g = d.groupby("year").agg(tonnes=("tonnes", "sum"), months_reported=("tonnes", "count")).reset_index()
    g["is_complete"] = g["months_reported"] == 12
    g.insert(0, "series_id", series_id)
    return g


def comtrade_world(df: pd.DataFrame, cov: pd.DataFrame) -> pd.DataFrame:
    """World-level monthly rows per HS code with explicit 'missing' rows for gaps inside the reported span."""
    w = df[df["partner_code"] == 0]
    reported_months = cov.loc[cov["records"] > 0, "period"]
    if reported_months.empty:
        return pd.DataFrame(columns=["series_id", "period", "tonnes", "fob_usd", "status"])
    span = pd.date_range(reported_months.min(), reported_months.max(), freq="MS")
    rows = []
    for code in config.HS_RICE:
        g = w[w["cmd_code"] == code].set_index("period")
        for p in span:
            if p in g.index:
                r = g.loc[p]
                kg = r["net_wgt_kg"]
                rows.append(
                    {
                        "series_id": f"comtrade_{code}",
                        "period": p,
                        "tonnes": None if pd.isna(kg) else kg / 1000.0,
                        "fob_usd": r["fob_usd"] if pd.notna(r["fob_usd"]) else r["primary_value_usd"],
                        "status": "missing" if pd.isna(kg) else "reported",
                    }
                )
            else:
                rows.append(
                    {"series_id": f"comtrade_{code}", "period": p, "tonnes": None, "fob_usd": None, "status": "missing"}
                )
    return pd.DataFrame(rows)


def dim_series_rows() -> list[tuple]:
    rows = [
        (
            SOWS_SERIES,
            "MEF Open Data Portal (SOWS)",
            "Cambodia monthly rice exports (SOWS via MEF)",
            "As published. The publisher's product definition may not be stated; verify it before interpreting.",
            "metric tons",
            "export",
        )
    ]
    for code, text in config.HS_RICE.items():
        rows.append(
            (
                f"comtrade_{code}",
                "UN Comtrade (preview API)",
                f"Cambodia-reported exports, HS {code}",
                text,
                "metric tons (net weight)",
                "export",
            )
        )
    return rows


def _snapshots(manifest: Path) -> pd.DataFrame:
    """Latest manifest line per local path, so the dashboard can show when each file was retrieved."""
    cols = ["source", "path", "url", "retrieved_utc", "sha256", "bytes"]
    if not manifest.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_json(manifest, lines=True, dtype=False)
    if df.empty:
        return pd.DataFrame(columns=cols)
    return df.sort_values("retrieved_utc").drop_duplicates("path", keep="last")[cols]


# ------------------------------------------------------------------ main build
def build(raw: Path = config.RAW, db_path: Path = config.DB_PATH, manifest: Path | None = None) -> dict:
    """Build the warehouse from whatever source files exist under `raw`; any source may be absent.

    `manifest` (a downloads.jsonl) is only read when given, so a demonstration database never shows another dataset's
    download records.
    """
    issues: list[dict] = []
    recon: list[dict] = []
    summary: dict = {}

    # ---- MEF / SOWS
    monthly, annual = mef.load_all(raw / "mef")
    if monthly.empty:
        issues.append(
            C.issue(
                "source_absent",
                "info",
                "mef",
                "no MEF files imported (see scripts/import_mef.py)",
                "document_discrepancy",
            )
        )
    sows = pd.DataFrame(columns=["period", "tonnes", "status"])
    if not monthly.empty:
        issues += C.find_duplicates(monthly, ["dataset", "period"], "mef")
        issues += C.invalid_dates(monthly["period"], "mef")
        issues += C.negative_values(monthly, "tonnes", "mef")
        for ds, g in monthly.groupby("dataset"):
            issues += C.blank_values(g, "tonnes", ds)
        sows, ov_issues, overlap = canonical_sows(monthly)
        issues += ov_issues
        for r in overlap.itertuples():
            recon.append(
                {
                    "kind": "mef_file_overlap",
                    "key": r.period,
                    "a_label": "min across files",
                    "a_value": r.min,
                    "b_label": "max across files",
                    "b_value": r.max,
                    "diff": r.max - r.min,
                    "rel_diff": (r.max - r.min) / r.max if r.max else np.nan,
                    "agrees": bool(r.agree),
                }
            )
        ann_rec = C.annual_reconciliation(monthly, annual)
        for r in ann_rec.itertuples():
            recon.append(
                {
                    "kind": "mef_annual_total",
                    "key": f"{r.dataset}:{r.year}",
                    "a_label": "reported yearly total",
                    "a_value": r.reported_total_t,
                    "b_label": "sum of reported months",
                    "b_value": r.monthly_sum_t,
                    "diff": r.diff_t,
                    "rel_diff": r.diff_t / r.reported_total_t if r.reported_total_t else np.nan,
                    "agrees": bool(r.matches),
                }
            )
            if not r.matches:
                issues.append(
                    C.issue(
                        "annual_total_mismatch",
                        "warning",
                        r.dataset,
                        f"{r.year}: reported {r.reported_total_t} vs monthly sum {r.monthly_sum_t}",
                        "document_discrepancy",
                    )
                )
        # the multi-year file against its year-specific sibling is covered by overlap; also flag unreported tail
        last_reported = sows.loc[sows["status"] == "reported", "period"].max()
        tail = sows[(sows["period"] > last_reported)]
        if len(tail):
            issues.append(
                C.issue(
                    "unreported_tail",
                    "warning",
                    "mef",
                    f"{len(tail)} month(s) after {last_reported:%Y-%m} are blank in the source "
                    f"(through {tail['period'].max():%Y-%m}); kept as missing, not zero",
                    "mark_missing",
                )
            )
        _, gap_issues = C.missing_months(sows.loc[sows["status"] == "reported", "period"], "mef_canonical")
        issues += gap_issues
        summary["sows_first"] = str(sows.loc[sows["status"] == "reported", "period"].min().date())
        summary["sows_last"] = str(last_reported.date())
        summary["sows_months"] = int((sows["status"] == "reported").sum())

    # ---- Comtrade exports
    exp, exp_cov = ct.load_view(raw / "comtrade", "exports")
    partners = ct.load_partner_names(raw / "comtrade" / "reference")
    fct_world = comtrade_world(exp, exp_cov)
    if not exp.empty:
        issues += C.find_duplicates(exp, ["period", "cmd_code", "reporter_code", "partner_code"], "comtrade_exports")
        issues += C.negative_values(exp, "net_wgt_kg", "comtrade_exports")
        _, gi = C.missing_months(exp_cov.loc[exp_cov["records"] > 0, "period"], "comtrade_exports")
        issues += gi
        est = int(exp["is_net_wgt_estimated"].sum())
        if est:
            issues.append(
                C.issue(
                    "estimated_weight",
                    "warning",
                    "comtrade_exports",
                    f"{est} row(s) have an estimated net weight",
                    "retain_with_warning",
                )
            )
        classes = sorted(exp["classification_code"].dropna().unique())
        if len(classes) > 1:
            issues.append(
                C.issue(
                    "classification_change",
                    "warning",
                    "comtrade_exports",
                    f"HS revisions present in rows: {classes}",
                    "document_discrepancy",
                )
            )
        ps = C.partner_sum_vs_total(exp)
        for r in ps[~ps["ok"]].itertuples():
            issues.append(
                C.issue(
                    "partner_sum_vs_world",
                    "warning",
                    "comtrade_exports",
                    f"{r.period:%Y-%m} {r.cmd_code}: partners {r.partners:.0f} vs world {r.world:.0f} kg",
                    "document_discrepancy",
                )
            )
        kids = C.children_vs_heading(exp, config.HS_CHILDREN)
        for r in kids[~kids["ok"]].itertuples():
            recon.append(
                {
                    "kind": "hs_children_vs_heading",
                    "key": f"{r.period:%Y-%m}",
                    "a_label": "HS 1006 kg",
                    "a_value": r.heading_kg,
                    "b_label": "sum of 4 children kg",
                    "b_value": r.children_sum,
                    "diff": r.children_sum - r.heading_kg,
                    "rel_diff": r.rel_diff,
                    "agrees": False,
                }
            )
        # SOWS (MEF) against alternative Comtrade definitions, same months only
        sw = sows[sows["status"] == "reported"].set_index("period")["tonnes"]
        piv = fct_world[fct_world["status"] == "reported"].pivot(index="period", columns="series_id", values="tonnes")
        for label, cols in {
            "HS 1006 total": ["comtrade_1006"],
            "HS 100630 milled": ["comtrade_100630"],
            "HS 100620+100630+100640 (non-paddy)": [f"comtrade_{c}" for c in NON_PADDY],
        }.items():
            if not all(c in piv for c in cols):
                continue
            ct_val = piv[cols].sum(axis=1, min_count=1)
            for p in sw.index.intersection(ct_val.dropna().index):
                a, b = sw[p], ct_val[p]
                recon.append(
                    {
                        "kind": f"sows_vs_comtrade[{label}]",
                        "key": f"{p:%Y-%m}",
                        "a_label": "SOWS (MEF) t",
                        "a_value": a,
                        "b_label": f"Comtrade {label} t",
                        "b_value": b,
                        "diff": b - a,
                        "rel_diff": (b - a) / a if a else np.nan,
                        "agrees": bool(abs(b - a) <= 0.05 * a),
                    }
                )
    summary["comtrade_export_months"] = int((exp_cov["records"] > 0).sum()) if len(exp_cov) else 0

    # ---- Partner and mirror
    fct_partner = pd.DataFrame()
    if not exp.empty:
        pe = exp[exp["partner_code"] != 0].merge(partners, on="partner_code", how="left")
        miss = int(pe["partner_name"].isna().sum())
        if miss:
            issues.append(
                C.issue(
                    "unknown_partner_code",
                    "warning",
                    "comtrade_exports",
                    f"{miss} row(s) with a partner code absent from the official list",
                    "retain_with_warning",
                )
            )
        fct_partner = pe.assign(
            net_wgt_t=pe["net_wgt_kg"] / 1000.0, fob_usd=pe["fob_usd"].fillna(pe["primary_value_usd"])
        )[["period", "cmd_code", "partner_code", "partner_name", "iso3", "is_group", "net_wgt_t", "fob_usd"]]
    mir, mir_cov = ct.load_view(raw / "comtrade", "mirror")
    fct_mirror = pd.DataFrame()
    if not mir.empty:
        rn = partners.rename(columns={"partner_code": "reporter_code", "partner_name": "reporter_name"})
        m = mir[mir["reporter_code"] != 0].merge(rn[["reporter_code", "reporter_name"]], on="reporter_code", how="left")
        issues += C.find_duplicates(m, ["period", "cmd_code", "reporter_code"], "comtrade_mirror")
        fct_mirror = m.assign(net_wgt_t=m["net_wgt_kg"] / 1000.0, cif_usd=m["cif_usd"].fillna(m["primary_value_usd"]))[
            ["period", "cmd_code", "reporter_code", "reporter_name", "net_wgt_t", "cif_usd"]
        ]
    summary["mirror_months"] = int((mir_cov["records"] > 0).sum()) if len(mir_cov) else 0

    # ---- Prices
    workbook = raw / "worldbank" / "CMO-Historical-Data-Monthly.xlsx"
    if workbook.exists():
        prices, pmeta = pink_sheet.load_rice_prices(workbook)
    else:
        prices = pd.DataFrame(
            {
                "period": pd.Series(dtype="datetime64[ns]"),
                "series": pd.Series(dtype="object"),
                "usd_per_tonne": pd.Series(dtype="float64"),
            }
        )
        pmeta = {"updated_note": "", "error_cells": []}
    for e in pmeta["error_cells"]:
        issues.append(
            C.issue(
                "source_error_cell",
                "warning",
                "pink_sheet",
                f"{e['series']} {e['period']}: cell holds {e['value']}; stored as NULL",
                "mark_missing",
            )
        )
    summary["price_note"] = pmeta["updated_note"]

    # ---- write
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    con.execute((SQL_DIR / "schema.sql").read_text(encoding="utf-8"))
    con.executemany("INSERT INTO dim_series VALUES (?,?,?,?,?,?)", dim_series_rows())
    if len(monthly):
        con.register(
            "m_df", monthly.assign(period=monthly["period"].dt.date)[["dataset", "period", "tonnes", "status"]]
        )
        con.execute("INSERT INTO raw_mef_monthly SELECT * FROM m_df")
    if not annual.empty:
        con.register("a_df", annual)
        con.execute("INSERT INTO raw_mef_annual SELECT dataset, year, reported_total_t FROM a_df")
    fm_sows = sows.assign(series_id=SOWS_SERIES, fob_usd=np.nan)[["series_id", "period", "tonnes", "fob_usd", "status"]]
    fm = pd.concat([fm_sows, fct_world], ignore_index=True)
    if len(fm):
        fm["period"] = pd.to_datetime(fm["period"]).dt.date
        con.register("fm_df", fm)
        con.execute("INSERT INTO fct_export_monthly SELECT series_id, period, tonnes, fob_usd, status FROM fm_df")
        fa = pd.concat(
            [annual_from_monthly(s, g.assign(period=pd.to_datetime(g["period"]))) for s, g in fm.groupby("series_id")],
            ignore_index=True,
        )
        con.register("fa_df", fa)
        con.execute(
            "INSERT INTO fct_export_annual SELECT series_id, year, tonnes, months_reported, is_complete FROM fa_df"
        )
    if len(fct_partner):
        fp = fct_partner.assign(period=fct_partner["period"].dt.date)
        con.register("fp_df", fp)
        con.execute(
            "INSERT INTO fct_partner_monthly SELECT period, cmd_code, partner_code, partner_name, iso3, "
            "is_group, net_wgt_t, fob_usd FROM fp_df"
        )
    if len(fct_mirror):
        fmir = fct_mirror.assign(period=fct_mirror["period"].dt.date)
        con.register("fmir_df", fmir)
        con.execute(
            "INSERT INTO fct_mirror_monthly SELECT period, cmd_code, reporter_code, reporter_name, net_wgt_t, "
            "cif_usd FROM fmir_df"
        )
    if len(prices):
        pr = prices.assign(period=prices["period"].dt.date)
        con.register("pr_df", pr)
        con.execute("INSERT INTO fct_price_monthly SELECT period, series, usd_per_tonne FROM pr_df")
    snap = _snapshots(manifest) if manifest else pd.DataFrame()
    if len(snap):
        con.register("snap_df", snap)
        con.execute("INSERT INTO src_snapshot SELECT source, path, url, retrieved_utc, sha256, bytes FROM snap_df")
    if issues:
        con.register("iss_df", pd.DataFrame(issues))
        con.execute('INSERT INTO dq_issue SELECT "check", severity, dataset, detail, decision FROM iss_df')
    if recon:
        con.register("rec_df", pd.DataFrame(recon))
        con.execute(
            "INSERT INTO dq_reconciliation SELECT kind, key, a_label, a_value, b_label, b_value, diff, "
            "rel_diff, agrees FROM rec_df"
        )
    con.close()
    summary.setdefault("sows_months", 0)
    summary["issues"] = len(issues)
    summary["reconciliations"] = len(recon)
    return summary
