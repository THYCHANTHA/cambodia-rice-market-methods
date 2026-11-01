"""Forecast experiment runner: reads a warehouse, evaluates models by rolling origin, writes forecast_* tables.

Nothing here knows about any particular dataset. The evaluated span of a series is either configured by the user or
detected as the longest gap-free run of reported months; the role (primary / exploratory) follows from the number of
complete annual cycles, not from the results.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

from rice_market import config
from rice_market.forecasting import evaluation as F

DEFAULTS = {"min_train": 24, "horizons": [1, 3, 6], "min_months": 36, "series": []}
GUIDELINE_CYCLES = 4  # a seasonal comparison is "primary" only with at least four complete annual cycles
BOOT_N = 2000
SEED = 20260501


def load_config(path: Path | None = None) -> dict:
    """Read the YAML settings (missing file = defaults)."""
    path = Path(path or config.EXPERIMENT_CONFIG)
    cfg = dict(DEFAULTS)
    if path.exists():
        cfg |= yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg["horizons"] = [int(h) for h in cfg["horizons"]]
    return cfg


def longest_gap_free_span(series: pd.Series) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Longest run of consecutive calendar months that are all reported (non-null). None if there is no value."""
    s = series.dropna()
    if s.empty:
        return None
    full = pd.date_range(s.index.min(), s.index.max(), freq="MS")
    ok = pd.Series(full.isin(s.index), index=full)
    best = (0, None, None)
    run_start, run_len = None, 0
    for ts, flag in ok.items():
        if flag:
            run_start = run_start if run_len else ts
            run_len += 1
            if run_len > best[0]:
                best = (run_len, run_start, ts)
        else:
            run_len = 0
    return (best[1], best[2]) if best[0] else None


def load_series(con: duckdb.DuckDBPyConnection, series_id: str) -> pd.Series:
    df = con.execute(
        "SELECT period, tonnes FROM fct_export_monthly WHERE series_id = ? AND status = 'reported' ORDER BY period",
        [series_id],
    ).df()
    df["period"] = pd.to_datetime(df["period"])
    return df.set_index("period")["tonnes"]


def resolve_span(series: pd.Series, spec: dict) -> tuple[pd.Timestamp, pd.Timestamp, str] | None:
    if spec.get("start") or spec.get("end"):
        start = pd.Timestamp(spec.get("start") or series.index.min())
        end = pd.Timestamp(spec.get("end") or series.index.max())
        return start, end, "configured"
    span = longest_gap_free_span(series)
    return (span[0], span[1], "detected") if span else None


def paired_origin_bootstrap(fc: pd.DataFrame, model: str, base: str, step: int, n: int = BOOT_N, seed: int = SEED):
    """Mean absolute-error difference (model - base) at one step, with an origin-resampling 95% interval.

    Origins are resampled independently, which ignores serial dependence; the interval is therefore optimistic.
    """
    a = fc[(fc["model"] == model) & (fc["step"] == step)].set_index("origin")
    b = fc[(fc["model"] == base) & (fc["step"] == step)].set_index("origin")
    idx = a.index.intersection(b.index)
    d = (a.loc[idx, "actual"] - a.loc[idx, "forecast"]).abs() - (b.loc[idx, "actual"] - b.loc[idx, "forecast"]).abs()
    d = d.to_numpy()
    if len(d) < 5:
        return {"n": len(d), "mean_diff": float("nan"), "lo": float("nan"), "hi": float("nan")}
    rng = np.random.default_rng(seed)
    boots = rng.choice(d, size=(n, len(d)), replace=True).mean(axis=1)
    return {
        "n": len(d),
        "mean_diff": float(d.mean()),
        "lo": float(np.percentile(boots, 2.5)),
        "hi": float(np.percentile(boots, 97.5)),
    }


def run(db_path: Path = config.DB_PATH, out_dir: Path | None = None, cfg: dict | None = None) -> dict:
    """Evaluate the configured (or all long-enough) series. Writes forecast_* tables; optionally a JSON record."""
    cfg = cfg or load_config()
    horizons = tuple(cfg["horizons"])
    con = duckdb.connect(str(db_path))
    for t in ("forecast_backtest", "forecast_summary", "forecast_series"):
        con.execute(f"DELETE FROM {t}")
    wanted = cfg["series"] or [
        {"series_id": r[0]}
        for r in con.execute(
            "SELECT series_id FROM fct_export_monthly WHERE status = 'reported' "
            "GROUP BY 1 HAVING count(*) >= ? ORDER BY 1",
            [int(cfg["min_months"])],
        ).fetchall()
    ]
    record = {
        "run_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "horizons": list(horizons),
        "min_train": cfg["min_train"],
        "seed": SEED,
        "series": {},
    }
    for spec in wanted:
        sid = spec["series_id"]
        raw = load_series(con, sid)
        span = resolve_span(raw, spec) if len(raw) else None
        if span is None:
            record["series"][sid] = {"status": "skipped: no reported values"}
            continue
        start, end, source = span
        y = raw.reindex(pd.date_range(start, end, freq="MS"))
        cycles = len(y) / 12
        info = {
            "start": str(start.date()),
            "end": str(end.date()),
            "span_source": source,
            "n_months": int(len(y)),
            "n_missing": int(y.isna().sum()),
            "annual_cycles": cycles,
            "role": "primary" if cycles >= GUIDELINE_CYCLES else "exploratory",
        }
        if y.isna().any() or len(y) < cfg["min_train"] + max(horizons):
            info["status"] = "skipped: gaps in span or too short (no interpolation)"
            record["series"][sid] = info
            continue
        fc, skipped = F.rolling_origin(y, horizon=max(horizons), min_train=cfg["min_train"])
        summ = F.summarise(fc, horizons)
        info.update(
            {
                "status": "ok",
                "n_origins": int(fc["origin"].nunique()),
                "first_origin": str(fc["origin"].min().date()),
                "last_origin": str(fc["origin"].max().date()),
                "skipped": skipped.groupby("model").size().to_dict() if len(skipped) else {},
                "summary": json.loads(summ.to_json(orient="records")),
                "bootstrap_vs_seasonal_naive": {
                    f"{m}@h{h}": paired_origin_bootstrap(fc, m, "seasonal_naive", h)
                    for h in horizons
                    for m in fc["model"].unique()
                    if m != "seasonal_naive"
                },
            }
        )
        con.execute(
            "INSERT INTO forecast_series VALUES (?,?,?,?,?,?,?)",
            [sid, start.date(), end.date(), info["n_months"], cycles, info["role"], source],
        )
        bt = fc.assign(series_id=sid)[
            ["series_id", "model", "origin", "train_size", "step", "target_period", "actual", "forecast"]
        ]
        for col in ("origin", "target_period"):
            bt[col] = bt[col].dt.date
        con.register("bt_df", bt)
        con.execute("INSERT INTO forecast_backtest SELECT * FROM bt_df")
        sm = summ.assign(series_id=sid)
        con.register("sm_df", sm)
        con.execute(
            "INSERT INTO forecast_summary SELECT series_id, horizon, model, n, mae, rmse, smape, "
            "mae_vs_naive, mae_vs_seasonal_naive FROM sm_df"
        )
        record["series"][sid] = info
    con.close()
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "forecast_experiment.json").write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
    return record
