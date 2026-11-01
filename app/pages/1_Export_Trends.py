"""Export Trends: monthly and annual volume, growth, seasonality. Partial years are always labelled."""

import plotly.graph_objects as go
import streamlit as st

from rice_market import data_access as da
from rice_market import ui
from rice_market.analytics import metrics as M

ui.setup("Export Trends", "📈")
con = ui.con()
st.title("Export Trends")

cat = da.series_catalog(con)
if cat.empty:
    st.warning("No export series in the warehouse.")
    st.stop()
labels = dict(zip(cat["series_id"], cat["label"], strict=True))
sid = st.sidebar.selectbox("Series", cat["series_id"].tolist(), format_func=lambda s: f"{s}: {labels[s]}")
row = cat[cat["series_id"] == sid].iloc[0]
first = row["first_reported"].to_pydatetime()
last = row["last_reported"].to_pydatetime()
start = st.sidebar.date_input("Analysis start (month)", value=first, min_value=first, max_value=last)
st.sidebar.caption(
    "Choose the analysis window from your own coverage audit (Data Quality page). Nothing is excluded automatically."
)

if sid == "comtrade_1006":
    ui.caveat(
        "HS 1006 is the whole rice heading and **includes paddy** (HS 100610). It is not comparable with a milled-rice "
        "series; use the sub-heading series for like-for-like comparisons."
    )

df = da.monthly(con, sid)
df = df[df["period"] >= str(start)[:7] + "-01"]
rep = df[df["status"] == "reported"].copy()
if len(rep) < 2:
    st.warning("Fewer than two reported months in this window.")
    st.stop()
if (df["status"] == "missing").any():
    ui.info(
        f"{int((df['status'] == 'missing').sum())} month(s) in this window have no value; they are shown as gaps, not zero."
    )

g = M.add_growth(rep)
st.subheader("Monthly volume")
fig = go.Figure()
fig.add_bar(x=g["period"], y=g["tonnes"], name="Monthly tonnes", marker_color=ui.LIGHT_BLUE)
fig.add_scatter(
    x=g["period"], y=g["rolling_12m"], name="12-month average (full window only)", line=dict(color=ui.BLUE, width=3)
)
fig.add_scatter(
    x=g["period"], y=g["rolling_3m"], name="3-month average", line=dict(color=ui.ORANGE, width=1.5, dash="dot")
)
fig.update_yaxes(title="metric tons")
st.plotly_chart(ui.style(fig), width="stretch")

st.subheader("Annual totals")
ann = M.annual_summary(rep)
fig = go.Figure(
    go.Bar(
        x=ann["year"].astype(str),
        y=ann["total"],
        marker_color=[ui.BLUE if c else ui.LIGHT_BLUE for c in ann["is_complete"]],
        text=[f"{n}/12 months" if n < 12 else "" for n in ann["months_reported"]],
        textposition="outside",
        marker_pattern_shape=["" if c else "/" for c in ann["is_complete"]],
    )
)
fig.update_yaxes(title="metric tons (sum of reported months)")
st.plotly_chart(ui.style(fig, 340, legend_below=False), width="stretch")
partial = ann[~ann["is_complete"]]
if len(partial):
    st.caption("Hatched bars are partial years (fewer than 12 reported months) and are not comparable with full years.")
    y = int(partial.iloc[-1]["year"])
    lfl = M.like_for_like_yoy(rep, y)
    if lfl["comparable"]:
        st.write(
            f"Like-for-like ({len(lfl['months'])} month(s) of {y} vs the same months of {y - 1}): "
            f"**{lfl['change_pct']:+.1f}%**. Few months make this a noisy basis."
        )
full = ann[ann["is_complete"]].copy()
if len(full) > 1:
    full["yoy_pct"] = full["total"].pct_change() * 100
    st.dataframe(
        full[["year", "total", "yoy_pct"]]
        .rename(columns={"year": "Year", "total": "Tonnes", "yoy_pct": "Change vs prior year (%)"})
        .style.format({"Tonnes": "{:,.0f}", "Change vs prior year (%)": "{:+.1f}"}, na_rep="n/a"),
        hide_index=True,
        width="stretch",
    )

st.subheader("Growth")
c1, c2 = st.columns(2)
fig = go.Figure(
    go.Bar(x=g["period"], y=g["yoy_pct"], marker_color=[ui.BLUE if (v or 0) >= 0 else ui.ORANGE for v in g["yoy_pct"]])
)
fig.update_yaxes(title="% vs same month last year")
c1.plotly_chart(ui.style(fig, 300, legend_below=False).update_layout(title="Year-over-year"), width="stretch")
fig = go.Figure(go.Bar(x=g["period"], y=g["mom_pct"], marker_color=ui.LIGHT_BLUE))
fig.update_yaxes(title="% vs previous month")
c2.plotly_chart(ui.style(fig, 300, legend_below=False).update_layout(title="Month-over-month"), width="stretch")
vol = M.volatility(rep)
st.write(
    f"Coefficient of variation **{vol['cv']:.2f}**; standard deviation of month-to-month log changes "
    f"**{vol['log_change_sd']:.2f}** ({vol['n_changes']} changes)."
)

st.subheader("Seasonality")
rep2 = rep.assign(year=rep["period"].dt.year, month=rep["period"].dt.month)
fig = go.Figure()
for yr, grp in rep2.groupby("year"):
    fig.add_scatter(x=grp["month"], y=grp["tonnes"], mode="lines+markers", name=str(yr))
fig.update_xaxes(
    tickmode="array",
    tickvals=list(range(1, 13)),
    ticktext=["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
)
fig.update_yaxes(title="metric tons")
st.plotly_chart(ui.style(fig, 340), width="stretch")
prof = M.seasonal_profile(rep)
if len(prof):
    n_years = int(prof["n_years"].max())
    peak, trough = prof.loc[prof["index"].idxmax()], prof.loc[prof["index"].idxmin()]
    st.write(
        f"Seasonal index over {n_years} complete year(s) (1.00 = average month): highest in month **{int(peak['month'])}** "
        f"({peak['index']:.2f}), lowest in month **{int(trough['month'])}** ({trough['index']:.2f})."
    )
    if n_years < 4:
        ui.caveat(f"Only {n_years} complete annual cycle(s): the seasonal pattern is indicative, not established.")
else:
    ui.caveat("No complete calendar year in this window, so no seasonal profile is computed.")
