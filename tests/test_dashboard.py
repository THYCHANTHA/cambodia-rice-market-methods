"""Headless render of every dashboard page (streamlit AppTest). No browser, no network, SYNTHETIC data only."""

import re
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from rice_market import config, demo

APP = Path(__file__).resolve().parents[1] / "app"
PAGES = ["Home.py", *sorted(p.relative_to(APP).as_posix() for p in (APP / "pages").glob("*.py"))]


def _render(page: str) -> AppTest:
    at = AppTest.from_file(str(APP / page), default_timeout=90)
    at.run()
    return at


def _text(at: AppTest) -> str:
    parts = [m.value for m in at.markdown] + [c.value for c in at.caption] + [i.value for i in at.info]
    parts += [e.value for e in at.error] + [w.value for w in at.warning] + [t.value for t in at.title]
    return "\n".join(str(p) for p in parts)


@pytest.fixture
def demo_mode(tmp_path, monkeypatch):
    import streamlit as st

    demo.build_demo(tmp_path / "raw", tmp_path / "demo.duckdb")
    monkeypatch.delenv("RICE_MARKET_MODE", raising=False)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "no_real_warehouse.duckdb")
    monkeypatch.setattr(config, "DEMO_DB_PATH", tmp_path / "demo.duckdb")
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture
def real_mode(built_db, tmp_path, monkeypatch):
    import streamlit as st

    db, _ = built_db
    monkeypatch.delenv("RICE_MARKET_MODE", raising=False)
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "DEMO_DB_PATH", tmp_path / "no_demo.duckdb")
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.fixture
def empty_mode(tmp_path, monkeypatch):
    import streamlit as st

    monkeypatch.delenv("RICE_MARKET_MODE", raising=False)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "none_a.duckdb")
    monkeypatch.setattr(config, "DEMO_DB_PATH", tmp_path / "none_b.duckdb")
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_on_synthetic_demo(demo_mode, page):
    at = _render(page)
    assert not at.exception, [e.value for e in at.exception]
    assert "SYNTHETIC DEMONSTRATION DATA" in _text(at)  # banner on every page
    assert any("Synthetic demonstration data" in w.value for w in at.sidebar.warning)


@pytest.mark.parametrize("page", PAGES)
def test_page_renders_on_a_user_built_warehouse_without_demo_banner(real_mode, page):
    at = _render(page)
    assert not at.exception, [e.value for e in at.exception]
    text = _text(at)
    assert "SYNTHETIC DEMONSTRATION DATA" not in text
    assert "Showing the warehouse you built locally" in text


@pytest.mark.parametrize("page", PAGES)
def test_empty_state_when_no_warehouse_exists(empty_mode, page):
    at = _render(page)
    assert not at.exception, [e.value for e in at.exception]
    text = _text(at)
    assert "No data available" in text and "scripts/make_demo.py" in text
    assert not at.dataframe and not at.metric  # nothing is displayed in place of data
    assert not at.get("plotly_chart")


def test_forced_mode_prefers_demo_over_real(built_db, tmp_path, monkeypatch):
    import streamlit as st

    from rice_market import data_access as da

    db, _ = built_db
    demo.build_demo(tmp_path / "raw", tmp_path / "demo.duckdb")
    monkeypatch.setattr(config, "DB_PATH", db)
    monkeypatch.setattr(config, "DEMO_DB_PATH", tmp_path / "demo.duckdb")
    monkeypatch.delenv("RICE_MARKET_MODE", raising=False)
    assert da.resolve_database()[1] == "real"
    monkeypatch.setenv("RICE_MARKET_MODE", "demo")
    assert da.resolve_database()[1] == "demo"
    monkeypatch.setenv("RICE_MARKET_MODE", "real")
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "gone.duckdb")
    assert da.resolve_database() == (None, "none")  # forced but absent: empty state, never a silent fallback
    st.cache_resource.clear()


def test_attribution_and_non_endorsement_on_every_page(demo_mode):
    for page in PAGES:
        text = " ".join(c.value for c in _render(page).sidebar.caption)
        assert "not endorsed" in text and "UN Comtrade" in text and "World Bank" in text, page


def test_paddy_hidden_by_default_and_flagged(demo_mode):
    at = _render("pages/3_Product_Composition.py")
    assert not at.exception
    box = [c for c in at.checkbox if "paddy" in c.label.lower()]
    assert box and box[0].value is False
    assert "hidden by default" in _text(at)


def test_hs1006_selection_warns_that_paddy_is_included(demo_mode):
    at = _render("pages/1_Export_Trends.py")
    assert not at.exception
    at.selectbox[0].select("comtrade_1006").run()
    assert not at.exception
    assert "includes paddy" in _text(at)


_MONTH_YEAR = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (19|20)\d\d\b")
_SEPARATED = re.compile(r"\b\d{1,3}(?:,\d{3})+\b")
_ALLOWED = {"1,500", "2,500", "10,000", "100,000"}  # HHI band edges and similar generic thresholds


def _findings_in(text: str) -> list[str]:
    """Period labels ('Mar 2031') and thousands-separated figures that are not generic thresholds."""
    found = [m.group(0) for m in _MONTH_YEAR.finditer(text)]
    found += sorted(set(_SEPARATED.findall(text)) - _ALLOWED)
    return found


def test_dashboard_source_contains_no_hardcoded_market_findings():
    """The shipped app must not embed statistics, period labels or conclusions: numbers come only from the warehouse.

    Structural check (it names no real value): no 'Month YYYY' labels, and no multi-digit figures with thousands separators
    other than a small allow-list of generic thresholds.
    """
    for f in [*APP.glob("*.py"), *(APP / "pages").glob("*.py")]:
        problems = _findings_in(f.read_text(encoding="utf-8"))
        assert not problems, f"{f.name}: {problems}"


def test_findings_gate_actually_detects_violations():
    """Guards the gate above against going vacuous (for example through a mangled regular expression)."""
    assert _findings_in('st.write("Exports peaked in Mar 2031 at 12,345 t")')
    assert _findings_in('x = "December 2034"')
    assert _findings_in('y = "total 98,765"')
    assert not _findings_in('z = "HHI bands: under 1,500 unconcentrated, above 2,500 high; 10,000 maximum"')
    assert not _findings_in("fig.update_layout(height=380)")
