"""Product composition by HS sub-heading. Categories are never converted into each other."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rice_market import config, ui
from rice_market import data_access as da

ui.setup("Product Composition", "🍚")
con = ui.con()
st.title("Rice Product Composition")
ui.info(
    "Categories follow the HS sub-headings: **100610** rice in the husk (paddy), **100620** husked (brown), "
    "**100630** semi-/wholly milled, **100640** broken. Weights are as reported (net weight); paddy tonnes are "
    "**not** converted to milled-rice equivalent, so shares by weight overstate paddy relative to milled output."
)
ui.caveat(
    "Paddy (HS 100610) is **hidden by default**: it is the category most likely to be reported inconsistently between "
    "exporter and importers, so check the mirror comparison at the bottom of this page before interpreting it."
)
include_paddy = st.sidebar.checkbox("Show paddy (HS 100610)", value=False)

w = da.world_by_code(con, "1900-01-01")
w = w[w["series_id"] != "comtrade_1006"].copy()
if w.empty:
    st.warning("No product-level series in the warehouse. Load trade data with HS sub-headings (see README).")
    st.stop()
w["code"] = w["series_id"].str.replace("comtrade_", "", regex=False)
w["year"] = w["period"].dt.year
names = {"100610": "Paddy", "100620": "Husked (brown)", "100630": "Milled", "100640": "Broken"}
shown = [c for c in ["100630", "100620", "100640"] + (["100610"] if include_paddy else []) if c in set(w["code"])]

st.subheader("Monthly volume by category")
fig = go.Figure()
for i, code in enumerate(shown):
    d = w[(w["code"] == code) & (w["status"] == "reported")]
    fig.add_bar(x=d["period"], y=d["tonnes"], name=names[code], marker_color=ui.PALETTE[i])
fig.update_layout(barmode="stack")
fig.update_yaxes(title="metric tons")
st.plotly_chart(ui.style(fig, 400), width="stretch")

st.subheader("Composition by calendar year (share of weight of the categories shown)")
yr = w[(w["status"] == "reported") & w["code"].isin(shown)].groupby(["year", "code"], as_index=False)["tonnes"].sum()
yr["share"] = yr["tonnes"] / yr.groupby("year")["tonnes"].transform("sum") * 100
fig = go.Figure()
for i, code in enumerate(shown):
    d = yr[yr["code"] == code]
    fig.add_bar(x=d["year"].astype(str), y=d["share"], name=names[code], marker_color=ui.PALETTE[i])
fig.update_layout(barmode="stack")
fig.update_yaxes(title="% of weight")
st.plotly_chart(ui.style(fig, 340), width="stretch")
tab = yr.pivot(index="year", columns="code", values="tonnes").rename(columns=names).fillna(0.0)
st.dataframe(tab.style.format("{:,.0f}"), width="stretch")
st.caption("Tonnes by calendar year; a zero here can mean 'not reported that year', see the month counts below.")

st.subheader("Reported months per category")
rep_months = w[w["status"] == "reported"].groupby(["year", "code"])["tonnes"].count().unstack(fill_value=0)
st.dataframe(rep_months.rename(columns=names), width="stretch")
st.caption(
    "A category with fewer than 12 months in a year was absent from the other months. Absence is 'not reported', not zero."
)

chk = da.reconciliation(con, "hs_children_vs_heading")
st.write(
    f"Consistency check: months in which the four sub-headings do not sum to the HS 1006 total (>0.1%): **{len(chk)}**."
)
if len(chk):
    st.dataframe(pd.DataFrame(chk), width="stretch")

st.subheader("Paddy (HS 100610): exporter's report vs importers' reports")
mir = da.mirror(con, "100610")
cam = w[(w["code"] == "100610") & (w["status"] == "reported")].groupby("year")["tonnes"].sum()
if mir.empty and cam.empty:
    st.info("No paddy records on either side in this warehouse.")
else:
    mir["year"] = mir["period"].dt.year
    imp = mir.groupby("year")["net_wgt_t"].sum()
    mon = mir.groupby("year")["period"].nunique()
    cmp_ = pd.DataFrame(
        {"Exporter reports (t)": cam, "Importers report (t)": imp, "Months with importer records": mon}
    ).reindex(sorted(set(cam.index) | set(imp.index)))
    st.dataframe(cmp_.style.format("{:,.0f}", na_rep="n/a"), width="stretch")
    one_sided = [
        int(y) for y, r in cmp_.iterrows() if pd.isna(r["Exporter reports (t)"]) != pd.isna(r["Importers report (t)"])
    ]
    if one_sided:
        st.write("Years in which only one side has a record: " + ", ".join(str(y) for y in one_sided) + ".")
    ui.caveat(
        "Where the two sides disagree by large factors, or only one side has a record, the paddy tonnage is "
        "**unreconciled**: do not read it as growth or decline in paddy exports without investigating the reporting."
    )
st.caption(f"HS codes handled: {', '.join(config.HS_RICE)}.")
