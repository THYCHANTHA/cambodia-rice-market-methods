"""Tests for the methods-only release: manual MEF import, optional connectors, absent sources, demo data.

All data here are SYNTHETIC (invented) or empty; no test touches the network.
"""

import json
import runpy
import sys

import duckdb
import numpy as np
import pandas as pd
import pytest

from rice_market import config, demo
from rice_market.forecasting import experiment as E
from rice_market.ingestion import comtrade as ct
from rice_market.ingestion import manual_import as mi
from rice_market.transformation.build import build

GOOD_LONG = "month,year,export_metric_tons\r\njan,2030,100.0\r\nfeb,2030,\r\nmar,2030,120.5\r\n"
GOOD_WIDE = "﻿Monthly,2031\r\nJan,10\r\nFeb,20\r\nYearly Export,30\r\n"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Keep manifests and raw files inside tmp_path."""
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "RAW", tmp_path / "data" / "raw")
    monkeypatch.setattr(config, "MANIFESTS", tmp_path / "data" / "manifests")
    monkeypatch.setattr(config, "DOWNLOAD_MANIFEST", tmp_path / "data" / "manifests" / "downloads.jsonl")
    return tmp_path


# ---------------------------------------------------------------- MEF manual import
def test_manual_import_validates_copies_and_records_without_network(isolated, monkeypatch):
    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("manual import must not use the network"))
    a, b = isolated / "x.csv", isolated / "y.csv"
    a.write_text(GOOD_LONG, encoding="utf-8")
    b.write_bytes(GOOD_WIDE.encode("utf-8"))
    out = mi.import_files([a, b])
    assert [o["stored_as"] for o in out] == ["mef_x.csv", "mef_y.csv"]
    assert (config.RAW / "mef" / "mef_x.csv").read_bytes() == a.read_bytes()  # byte-for-byte
    manifest = config.DOWNLOAD_MANIFEST.read_text(encoding="utf-8")
    assert "mef_manual_import" in manifest and "no network access" in manifest
    assert str(isolated) not in manifest  # no machine-specific absolute paths


def test_manual_import_refuses_bad_files_and_is_all_or_nothing(isolated):
    good, bad = isolated / "good.csv", isolated / "bad.csv"
    good.write_text(GOOD_LONG, encoding="utf-8")
    bad.write_text("month,year,export_metric_tons\r\njan,2030,1,234\r\n", encoding="utf-8")  # separator inside a value
    with pytest.raises(mi.ImportRefused):
        mi.import_files([good, bad])
    assert not (config.RAW / "mef").exists() or not list((config.RAW / "mef").glob("*.csv"))  # nothing copied
    for text in ("a,b,c\r\n1,2,3\r\n", "month,year,export_metric_tons\r\njan,2030,-5\r\n", ""):
        f = isolated / "w.csv"
        f.write_text(text, encoding="utf-8")
        with pytest.raises(mi.ImportRefused):
            mi.validate_file(f)
    with pytest.raises(mi.ImportRefused):
        mi.validate_file(isolated / "does_not_exist.csv")


def test_no_automated_mef_retrieval_exists_in_the_package():
    """No MEF connector in the API surface (the tracked-file text scan lives in test_repo_hygiene)."""
    import rice_market.ingestion.sources as sources

    assert not [n for n in dir(sources) if "mef" in n.lower()]
    assert not [n for n in dir(config) if n.startswith("MEF_")]


# ---------------------------------------------------------------- optional Comtrade connector
def test_fetch_range_respects_call_budget_and_cache(isolated, monkeypatch):
    calls = []

    def fake_fetch(view, period, force=False):
        path = ct.cache_path(view, period)
        if path.exists():
            return path, False
        calls.append(period)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"count": 0, "data": []}), encoding="utf-8")
        return path, True

    monkeypatch.setattr(ct, "fetch_period", fake_fetch)
    monkeypatch.setattr(ct, "PAUSE_SECONDS", 0)
    s1 = ct.fetch_range("exports", "203001", "203012", log=lambda *_: None, max_calls=5)
    assert len(calls) == 5 and s1["stopped"] is True
    s2 = ct.fetch_range("exports", "203001", "203012", log=lambda *_: None, max_calls=5)  # resumes; cached months free
    assert len(calls) == 10 and s2["cached"] == 5
    s3 = ct.fetch_range("exports", "203001", "203012", log=lambda *_: None)
    assert len(calls) == 12 and s3["stopped"] is False


def test_comtrade_script_refuses_without_explicit_terms_flag(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["fetch_comtrade.py", "--start", "203001", "--end", "203001"])
    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("must not call the network without opt-in"))
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(config.ROOT / "scripts" / "fetch_comtrade.py"), run_name="__main__")
    assert exc.value.code == 2
    assert "REFUSED" in capsys.readouterr().out


def test_pipeline_downloads_nothing_by_default_and_refuses_comtrade_without_opt_in(monkeypatch, capsys):
    import requests

    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("no network use expected"))
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py", "--comtrade"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(config.ROOT / "scripts" / "run_pipeline.py"), run_name="__main__")
    assert exc.value.code == 2
    assert "REFUSED" in capsys.readouterr().out


def test_user_agent_is_configurable_and_generic_by_default():
    from rice_market.ingestion import http

    assert "rice-market-methods" in http.DEFAULT_USER_AGENT
    assert "THYCHANTHA" not in http.DEFAULT_USER_AGENT


# ---------------------------------------------------------------- absent sources
def test_build_runs_with_no_sources_at_all(tmp_path):
    raw = tmp_path / "raw"
    raw.mkdir()
    db = tmp_path / "empty.duckdb"
    summary = build(raw=raw, db_path=db)
    assert summary["sows_months"] == 0 and summary["comtrade_export_months"] == 0
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT count(*) FROM fct_export_monthly").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM dq_issue WHERE check_name = 'source_absent'").fetchone()[0] == 1


def test_build_runs_with_only_prices(tmp_path, synthetic_raw):
    raw = tmp_path / "only_prices"
    (raw / "worldbank").mkdir(parents=True)
    (raw / "worldbank" / "CMO-Historical-Data-Monthly.xlsx").write_bytes(
        (synthetic_raw / "worldbank" / "CMO-Historical-Data-Monthly.xlsx").read_bytes()
    )
    db = tmp_path / "p.duckdb"
    build(raw=raw, db_path=db)
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT count(*) FROM fct_price_monthly").fetchone()[0] > 0
    assert con.execute("SELECT count(*) FROM fct_export_monthly").fetchone()[0] == 0


def test_narrower_mef_file_wins_a_conflict_and_the_conflict_is_logged(tmp_path):
    raw = tmp_path / "raw"
    (raw / "mef").mkdir(parents=True)
    (raw / "mef" / "mef_wide.csv").write_text(
        "month,year,export_metric_tons\r\njan,2030,100.0\r\nfeb,2030,200.0\r\nmar,2030,300.0\r\n", encoding="utf-8"
    )
    (raw / "mef" / "mef_narrow.csv").write_bytes("﻿Monthly,2030\r\nJan,999\r\nYearly Export,999\r\n".encode())
    db = tmp_path / "c.duckdb"
    build(raw=raw, db_path=db)
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT tonnes FROM fct_export_monthly WHERE period = '2030-01-01'").fetchone()[0] == 999.0
    assert con.execute("SELECT count(*) FROM dq_issue WHERE check_name = 'overlap_conflict'").fetchone()[0] == 1


# ---------------------------------------------------------------- experiment settings and span detection
def test_longest_gap_free_span_ignores_gaps_and_picks_the_longest_run():
    idx = pd.date_range("2030-01-01", periods=20, freq="MS")
    s = pd.Series(np.arange(20.0), index=idx).drop(idx[5])  # gap at month 6
    start, end = E.longest_gap_free_span(s)
    assert (start, end) == (idx[6], idx[19])  # run of 14 beats the first run of 5
    assert E.longest_gap_free_span(pd.Series(dtype=float)) is None


def test_experiment_config_defaults_and_override(tmp_path):
    assert E.load_config(tmp_path / "missing.yaml")["min_train"] == 24
    f = tmp_path / "c.yaml"
    f.write_text("min_train: 18\nhorizons: [1, 2]\n", encoding="utf-8")
    cfg = E.load_config(f)
    assert cfg["min_train"] == 18 and cfg["horizons"] == [1, 2]


def test_experiment_runs_on_synthetic_warehouse_and_labels_roles(tmp_path):
    info = demo.write_synthetic_raw(tmp_path / "raw")
    db = tmp_path / "d.duckdb"
    build(raw=tmp_path / "raw", db_path=db)
    cfg = E.load_config() | {"min_months": 36}
    rec = E.run(db_path=db, out_dir=tmp_path / "out", cfg=cfg)
    ok = {k: v for k, v in rec["series"].items() if v.get("status") == "ok"}
    assert ok, rec
    for v in ok.values():
        assert v["role"] == ("primary" if v["annual_cycles"] >= 4 else "exploratory")
        assert v["span_source"] == "detected"
    assert info["months"] == 60
    assert (tmp_path / "out" / "forecast_experiment.json").exists()
    con = duckdb.connect(str(db), read_only=True)
    assert con.execute("SELECT count(*) FROM forecast_series").fetchone()[0] == len(ok)


# ---------------------------------------------------------------- synthetic demo data
def test_demo_is_deterministic_and_clearly_synthetic(tmp_path):
    demo.write_synthetic_raw(tmp_path / "a")
    demo.write_synthetic_raw(tmp_path / "b")
    f1 = (tmp_path / "a" / "comtrade" / "exports" / "203003.json").read_bytes()
    assert f1 == (tmp_path / "b" / "comtrade" / "exports" / "203003.json").read_bytes()
    assert (
        (tmp_path / "a" / "SYNTHETIC_DATA.txt").read_text(encoding="utf-8").startswith("SYNTHETIC DEMONSTRATION DATA")
    )
    names = json.loads((tmp_path / "a" / "comtrade" / "reference" / "partnerAreas.json").read_text(encoding="utf-8"))[
        "results"
    ]
    assert all(r["PartnerDesc"].startswith("Synthetic") or r["PartnerDesc"] == "World" for r in names)
    years = {int(p.stem[:4]) for p in (tmp_path / "a" / "comtrade" / "exports").glob("*.json")}
    assert min(years) >= 2030  # fictional future years, not any real period
    assert demo.EXPORTER_CODE not in (116,)  # the exporter code is fictional


def test_build_demo_produces_a_consistent_warehouse(tmp_path):
    summary = demo.build_demo(tmp_path / "raw", tmp_path / "demo.duckdb")
    assert summary["months"] == 60
    con = duckdb.connect(str(tmp_path / "demo.duckdb"), read_only=True)
    assert (
        con.execute("SELECT count(*) FROM dq_reconciliation WHERE kind = 'hs_children_vs_heading'").fetchone()[0] == 0
    )
    assert con.execute("SELECT count(*) FROM dq_issue WHERE check_name = 'partner_sum_vs_world'").fetchone()[0] == 0
    assert con.execute("SELECT count(*) FROM fct_mirror_monthly").fetchone()[0] > 0
    assert con.execute("SELECT count(*) FROM forecast_summary").fetchone()[0] > 0
