"""Overview: what is in the loaded warehouse, how complete it is, and how the sources relate."""

import plotly.graph_objects as go
import streamlit as st

from rice_market import data_access as da
from rice_market import ui

ui.setup("Overview")
con = ui.con()

st.title("Cambodia Rice Market Methods")
st.caption(
    "Open methods for rice export statistics: ingestion, validation, reconciliation, analytics and forecast evaluation."
)
ui.info(
    "Export volumes from different publishers are kept as **separate series** and compared, never merged. "
    "Benchmark prices are international quotations, **not** Cambodian export prices. "
    "A year counts as complete only when all 12 months are reported."
)

cat = da.series_catalog(con)
if cat.empty:
    st.warning("The warehouse contains no export series yet. Import or download data, then rebuild (see README).")
    st.stop()

st.subheader("Latest period per series")
shown = cat.head(4)
cols = st.columns(len(shown))
for col, row in zip(cols, shown.itertuples(), strict=True):
    m = da.monthly(con, row.series_id)
    rep = m[m["status"] == "reported"]
    last = rep.iloc[-1] if len(rep) else None
    col.markdown(
        ui.kpi(
            row.series_id,
            ui.month_label(last["period"]) if last is not None else "n/a",
            f"{ui.tonnes(last['tonnes'])} · {int(row.months_reported)} of {int(row.months_in_span)} months reported"
            if last is not None
            else "no reported months",
        ),
        unsafe_allow_html=True,
    )
gaps = cat[cat["months_reported"] < cat["months_in_span"]]
if len(gaps):
    ui.caveat(
        "Series with months inside their span but **no value** (kept missing, never zero): "
        + ", ".join(f"{r.series_id} ({int(r.months_in_span - r.months_reported)})" for r in gaps.itertuples())
        + "."
    )

st.subheader("Source coverage")
fig = go.Figure()
for i, row in enumerate(cat.itertuples()):
    fig.add_scatter(
        x=[row.first_reported, row.last_reported],
        y=[row.series_id, row.series_id],
        mode="lines+markers",
        line=dict(color=ui.PALETTE[i % len(ui.PALETTE)], width=12),
        marker=dict(size=7),
        showlegend=False,
        hovertemplate=f"{row.series_id}<br>{ui.month_label(row.first_reported)} to {ui.month_label(row.last_reported)}"
        "<extra></extra>",
    )
st.plotly_chart(ui.style(fig, 60 + 45 * len(cat), legend_below=False), width="stretch")
st.caption(
    "First and last month with a reported value for each series. Compare series only over the months they share."
)

st.subheader("Compare two series (shown side by side, as published)")
ids = cat["series_id"].tolist()
a_col, b_col = st.columns(2)
sa = a_col.selectbox("First series", ids, index=0)
sb = b_col.selectbox("Second series", ids, index=min(1, len(ids) - 1))
fig = go.Figure()
for sid in dict.fromkeys([sa, sb]):
    m = da.monthly(con, sid)
    fig.add_scatter(x=m["period"], y=m["tonnes"], name=sid, mode="lines+markers", connectgaps=False)
fig.update_yaxes(title="metric tons")
st.plotly_chart(ui.style(fig), width="stretch")
st.caption(
    "Different publishers can define the product, the month and the unit differently. See Data Quality & Methodology for the "
    "reconciliation tables computed from your data."
)

st.subheader("Questions this toolkit helps examine")
st.markdown(
    "1. How has export volume changed, and how do two sources compare over their common months?\n"
    "2. What seasonal pattern and trend are visible (and how many complete annual cycles support them)?\n"
    "3. Which destinations matter, and how concentrated are they (shares, HHI)?\n"
    "4. How does export growth co-move with international benchmark prices (exploratory, not causal)?\n"
    "5. How do simple and statistical forecasting methods compare in chronological backtests?"
)
st.caption("The app computes answers only from the data loaded in the warehouse; it does not ship any.")
