"""Data-quality checks, reconciliation and analytics tests on synthetic series."""

import numpy as np
import pandas as pd
import pytest

from rice_market.analytics import metrics as M
from rice_market.validation import checks as C


def monthly(values, start="2030-01-01"):
    p = pd.date_range(start, periods=len(values), freq="MS")
    return pd.DataFrame({"period": p, "tonnes": values})


# ------------------------------------------------------------ checks
def test_duplicates_detected():
    df = pd.DataFrame({"period": ["a", "a", "b"], "x": [1, 2, 3]})
    assert C.find_duplicates(df, ["period"], "d")[0]["check"] == "duplicate_keys"
    assert C.find_duplicates(df.drop_duplicates("period"), ["period"], "d") == []


def test_missing_months_found_and_not_filled():
    p = pd.Series(pd.to_datetime(["2030-01-01", "2030-02-01", "2030-05-01"]))
    gone, issues = C.missing_months(p, "d")
    assert [g.strftime("%Y-%m") for g in gone] == ["2030-03", "2030-04"]
    assert issues[0]["decision"] == "mark_missing"


def test_negative_and_invalid_dates():
    df = pd.DataFrame({"tonnes": [1.0, -2.0]})
    assert C.negative_values(df, "tonnes", "d")
    assert C.negative_values(df.abs(), "tonnes", "d") == []
    assert C.invalid_dates(pd.Series(["2030-01-01", "not a date"]), "d")


def test_annual_reconciliation_flags_mismatch():
    m = pd.DataFrame({"dataset": ["x"] * 3, "year": [2030] * 3, "tonnes": [10.0, 20.0, np.nan]})
    ok = C.annual_reconciliation(m, pd.DataFrame({"dataset": ["x"], "year": [2030], "reported_total_t": [30.0]}))
    bad = C.annual_reconciliation(m, pd.DataFrame({"dataset": ["x"], "year": [2030], "reported_total_t": [31.0]}))
    assert bool(ok.loc[0, "matches"]) and not bool(bad.loc[0, "matches"])
    assert ok.loc[0, "months_reported"] == 2


def test_overlap_conflicts():
    df = pd.DataFrame(
        {"period": ["p1", "p1", "p2", "p2", "p3"], "src": ["a", "b", "a", "b", "a"], "v": [10.0, 10.0, 5.0, 9.0, 1.0]}
    )
    out = C.overlap_conflicts(df, "period", "v", "src").set_index("period")
    assert bool(out.loc["p1", "agree"]) and not bool(out.loc["p2", "agree"])
    assert "p3" not in out.index


def test_partner_sum_vs_total_and_children():
    p = pd.Timestamp("2030-01-01")
    df = pd.DataFrame(
        {"period": [p] * 3, "cmd_code": ["1006"] * 3, "partner_code": [0, 1, 2], "net_wgt_kg": [100.0, 60.0, 30.0]}
    )
    r = C.partner_sum_vs_total(df)
    assert not bool(r.loc[0, "ok"]) and r.loc[0, "rel_diff"] == pytest.approx(0.1)
    kids = pd.DataFrame(
        {
            "period": [p] * 3,
            "cmd_code": ["1006", "100610", "100630"],
            "partner_code": [0, 0, 0],
            "net_wgt_kg": [100.0, 40.0, 60.0],
        }
    )
    assert bool(C.children_vs_heading(kids, ["100610", "100630"]).loc[0, "ok"])


# ------------------------------------------------------------ analytics
def test_growth_does_not_bridge_gaps():
    df = monthly([100.0, 110.0, np.nan, 130.0]).dropna()
    g = M.add_growth(df).set_index("period")
    assert g.loc["2030-02-01", "mom_pct"] == pytest.approx(10.0)
    assert np.isnan(g.loc["2030-04-01", "mom_pct"])  # previous month absent -> no growth number
    assert np.isnan(g.loc["2030-03-01", "tonnes"])  # the gap stays visible


def test_yoy_requires_exact_twelve_month_lag():
    g = M.add_growth(monthly(list(range(100, 124)))).set_index("period")
    assert g.loc["2031-01-01", "yoy_pct"] == pytest.approx((112 / 100 - 1) * 100)
    assert g["yoy_pct"].iloc[:12].isna().all()


def test_annual_summary_flags_partial_year():
    a = M.annual_summary(monthly([1.0] * 14)).set_index("year")
    assert bool(a.loc[2030, "is_complete"]) and not bool(a.loc[2031, "is_complete"])
    assert a.loc[2031, "months_reported"] == 2


def test_like_for_like_never_compares_partial_with_full():
    df = monthly([10.0] * 12 + [20.0])  # 2031 has January only
    r = M.like_for_like_yoy(df, 2031)
    assert r["comparable"] and r["months"] == [1] and r["change_pct"] == pytest.approx(100.0)
    assert not M.like_for_like_yoy(monthly([10.0] * 5 + [20.0]), 2030)["comparable"]  # no prior year


def test_seasonal_profile_uses_complete_years_only():
    prof = M.seasonal_profile(monthly(list(range(1, 13)) + [1000.0]))
    assert prof["n_years"].max() == 1 and prof["index"].mean() == pytest.approx(1.0)


def test_hhi_and_shares():
    assert M.hhi([1.0]) == 10_000
    assert M.hhi([0.5, 0.5]) == pytest.approx(5_000)
    assert M.hhi(np.full(10, 0.1)) == pytest.approx(1_000)
    with pytest.raises(ValueError):
        M.hhi([0.5, 0.2])
    s = M.shares(pd.DataFrame({"p": ["a", "b", "a"], "v": [1.0, 1.0, 2.0]}), "p", "v")
    assert s.loc[0, "p"] == "a" and s["share"].sum() == pytest.approx(1.0)


def test_price_alignment_inner_join_only():
    a = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2030-01-01", periods=3, freq="MS"))
    b = pd.Series([5.0, np.nan, 7.0], index=pd.date_range("2030-02-01", periods=3, freq="MS"))
    j = M.align_monthly(a, b)
    assert list(j.index.strftime("%Y-%m")) == ["2030-02"] and j.iloc[0].tolist() == [2.0, 5.0]


def test_lagged_correlation_needs_enough_pairs():
    s = pd.Series(np.arange(20.0), index=pd.date_range("2030-01-01", periods=20, freq="MS"))
    out = M.lagged_correlations(s, s * 2, lags=[0, 1], min_pairs=12)
    assert out.loc[0, "pearson"] == pytest.approx(1.0)
    short = M.lagged_correlations(s.iloc[:5], s.iloc[:5], lags=[0], min_pairs=12)
    assert np.isnan(short.loc[0, "pearson"])


def test_unit_value_zero_quantity_is_nan():
    uv = M.unit_value(pd.Series([100.0, 50.0]), pd.Series([10.0, 0.0]))
    assert uv.iloc[0] == 10.0 and np.isnan(uv.iloc[1])
