"""Descriptive analytics on monthly series. Series are DataFrames with columns period (month start) and tonnes.

Rules enforced here: growth is computed only between months that are both reported and exactly 1 / 12 months apart
(a gap yields NaN, never a bridge across the gap); a year is 'complete' only when all 12 months are reported.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _regular(df: pd.DataFrame, value: str = "tonnes") -> pd.Series:
    """Series on a continuous monthly index; absent months become NaN (kept visible, not filled)."""
    s = df.set_index("period")[value].sort_index()
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="MS"))


def add_growth(df: pd.DataFrame, value: str = "tonnes") -> pd.DataFrame:
    s = _regular(df, value)
    out = pd.DataFrame(
        {
            value: s,
            "mom_pct": s.pct_change(1, fill_method=None) * 100,
            "yoy_pct": s.pct_change(12, fill_method=None) * 100,
            "rolling_3m": s.rolling(3, min_periods=3).mean(),
            "rolling_12m": s.rolling(12, min_periods=12).mean(),
        }
    )
    out.index.name = "period"
    return out.reset_index()


def annual_summary(df: pd.DataFrame, value: str = "tonnes") -> pd.DataFrame:
    d = df.dropna(subset=[value]).copy()
    d["year"] = d["period"].dt.year
    g = d.groupby("year").agg(
        total=(value, "sum"),
        months_reported=(value, "count"),
        first_month=("period", "min"),
        last_month=("period", "max"),
    )
    g["is_complete"] = g["months_reported"] == 12
    g["monthly_mean"] = g["total"] / g["months_reported"]
    return g.reset_index()


def like_for_like_yoy(df: pd.DataFrame, year: int, value: str = "tonnes") -> dict:
    """Compare `year` with the previous year over exactly the months reported in `year` (no partial-vs-full)."""
    d = df.dropna(subset=[value]).copy()
    d["year"], d["month"] = d["period"].dt.year, d["period"].dt.month
    cur = d[d["year"] == year]
    months = set(cur["month"])
    prev = d[(d["year"] == year - 1) & d["month"].isin(months)]
    if len(months) == 0 or len(prev) != len(months):
        return {"year": year, "months": sorted(months), "comparable": False, "change_pct": float("nan")}
    a, b = cur[value].sum(), prev[value].sum()
    return {
        "year": year,
        "months": sorted(months),
        "comparable": True,
        "current": a,
        "previous": b,
        "change_pct": (a / b - 1) * 100 if b else float("nan"),
    }


def seasonal_profile(df: pd.DataFrame, value: str = "tonnes") -> pd.DataFrame:
    """Mean of each calendar month relative to the mean of complete years only (index 1.0 = average month)."""
    ann = annual_summary(df, value)
    full = set(ann.loc[ann["is_complete"], "year"])
    d = df.dropna(subset=[value]).copy()
    d = d[d["period"].dt.year.isin(full)]
    if d.empty:
        return pd.DataFrame(columns=["month", "mean", "index", "n_years"])
    d["month"] = d["period"].dt.month
    g = d.groupby("month")[value].agg(mean="mean", n_years="count").reset_index()
    g["index"] = g["mean"] / d[value].mean()
    return g


def volatility(df: pd.DataFrame, value: str = "tonnes") -> dict:
    s = _regular(df, value)
    lr = np.log(s).diff().dropna()
    lr = lr[np.isfinite(lr)]
    return {
        "cv": float(s.std(ddof=1) / s.mean()) if s.count() > 1 else float("nan"),
        "log_change_sd": float(lr.std(ddof=1)) if len(lr) > 1 else float("nan"),
        "n_changes": int(len(lr)),
    }


def shares(df: pd.DataFrame, group: str, value: str) -> pd.DataFrame:
    tot = df[value].sum()
    out = df.groupby(group, as_index=False)[value].sum()
    out["share"] = out[value] / tot if tot else float("nan")
    return out.sort_values("share", ascending=False).reset_index(drop=True)


def hhi(shares_: pd.Series | np.ndarray) -> float:
    """Herfindahl-Hirschman index on shares that sum to 1 (returned on the 0-10,000 scale)."""
    s = np.asarray(shares_, dtype=float)
    if len(s) == 0 or not np.isclose(s.sum(), 1.0, atol=1e-6):
        raise ValueError(f"shares must sum to 1, got {s.sum() if len(s) else 'empty'}")
    return float((s**2).sum() * 10_000)


def align_monthly(a: pd.Series, b: pd.Series) -> pd.DataFrame:
    """Inner-join two monthly series on their period index; only months present and non-null in both remain."""
    return pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()


def lagged_correlations(x: pd.Series, y: pd.Series, lags=range(0, 4), min_pairs: int = 12) -> pd.DataFrame:
    """Pearson/Spearman between y(t) and x(t-lag). Exploratory only: no causal reading is implied."""
    rows = []
    for lag in lags:
        j = align_monthly(x.shift(lag, freq="MS"), y)
        if len(j) < min_pairs:
            rows.append({"lag_months": lag, "n": len(j), "pearson": np.nan, "spearman": np.nan})
            continue
        rows.append(
            {
                "lag_months": lag,
                "n": len(j),
                "pearson": float(j["a"].corr(j["b"])),
                "spearman": float(j["a"].corr(j["b"], method="spearman")),
            }
        )
    return pd.DataFrame(rows)


def unit_value(value_usd: pd.Series, quantity_t: pd.Series) -> pd.Series:
    """Export unit value (FOB USD per tonne) from the SAME trade record. Not a market or transaction price."""
    return (value_usd / quantity_t.where(quantity_t > 0)).rename("unit_value_usd_per_t")
