"""Read-only data access for the dashboard and scripts. No page talks to the network or writes anything."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pandas as pd

from rice_market import config

REQUIRED_TABLES = (
    "dim_series",
    "fct_export_monthly",
    "fct_export_annual",
    "fct_partner_monthly",
    "fct_price_monthly",
    "dq_issue",
    "dq_reconciliation",
    "forecast_summary",
    "forecast_backtest",
)


class WarehouseMissing(RuntimeError):
    """Raised when the warehouse has not been built; the message tells the user the command to run."""


def resolve_database() -> tuple[Path | None, str]:
    """Which warehouse the dashboard should read, as (path or None, mode) with mode 'real', 'demo' or 'none'.

    RICE_MARKET_MODE=demo forces the synthetic demonstration warehouse; =real forces the user's own. Otherwise the
    user's
    own warehouse is preferred, then the synthetic demo, then nothing (the app shows an empty state).
    """
    forced = os.environ.get("RICE_MARKET_MODE", "").lower()
    candidates = {"real": config.DB_PATH, "demo": config.DEMO_DB_PATH}
    if forced in candidates:
        path = candidates[forced]
        return (path, forced) if path.exists() else (None, "none")
    for mode in ("real", "demo"):
        if candidates[mode].exists():
            return candidates[mode], mode
    return None, "none"


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = Path(db_path or config.DB_PATH)
    if not path.exists():
        raise WarehouseMissing(
            f"Warehouse not found at {path.name}. Build a synthetic demo with `python scripts/make_demo.py`, or build "
            "your own with `python scripts/run_pipeline.py` (see README)."
        )
    return duckdb.connect(str(path), read_only=True)


def _df(con, sql: str, params: list | None = None) -> pd.DataFrame:
    df = con.execute(sql, params or []).df()
    for col in df.columns:
        if col in ("period", "origin", "target_period", "start_period", "end_period"):
            df[col] = pd.to_datetime(df[col])
    return df


def health(con) -> dict:
    """Equivalent of a health-check endpoint: every required table exists and is non-empty."""
    out = {}
    for t in REQUIRED_TABLES:
        try:
            out[t] = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        except duckdb.Error:
            out[t] = None
    out["ok"] = all(v for k, v in out.items() if k != "ok" and k != "forecast_backtest")
    return out


def series_catalog(con) -> pd.DataFrame:
    return _df(
        con,
        """SELECT d.series_id, d.label, d.source, d.product_definition, d.unit,
                  min(f.period) FILTER (WHERE f.status = 'reported') AS first_reported,
                  max(f.period) FILTER (WHERE f.status = 'reported') AS last_reported,
                  count(*) FILTER (WHERE f.status = 'reported') AS months_reported,
                  count(*) AS months_in_span
           FROM dim_series d JOIN fct_export_monthly f USING (series_id)
           GROUP BY ALL ORDER BY d.series_id""",
    )


def monthly(con, series_id: str, start: str | None = None) -> pd.DataFrame:
    sql = "SELECT period, tonnes, fob_usd, status FROM fct_export_monthly WHERE series_id = ?"
    params: list = [series_id]
    if start:
        sql += " AND period >= ?"
        params.append(start)
    return _df(con, sql + " ORDER BY period", params)


def annual(con, series_id: str) -> pd.DataFrame:
    return _df(
        con,
        "SELECT year, tonnes, months_reported, is_complete FROM fct_export_annual WHERE series_id = ? ORDER BY year",
        [series_id],
    )


def partners(con, cmd_code: str, start: str, end: str) -> pd.DataFrame:
    return _df(
        con,
        """SELECT period, partner_code, partner_name, iso3, is_group, net_wgt_t, fob_usd
           FROM fct_partner_monthly WHERE cmd_code = ? AND period BETWEEN ? AND ? ORDER BY period""",
        [cmd_code, start, end],
    )


def mirror(con, cmd_code: str) -> pd.DataFrame:
    try:
        return _df(
            con,
            "SELECT period, reporter_code, reporter_name, net_wgt_t, cif_usd "
            "FROM fct_mirror_monthly WHERE cmd_code = ?",
            [cmd_code],
        )
    except duckdb.Error:
        return pd.DataFrame(columns=["period", "reporter_code", "reporter_name", "net_wgt_t", "cif_usd"])


def world_by_code(con, start: str = "2015-01-01") -> pd.DataFrame:
    return _df(
        con,
        """SELECT series_id, period, tonnes, fob_usd, status FROM fct_export_monthly
           WHERE series_id LIKE 'comtrade_%' AND period >= ? ORDER BY period""",
        [start],
    )


def prices(con, series: list[str] | None = None) -> pd.DataFrame:
    df = _df(con, "SELECT period, series, usd_per_tonne FROM fct_price_monthly ORDER BY period")
    return df[df["series"].isin(series)] if series else df


def issues(con) -> pd.DataFrame:
    return _df(con, "SELECT check_name, severity, dataset, detail, decision FROM dq_issue ORDER BY severity, dataset")


def reconciliation(con, kind_like: str = "%") -> pd.DataFrame:
    return _df(con, "SELECT * FROM dq_reconciliation WHERE kind LIKE ? ORDER BY kind, key", [kind_like])


def forecast_summary(con, series_id: str) -> pd.DataFrame:
    return _df(con, "SELECT * FROM forecast_summary WHERE series_id = ? ORDER BY horizon, mae", [series_id])


def forecast_backtest(con, series_id: str, model: str, step: int) -> pd.DataFrame:
    return _df(
        con,
        """SELECT origin, target_period, actual, forecast FROM forecast_backtest
           WHERE series_id = ? AND model = ? AND step = ? ORDER BY target_period""",
        [series_id, model, step],
    )


def snapshots(con) -> pd.DataFrame:
    return _df(con, "SELECT source, path, url, retrieved_utc, sha256, bytes FROM src_snapshot ORDER BY source, path")


def forecast_series(con) -> pd.DataFrame:
    return _df(
        con,
        "SELECT series_id, start_period, end_period, n_months, annual_cycles, role, span_source "
        "FROM forecast_series ORDER BY series_id",
    )
