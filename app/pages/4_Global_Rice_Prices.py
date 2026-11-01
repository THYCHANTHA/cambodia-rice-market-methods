"""Global rice prices: benchmark quotations kept separate from trade values; exploratory comparison only."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rice_market import data_access as da
from rice_market import ui
from rice_market.analytics import metrics as M

ui.setup("Global Rice Prices", "💵")
con = ui.con()
st.title("Global Rice Prices")
ui.caveat(
    "These are **international benchmark quotations** (nominal US$ per tonne, free-on-board indications for other "
    "countries' rice), not the exporter's prices and not transaction prices. Source of the optional workbook: World Bank "
    "Commodity Price Data (The Pink Sheet); the rice quotations are credited in the file to Bloomberg Finance L.P., the "
    "US Department of Agriculture and the World Bank."
)

allp = da.prices(con)
if allp.empty:
    st.info("No price data loaded. The Pink Sheet workbook is an optional download (see README).")
    st.stop()
series = sorted(allp["series"].unique())
chosen = st.sidebar.multiselect("Benchmark series", series, default=series[:2])
lo_year = int(allp["period"].dt.year.min())
hi_year = int(allp["period"].dt.year.max())
since = st.sidebar.slider("From year", lo_year, hi_year, lo_year)
if not chosen:
    st.info("Select at least one series in the sidebar.")
    st.stop()

pr = allp[allp["series"].isin(chosen) & (allp["period"].dt.year >= since)]
fig = go.Figure()
for s in chosen:
    d = pr[pr["series"] == s]
    fig.add_scatter(x=d["period"], y=d["usd_per_tonne"], name=s, connectgaps=False)
fig.update_yaxes(title="nominal US$ per tonne")
st.plotly_chart(ui.style(fig), width="stretch")
cov = allp.dropna(subset=["usd_per_tonne"]).groupby("series")["period"].agg(["min", "max"])
st.caption(
    "Nominal US dollars (not inflation-adjusted). Blank months stay blank. Coverage: "
    + "; ".join(f"{s}: {r['min']:%Y-%m} to {r['max']:%Y-%m}" for s, r in cov.loc[chosen].iterrows())
    + "."
)

st.subheader("Price changes and volatility")
rows, fig = [], go.Figure()
for s in chosen:
    ser = allp[allp["series"] == s].set_index("period")["usd_per_tonne"].asfreq("MS")
    yoy = ser.pct_change(12, fill_method=None) * 100
    view = yoy[yoy.index.year >= since]
    fig.add_scatter(x=view.index, y=view, name=s)
    lr = np.log(ser).diff()
    sub = lr[lr.index.year >= since].dropna()
    rows.append(
        {
            "Series": s,
            "Latest month": ui.month_label(ser.dropna().index.max()),
            "Latest US$/t": ser.dropna().iloc[-1],
            "SD of monthly log change": sub.std(),
            "Max YoY %": view.max(),
            "Min YoY %": view.min(),
        }
    )
fig.add_hline(y=0, line_color="#aab4c0")
fig.update_yaxes(title="% vs same month last year")
st.plotly_chart(ui.style(fig, 320), width="stretch")
st.dataframe(
    pd.DataFrame(rows).style.format(
        {
            "Latest US$/t": "{:,.0f}",
            "SD of monthly log change": "{:.3f}",
            "Max YoY %": "{:+.1f}",
            "Min YoY %": "{:+.1f}",
        }
    ),
    hide_index=True,
    width="stretch",
)

st.subheader("Exploratory comparison with an export series")
ui.info(
    "Correlation describes co-movement over a short window. It does **not** show that prices drive exports (or the "
    "reverse): both respond to harvests, weather, policy and demand; the window is short and the series are "
    "autocorrelated."
)
cat = da.series_catalog(con)
exp_series = st.selectbox("Export series", cat["series_id"].tolist())
price_series = st.selectbox("Benchmark", series)
ex = da.monthly(con, exp_series)
ex = ex[ex["status"] == "reported"].set_index("period")["tonnes"].asfreq("MS")
px_ = allp[allp["series"] == price_series].set_index("period")["usd_per_tonne"].asfreq("MS")
basis = st.radio("Compare", ["12-month growth rates", "levels"], horizontal=True)
if basis == "12-month growth rates":
    a, b = px_.pct_change(12, fill_method=None) * 100, ex.pct_change(12, fill_method=None) * 100
else:
    a, b = px_, ex
lag = st.slider("Price leads exports by (months)", 0, 6, 0)
j = M.align_monthly(a.shift(lag, freq="MS"), b)
if len(j) < 12:
    st.warning(f"Only {len(j)} aligned months: too few for a correlation.")
else:
    pear, spear = j["a"].corr(j["b"]), j["a"].corr(j["b"], method="spearman")
    st.write(
        f"Aligned months: **{len(j)}** · Pearson **{pear:+.2f}** · Spearman **{spear:+.2f}** (lag {lag} months). "
        "Levels of trending, seasonal series can correlate spuriously; growth rates are shown by default."
    )
    fig = go.Figure(
        go.Scatter(
            x=j["a"],
            y=j["b"],
            mode="markers",
            marker=dict(color=ui.BLUE, size=8),
            text=j.index.strftime("%b %Y"),
            hovertemplate="%{text}<br>price %{x:.1f}, exports %{y:.1f}<extra></extra>",
        )
    )
    fig.update_xaxes(title="benchmark price (" + ("YoY %" if basis != "levels" else "US$/t") + ")")
    fig.update_yaxes(title="exports (" + ("YoY %" if basis != "levels" else "t") + ")")
    st.plotly_chart(ui.style(fig, 340, legend_below=False), width="stretch")
    with st.expander("Correlation at several lags (same basis)"):
        lc = M.lagged_correlations(a, b, lags=range(0, 7), min_pairs=12)
        st.dataframe(
            lc.rename(columns={"lag_months": "Price leads by (months)", "n": "Aligned months"}).round(3),
            hide_index=True,
        )

st.subheader("Export unit value (not a market price)")
unit_series = [s for s in cat["series_id"] if s.startswith("comtrade_")]
if unit_series:
    us = st.selectbox("Series with value and weight", unit_series, index=min(1, len(unit_series) - 1))
    w = da.monthly(con, us)
    w = w[(w["status"] == "reported") & w["fob_usd"].notna()].set_index("period")
    uv = M.unit_value(w["fob_usd"], w["tonnes"]).dropna()
    if len(uv):
        fig = go.Figure()
        fig.add_scatter(x=uv.index, y=uv, name=f"{us} export unit value (FOB US$/t)")
        bench = allp[allp["series"] == price_series].set_index("period")["usd_per_tonne"]
        bench = bench[bench.index >= uv.index.min()]
        fig.add_scatter(x=bench.index, y=bench, name=f"{price_series} (US$/t)", line=dict(dash="dot"))
        fig.update_yaxes(title="US$ per tonne")
        st.plotly_chart(ui.style(fig, 340), width="stretch")
        st.caption(
            "Unit value = reported FOB value / reported net weight in the same record, so it blends all grades and "
            "destinations. It is a customs average, not a quoted price, and can differ from benchmarks because of "
            "grade, contract timing and freight terms."
        )
    else:
        st.info("No value-and-weight records for this series.")
