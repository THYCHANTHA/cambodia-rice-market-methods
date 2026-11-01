"""Data quality, reconciliation, sources and methods for whatever data are loaded."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rice_market import data_access as da
from rice_market import ui

ui.setup("Data Quality & Methodology", "🧪")
con = ui.con()
st.title("Data Quality & Methodology")

st.subheader("Sources and how this toolkit obtains them")
st.table(
    pd.DataFrame(
        [
            [
                "Cambodia Data EF / MEF, Secretariat One Window Service",
                "Monthly export volume (metric tons)",
                "Manual import of files you download yourself (`scripts/import_mef.py`); automated retrieval is disabled",
                "Use with attribution; no licence or redistribution terms stated: see docs/DATA_LICENSE_AUDIT.md",
            ],
            [
                "UN Comtrade",
                "Monthly trade by HS code and partner; mirror imports",
                "Optional connector, explicit opt-in, call budget (`scripts/fetch_comtrade.py`)",
                "Subject to the UN Comtrade licence and re-dissemination policy: see docs/DATA_LICENSE_AUDIT.md",
            ],
            [
                "World Bank Commodity Price Data (The Pink Sheet)",
                "Monthly benchmark rice prices (nominal US$/t)",
                "Optional download (`scripts/fetch_optional_sources.py --pink-sheet`)",
                "CC BY 4.0 default for World Bank datasets; third-party quotations credited in the file; attribute and state changes",
            ],
        ],
        columns=["Source", "Content", "How obtained here", "Terms status"],
    ).set_index("Source")
)

snap = da.snapshots(con)
if len(snap):
    with st.expander("Download manifest (retrieval time and SHA-256)"):
        st.dataframe(
            snap.drop(columns=["url"]).assign(sha256=snap["sha256"].str[:16] + "..."), hide_index=True, width="stretch"
        )

st.subheader("Completeness by series")
cat = da.series_catalog(con)
if cat.empty:
    st.info("No export series loaded.")
else:
    cat = cat.assign(
        first_reported=cat["first_reported"].dt.strftime("%Y-%m"),
        last_reported=cat["last_reported"].dt.strftime("%Y-%m"),
    )
    st.dataframe(
        cat[["series_id", "label", "first_reported", "last_reported", "months_reported", "months_in_span"]].rename(
            columns={"months_in_span": "months in span"}
        ),
        hide_index=True,
        width="stretch",
    )
    fig = go.Figure()
    for sid in cat["series_id"]:
        d = da.monthly(con, sid)
        fig.add_scatter(
            x=d["period"],
            y=[sid] * len(d),
            mode="markers",
            marker=dict(
                symbol="square", size=7, color=[ui.BLUE if s == "reported" else "#e5b9b9" for s in d["status"]]
            ),
            showlegend=False,
            hovertext=d["status"],
        )
    st.plotly_chart(ui.style(fig, 80 + 40 * len(cat), legend_below=False), width="stretch")
    st.caption(
        "Blue = reported; pink = month inside the series span with no value (kept missing). Dates in a source's metadata "
        "(for example 'updated on') are not data coverage: read coverage from this table."
    )

st.subheader("Reconciliation of sources")
rec = da.reconciliation(con)
if rec.empty:
    st.info("No reconciliation rows (they appear when two statements of the same quantity exist).")
else:
    summ = (
        rec.assign(abs_rel=rec["rel_diff"].abs())
        .groupby("kind")
        .agg(
            comparisons=("key", "count"),
            agree=("agrees", "sum"),
            median_rel_diff=("rel_diff", "median"),
            mean_abs_rel=("abs_rel", "mean"),
        )
        .reset_index()
    )
    st.dataframe(
        summ.style.format({"median_rel_diff": "{:+.3f}", "mean_abs_rel": "{:.3f}"}), hide_index=True, width="stretch"
    )
    st.caption(
        "'agree' = within the stated tolerance (0.5 t for file overlaps and annual totals; 5% for cross-source monthly "
        "comparisons). A relative difference is (second statement - first) / first."
    )

st.subheader("Detected issues and decisions")
iss = da.issues(con)
if iss.empty:
    st.info("No issues recorded.")
else:
    st.dataframe(iss, hide_index=True, width="stretch")

st.subheader("Methods in brief")
st.markdown(
    "- **Layers:** raw files (kept byte-for-byte, hashed) → standardised tables in DuckDB → analytics → dashboard.\n"
    "- **Never silently altered:** blank values stay missing; nothing is interpolated; sources are not merged; a partial year "
    "is never compared with a full year.\n"
    "- **Units:** MEF-style values are plain metric tons (thousands separators are refused, not guessed). Comtrade net weight "
    "is kilograms, converted to tonnes.\n"
    "- **Forecasting:** expanding-window rolling-origin backtests; MAE, RMSE, sMAPE; baselines first.\n"
    "- **Full documents:** see `docs/` in the repository."
)
st.subheader("Limitations of this toolkit")
st.markdown(
    "- It reports what the loaded data show; it does not judge whether a source is complete. Use the completeness and "
    "reconciliation tables, and compare with importers' (mirror) reports.\n"
    "- Product definitions can differ between publishers; HS 1006 includes paddy.\n"
    "- Benchmark prices are not exporter prices; correlations are exploratory.\n"
    "- Backtests describe fit to the history provided and are not forecasts."
)
