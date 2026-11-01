"""Shared Streamlit helpers: theme, warehouse resolution, empty state, KPI cards, caveat banners, plotly defaults."""

from __future__ import annotations

import re

import plotly.graph_objects as go
import streamlit as st

from rice_market import data_access as da

BLUE = "#1f6fb2"
LIGHT_BLUE = "#9cc9ee"
PALE = "#eaf3fc"
ORANGE = "#d9822b"
GREY = "#6b7a8c"
INK = "#12263f"
PALETTE = [BLUE, ORANGE, "#2a9d8f", "#8e6bbf", GREY, "#c0504d", "#4f9fd8", "#a3a847"]

CSS = f"""
<style>
html, body, [class*="css"] {{ font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif; color: {INK}; }}
h1 {{ font-weight: 650; letter-spacing: -0.01em; }}
h2, h3 {{ font-weight: 600; }}
.block-container {{ padding-top: 2.2rem; max-width: 1200px; }}
.kpi {{ background: {PALE}; border: 1px solid #d3e6f8; border-radius: 10px; padding: 14px 16px; height: 100%; }}
.kpi .label {{ font-size: 0.78rem; color: {GREY}; text-transform: uppercase; letter-spacing: 0.04em; }}
.kpi .value {{ font-size: 1.7rem; font-weight: 650; color: {BLUE}; line-height: 1.25; }}
.kpi .note {{ font-size: 0.8rem; color: {GREY}; }}
.caveat {{ border-left: 4px solid {ORANGE}; background: #fff7ee; padding: 10px 14px; border-radius: 4px;
          font-size: 0.9rem; margin: 0.4rem 0 1rem 0; }}
.info {{ border-left: 4px solid {BLUE}; background: {PALE}; padding: 10px 14px; border-radius: 4px;
        font-size: 0.9rem; margin: 0.4rem 0 1rem 0; }}
@media (max-width: 640px) {{ .kpi .value {{ font-size: 1.3rem; }} .block-container {{ padding: 1rem 0.8rem; }} }}
</style>
"""

ATTRIBUTION = (
    "Independent research toolkit; not endorsed by any data provider. If you load real data, attribute each source "
    "(UN Comtrade; Cambodia Data EF / MEF, Secretariat One Window Service; World Bank Commodity Price Data (The Pink "
    "Sheet), whose rice quotations are credited to Bloomberg Finance L.P. and USDA) and follow its terms; derived "
    "figures are your own calculations."
)
DEMO_BANNER = (
    "**SYNTHETIC DEMONSTRATION DATA.** Every number in this app was invented by a random generator "
    "(`scripts/make_demo.py`). These are not trade statistics and show no real finding."
)
REAL_NOTE = (
    "Showing the warehouse you built locally from data you supplied. Check each provider's terms before sharing "
    "any chart, table or figure from it."
)


def _html(text: str) -> str:
    """Inside raw HTML blocks markdown is not parsed, so convert **bold** and `code` explicitly."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", text)


def setup(title: str, icon: str = "🌾") -> None:
    st.set_page_config(page_title=f"{title} | Rice Market Methods", page_icon=icon, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.sidebar.caption(ATTRIBUTION)
    _, current = da.resolve_database()
    if current == "demo":
        st.markdown(f'<div class="caveat">{_html(DEMO_BANNER)}</div>', unsafe_allow_html=True)
        st.sidebar.warning("Synthetic demonstration data")
    elif current == "real":
        st.markdown(f'<div class="info">{_html(REAL_NOTE)}</div>', unsafe_allow_html=True)


@st.cache_resource(show_spinner=False)
def _connection(path: str):
    return da.connect(path)


def mode() -> str:
    """'real', 'demo' or 'none' (see data_access.resolve_database)."""
    return da.resolve_database()[1]


def con():
    """Read-only connection to the resolved warehouse, or a clear empty state (and stop) if there is none."""
    path, _ = da.resolve_database()
    if path is None:
        st.title("No data available")
        st.info(
            "No warehouse was found, so there is nothing to display. This app never invents or substitutes numbers "
            "by itself.\n\n"
            "- To explore the app with **synthetic demonstration data**: `python scripts/make_demo.py`\n"
            "- To analyse **your own data**: import MEF files with `python scripts/import_mef.py <files>`, optionally "
            "use the connectors described in the README, then run `python scripts/run_pipeline.py`"
        )
        st.stop()
    return _connection(str(path))


def kpi(label: str, value: str, note: str = "") -> str:
    return (
        f'<div class="kpi"><div class="label">{label}</div><div class="value">{value}</div>'
        f'<div class="note">{note}</div></div>'
    )


def caveat(text: str) -> None:
    st.markdown(f'<div class="caveat">{_html(text)}</div>', unsafe_allow_html=True)


def info(text: str) -> None:
    st.markdown(f'<div class="info">{_html(text)}</div>', unsafe_allow_html=True)


def style(fig: go.Figure, height: int = 380, legend_below: bool = True) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        height=height,
        margin=dict(l=10, r=10, t=40, b=10),
        font=dict(family="Segoe UI, Arial, sans-serif", color=INK, size=13),
        colorway=PALETTE,
        legend=dict(orientation="h", y=-0.2) if legend_below else {},
        hovermode="x unified",
    )
    return fig


def tonnes(v: float | None) -> str:
    if v is None or v != v:
        return "n/a"
    return f"{v / 1000:,.1f} kt" if abs(v) >= 1000 else f"{v:,.0f} t"


def month_label(ts) -> str:
    return "n/a" if ts is None or ts != ts else ts.strftime("%b %Y")
