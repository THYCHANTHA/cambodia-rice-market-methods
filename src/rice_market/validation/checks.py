"""Pure data-quality checks. Each returns a list of issue dicts; nothing here modifies or fills data.

Issue fields: check, severity (error|warning|info), dataset, detail, decision. 'decision' states what the pipeline does:
reject | retain_with_warning | mark_missing | document_discrepancy.
"""

from __future__ import annotations

import pandas as pd


def issue(check: str, severity: str, dataset: str, detail: str, decision: str) -> dict:
    return {"check": check, "severity": severity, "dataset": dataset, "detail": detail, "decision": decision}


def find_duplicates(df: pd.DataFrame, keys: list[str], dataset: str) -> list[dict]:
    dup = df[df.duplicated(keys, keep=False)]
    if dup.empty:
        return []
    n = int(df.duplicated(keys).sum())
    return [issue("duplicate_keys", "error", dataset, f"{n} repeated key(s) on {keys}", "reject")]


def missing_months(periods: pd.Series, dataset: str, start=None, end=None) -> tuple[list[pd.Timestamp], list[dict]]:
    """Calendar months absent between first and last observed period (or the given bounds)."""
    p = pd.DatetimeIndex(pd.to_datetime(periods)).unique().sort_values()
    if len(p) == 0:
        return [], [issue("missing_months", "error", dataset, "no periods", "document_discrepancy")]
    lo, hi = pd.Timestamp(start) if start else p[0], pd.Timestamp(end) if end else p[-1]
    full = pd.date_range(lo, hi, freq="MS")
    gone = [d for d in full if d not in set(p)]
    if not gone:
        return [], []
    label = ", ".join(d.strftime("%Y-%m") for d in gone[:12]) + (" ..." if len(gone) > 12 else "")
    return gone, [issue("missing_months", "warning", dataset, f"{len(gone)} month(s) absent: {label}", "mark_missing")]


def invalid_dates(periods: pd.Series, dataset: str) -> list[dict]:
    bad = pd.to_datetime(periods, errors="coerce").isna().sum()
    return [issue("invalid_dates", "error", dataset, f"{int(bad)} unparseable period(s)", "reject")] if bad else []


def negative_values(df: pd.DataFrame, col: str, dataset: str) -> list[dict]:
    n = int((df[col] < 0).sum())
    return [issue("negative_quantity", "error", dataset, f"{n} negative value(s) in {col}", "reject")] if n else []


def blank_values(df: pd.DataFrame, col: str, dataset: str) -> list[dict]:
    n = int(df[col].isna().sum())
    return (
        [issue("blank_values", "info", dataset, f"{n} blank/missing value(s) in {col}; not imputed", "mark_missing")]
        if n
        else []
    )


def annual_reconciliation(
    monthly: pd.DataFrame, annual: pd.DataFrame, dataset_col: str = "dataset", tol_t: float = 0.5
) -> pd.DataFrame:
    """Compare a file's own 'Yearly Export' total with the sum of its monthly values.

    monthly needs dataset, year, tonnes; annual needs dataset, year, reported_total_t.
    """
    if annual.empty:
        return pd.DataFrame(
            columns=["dataset", "year", "reported_total_t", "monthly_sum_t", "months_reported", "diff_t", "matches"]
        )
    g = monthly.groupby([dataset_col, "year"]).agg(monthly_sum_t=("tonnes", "sum"), months_reported=("tonnes", "count"))
    out = annual.merge(g.reset_index(), on=[dataset_col, "year"], how="left")
    out["diff_t"] = out["monthly_sum_t"] - out["reported_total_t"]
    out["matches"] = out["diff_t"].abs() <= tol_t
    return out


def overlap_conflicts(df: pd.DataFrame, key: str, value: str, source: str, tol: float = 0.5) -> pd.DataFrame:
    """Periods reported by more than one source: list each pair and whether the values agree."""
    rows = []
    rep = df.dropna(subset=[value])
    for k, grp in rep.groupby(key):
        if grp[source].nunique() < 2:
            continue
        vals = grp.set_index(source)[value]
        rows.append(
            {
                key: k,
                "sources": ", ".join(vals.index),
                "min": vals.min(),
                "max": vals.max(),
                "agree": bool(vals.max() - vals.min() <= tol),
            }
        )
    return pd.DataFrame(rows, columns=[key, "sources", "min", "max", "agree"])


def partner_sum_vs_total(df: pd.DataFrame, qty: str = "net_wgt_kg", tol_rel: float = 0.001) -> pd.DataFrame:
    """For each (period, cmd_code): world row against the sum of individual partner rows.

    A partner-level table that does not add up to the reported total cannot support share analysis.
    """
    keys = ["period", "cmd_code"]
    world = df[df["partner_code"] == 0].groupby(keys)[qty].sum().rename("world")
    parts = df[df["partner_code"] != 0].groupby(keys)[qty].sum().rename("partners")
    out = pd.concat([world, parts], axis=1).fillna(0.0).reset_index()
    out["rel_diff"] = (out["partners"] - out["world"]).abs() / out["world"].where(out["world"] > 0)
    out["ok"] = out["rel_diff"].fillna(0.0) <= tol_rel
    return out


def children_vs_heading(
    df: pd.DataFrame, children: list[str], qty: str = "net_wgt_kg", tol_rel: float = 0.001
) -> pd.DataFrame:
    """World-level HS 1006 against the sum of its four 6-digit children."""
    w = df[df["partner_code"] == 0]
    piv = w.pivot_table(index="period", columns="cmd_code", values=qty, aggfunc="sum")
    for c in ["1006", *children]:
        if c not in piv:
            piv[c] = float("nan")
    piv["children_sum"] = piv[children].sum(axis=1, min_count=1)
    piv["rel_diff"] = (piv["children_sum"] - piv["1006"]).abs() / piv["1006"].where(piv["1006"] > 0)
    piv["ok"] = piv["rel_diff"].fillna(0.0) <= tol_rel
    return piv.reset_index().rename(columns={"1006": "heading_kg"})[
        ["period", "heading_kg", "children_sum", "rel_diff", "ok"]
    ]
