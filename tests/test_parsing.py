"""Parsing and normalisation tests. Fixtures are SYNTHETIC text shaped like the real files; they carry no real data."""

import pandas as pd
import pytest

from rice_market.ingestion.comtrade import periods
from rice_market.transformation import mef, pink_sheet
from rice_market.transformation.comtrade import parse_payload

LONG = "month,year,export_metric_tons\r\njan,2030,1000.0\r\nfeb,2030,\r\ndec,2030,2500.0"
WIDE = "﻿Monthly,2031\r\nJan,100\r\nFeb,\r\nMar,300\r\nYearly Export,400\r\n"


def test_month_labels_case_insensitive():
    assert mef.month_number("JAN") == 1
    assert mef.month_number("Dec") == 12
    with pytest.raises(ValueError):
        mef.month_number("xyz")


def test_long_layout_blank_is_missing_not_zero():
    m, a = mef.parse_long(LONG, "t")
    assert list(m["month"]) == [1, 2, 12]
    assert m.loc[m.month == 2, "status"].item() == "missing"
    assert pd.isna(m.loc[m.month == 2, "tonnes"].item())
    assert a.empty
    assert m["period"].iloc[0] == pd.Timestamp("2030-01-01")


def test_wide_layout_bom_and_annual_row():
    m, a = mef.parse_wide(WIDE, "t31")
    assert list(m["year"].unique()) == [2031]
    assert m["tonnes"].sum() == 400
    assert a.loc[0, "reported_total_t"] == 400
    assert m.loc[m.month == 2, "status"].item() == "missing"


def test_period_dot_number_is_tonnes_not_decimal():
    # '1234.0' must stay 1,234 t; a thousands-style '1,234' must be refused rather than guessed.
    assert mef._number("1234.0") == 1234.0
    with pytest.raises(ValueError):
        mef._number("1,234")


def test_unexpected_columns_rejected():
    with pytest.raises(ValueError):
        mef.parse_long("a,b,c\r\n1,2,3", "bad")


def test_pink_sheet_period_and_missing_markers():
    assert pink_sheet.parse_period("1999M07") == pd.Timestamp("1999-07-01")
    with pytest.raises(ValueError):
        pink_sheet.parse_period("1999-07")
    assert pink_sheet.parse_value("..") is None
    assert pink_sheet.parse_value("…") is None
    assert pink_sheet.parse_value("#VALUE!") is None
    assert pink_sheet.parse_value("104.5") == 104.5
    assert pink_sheet.is_error_cell("#VALUE!") and not pink_sheet.is_error_cell(3.0)


def test_comtrade_period_range_crosses_year_end():
    assert periods("202411", "202502") == ["202411", "202412", "202501", "202502"]


def test_comtrade_payload_parsing():
    payload = {
        "data": [
            {
                "refYear": 2030,
                "refMonth": 3,
                "cmdCode": "100630",
                "reporterCode": 116,
                "partnerCode": 0,
                "netWgt": 5000.0,
                "qty": 5000.0,
                "qtyUnitCode": 8,
                "fobvalue": 900.0,
                "cifvalue": None,
                "primaryValue": 900.0,
                "isNetWgtEstimated": False,
                "isAggregate": True,
            }
        ]
    }
    rows = parse_payload("exports", payload)
    assert rows[0]["period"] == pd.Timestamp("2030-03-01")
    assert rows[0]["cmd_code"] == "100630"
    assert rows[0]["net_wgt_kg"] == 5000.0
    assert parse_payload("exports", {"data": None}) == []


def test_quota_exceeded_is_a_clear_error_not_a_retry_loop(monkeypatch):
    import requests

    from rice_market.ingestion import http

    calls = []

    class Resp:
        status_code = 403
        text = "Quota Exceeded"

    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(1) or Resp())
    with pytest.raises(http.QuotaExceeded, match="re-run later"):
        http.get_with_retry("https://example.invalid/x?y=1")
    assert len(calls) == 1  # no pointless retries
