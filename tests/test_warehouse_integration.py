"""Integration tests: build the whole warehouse from SYNTHETIC raw files and check constraints and reconciliation."""

import duckdb
import pytest

from rice_market import data_access as da


def test_build_summary(built_db):
    _, s = built_db
    assert s["sows_months"] == 22  # 24 months minus 2 blanks
    assert s["sows_last"] == "2031-10-01"
    assert s["comtrade_export_months"] == 24


def test_missing_months_are_rows_with_status_not_zero(built_db):
    db, _ = built_db
    con = duckdb.connect(str(db), read_only=True)
    r = con.execute(
        "SELECT tonnes, status FROM fct_export_monthly WHERE series_id='sows_mef' AND period='2031-12-01'"
    ).fetchone()
    assert r == (None, "missing")
    assert con.execute("SELECT count(*) FROM fct_export_monthly WHERE tonnes = 0").fetchone()[0] == 0


def test_overlapping_mef_files_agree_and_are_not_double_counted(built_db):
    db, _ = built_db
    con = duckdb.connect(str(db), read_only=True)
    assert (
        con.execute(
            "SELECT count(*) FROM fct_export_monthly WHERE series_id='sows_mef' AND period < '2031-01-01'"
        ).fetchone()[0]
        == 12
    )
    ov = con.execute(
        "SELECT count(*), sum(agrees::int) FROM dq_reconciliation WHERE kind='mef_file_overlap'"
    ).fetchone()
    assert ov == (12, 12)


def test_annual_total_reconciles_and_year_flags(built_db):
    db, _ = built_db
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT agrees FROM dq_reconciliation WHERE kind='mef_annual_total'").fetchone()[0] is True
    ann = dict(con.execute("SELECT year, is_complete FROM fct_export_annual WHERE series_id='sows_mef'").fetchall())
    assert ann == {2030: True, 2031: False}


def test_primary_key_is_enforced(built_db):
    db, _ = built_db
    con = duckdb.connect(str(db))
    with pytest.raises(duckdb.ConstraintException):
        con.execute("INSERT INTO fct_export_monthly VALUES ('sows_mef', '2030-01-01', 1, NULL, 'reported')")


def test_negative_quantity_is_refused_by_constraint(built_db):
    db, _ = built_db
    con = duckdb.connect(str(db))
    with pytest.raises(duckdb.ConstraintException):
        con.execute("INSERT INTO fct_export_monthly VALUES ('sows_mef', '2040-01-01', -5, NULL, 'reported')")


def test_comtrade_units_kg_to_tonnes_and_children_sum(built_db):
    db, _ = built_db
    con = duckdb.connect(str(db), read_only=True)
    t = con.execute(
        "SELECT tonnes FROM fct_export_monthly WHERE series_id='comtrade_100630' AND period='2030-01-01'"
    ).fetchone()[0]
    assert t == 100.0  # 100,000 kg
    bad = con.execute("SELECT count(*) FROM dq_reconciliation WHERE kind='hs_children_vs_heading'").fetchone()[0]
    assert bad == 0


def test_partner_rows_exclude_world_and_carry_names(built_db):
    db, _ = built_db
    con = duckdb.connect(str(db), read_only=True)
    names = {r[0] for r in con.execute("SELECT DISTINCT partner_name FROM fct_partner_monthly").fetchall()}
    assert names == {"Testland", "Fakeria"}
    assert con.execute("SELECT count(*) FROM fct_partner_monthly WHERE partner_code = 0").fetchone()[0] == 0


def test_paddy_gap_is_missing_not_zero(built_db):
    db, _ = built_db
    con = duckdb.connect(str(db), read_only=True)
    rows = con.execute(
        "SELECT status, count(*) FROM fct_export_monthly WHERE series_id='comtrade_100610' GROUP BY 1 ORDER BY 1"
    ).fetchall()
    assert rows == [("missing", 21), ("reported", 3)]


def test_pink_sheet_error_cell_and_blank_become_null_and_are_logged(built_db):
    db, _ = built_db
    con = duckdb.connect(str(db), read_only=True)
    assert (
        con.execute(
            "SELECT usd_per_tonne FROM fct_price_monthly WHERE series='rice_thai_25' AND period='2030-04-01'"
        ).fetchone()[0]
        is None
    )
    assert (
        con.execute(
            "SELECT count(*) FROM fct_price_monthly WHERE series='rice_thai_a1' AND usd_per_tonne IS NOT NULL"
        ).fetchone()[0]
        == 0
    )
    assert con.execute("SELECT count(*) FROM dq_issue WHERE check_name='source_error_cell'").fetchone()[0] == 1


def test_price_alignment_with_exports_uses_common_months_only(built_db):
    db, _ = built_db
    con = da.connect(db)
    from rice_market.analytics import metrics as M

    ex = da.monthly(con, "comtrade_100630").set_index("period")["tonnes"]
    px = da.prices(con, ["rice_thai_5"]).set_index("period")["usd_per_tonne"]
    assert len(M.align_monthly(ex, px)) == 24


def test_data_access_health_and_missing_warehouse(built_db, tmp_path):
    db, _ = built_db
    con = da.connect(db)
    h = da.health(con)
    assert h["fct_export_monthly"] > 0
    assert h["forecast_summary"] == 0  # experiment not run in the fixture ...
    assert h["ok"] is False  # ... so the health check must say so rather than pass
    with pytest.raises(da.WarehouseMissing):
        da.connect(tmp_path / "nope.duckdb")


def test_rebuild_is_idempotent(synthetic_raw, tmp_path):
    from rice_market.transformation.build import build

    db = tmp_path / "x.duckdb"
    a = build(raw=synthetic_raw, db_path=db)
    b = build(raw=synthetic_raw, db_path=db)
    assert a == b
