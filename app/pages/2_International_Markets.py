"""International Markets: destination shares and concentration from partner-level rows, plus a mirror comparison."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rice_market import config, ui
from rice_market import data_access as da
from rice_market.analytics import metrics as M

ui.setup("International Markets", "🌏")
con = ui.con()
st.title("International Markets")
ui.caveat(
    "Destinations come from partner-level rows of the reporting country's own trade data. Residual categories such as "
    "'nes' (not elsewhere specified) are counted as single destinations, which affects shares and HHI. Check how many "
    "months each year has before reading a year as a full-year mix."
)

codes = [r[0] for r in con.execute("SELECT DISTINCT cmd_code FROM fct_partner_monthly ORDER BY 1").fetchall()]
if not codes:
    st.warning("No partner-level data in the warehouse. Load trade data that contains partner rows (see README).")
    st.stop()
cmd = st.sidebar.selectbox("Product (HS code)", codes, format_func=lambda c: f"{c}: {config.HS_RICE.get(c, c)}")
bounds = con.execute("SELECT min(period), max(period) FROM fct_partner_monthly WHERE cmd_code = ?", [cmd]).fetchone()
first_year, last_year = bounds[0].year, bounds[1].year
y_lo, y_hi = st.sidebar.slider("Years", first_year, last_year, (first_year, last_year))
p = da.partners(con, cmd, f"{y_lo}-01-01", f"{y_hi}-12-01")
p["year"] = p["period"].dt.year
p["partner"] = p["partner_name"].fillna(p["partner_code"].astype(str))
months = p.groupby("year")["period"].nunique()
if (months < 12).any():
    ui.caveat("Months with partner records per year: " + ", ".join(f"{y}: {n}" for y, n in months.items()) + ".")
st.sidebar.caption("Choose the window from your coverage audit; partner coverage can differ strongly between years.")

yearly = p.groupby(["year", "partner"], as_index=False)["net_wgt_t"].sum()
years = sorted(yearly["year"].unique())
top_n = st.sidebar.slider("Top destinations shown", 3, 12, 8)
sel_year = st.sidebar.selectbox("Year for detail", years, index=len(years) - 1)

st.subheader(f"Destination mix by year (top {top_n} of {sel_year}, rest grouped)")
top = M.shares(yearly[yearly["year"] == sel_year], "partner", "net_wgt_t").head(top_n)["partner"].tolist()
yearly["group"] = yearly["partner"].where(yearly["partner"].isin(top), "All other")
mix = yearly.groupby(["year", "group"], as_index=False)["net_wgt_t"].sum()
mix["share"] = mix["net_wgt_t"] / mix.groupby("year")["net_wgt_t"].transform("sum") * 100
fig = go.Figure()
for i, grp in enumerate([*top, "All other"]):
    d = mix[mix["group"] == grp]
    fig.add_bar(
        x=d["year"].astype(str),
        y=d["share"],
        name=grp,
        marker_color="#c9d3df" if grp == "All other" else ui.PALETTE[i % 8],
    )
fig.update_layout(barmode="stack")
fig.update_yaxes(title="share of tonnage (%)")
st.plotly_chart(ui.style(fig, 400), width="stretch")

st.subheader("Market concentration (HHI)")
rows = []
for y in years:
    s = M.shares(yearly[yearly["year"] == y], "partner", "net_wgt_t")
    rows.append(
        {
            "year": y,
            "partners": len(s),
            "top1": s["partner"].iloc[0],
            "top1_share": s["share"].iloc[0] * 100,
            "top5_share": s["share"].head(5).sum() * 100,
            "hhi": M.hhi(s["share"].to_numpy()),
        }
    )
conc = pd.DataFrame(rows)
fig = go.Figure(go.Scatter(x=conc["year"], y=conc["hhi"], mode="lines+markers", line=dict(color=ui.BLUE, width=3)))
fig.update_yaxes(title="HHI (0-10,000)", rangemode="tozero")
fig.update_xaxes(dtick=1)
c1, c2 = st.columns([3, 2])
c1.plotly_chart(ui.style(fig, 320, legend_below=False), width="stretch")
c2.dataframe(
    conc.rename(
        columns={
            "year": "Year",
            "partners": "Partners",
            "top1": "Largest",
            "top1_share": "Top-1 %",
            "top5_share": "Top-5 %",
            "hhi": "HHI",
        }
    ).style.format({"Top-1 %": "{:.1f}", "Top-5 %": "{:.1f}", "HHI": "{:,.0f}"}),
    hide_index=True,
    width="stretch",
)
st.caption(
    "HHI = sum of squared shares x 10,000, over reported partner rows. A common (US antitrust) reading: under 1,500 "
    "unconcentrated, 1,500-2,500 moderate, above 2,500 high; it depends on how partners are defined."
)

if len(years) > 1:
    st.subheader("Destination changes between two years")
    a, b = st.columns(2)
    y0 = a.selectbox("From", years, index=0)
    y1 = b.selectbox("To", years, index=len(years) - 1)
    x0 = yearly[yearly["year"] == y0].set_index("partner")["net_wgt_t"]
    x1 = yearly[yearly["year"] == y1].set_index("partner")["net_wgt_t"]
    cmp_ = pd.concat([x0.rename("t0"), x1.rename("t1")], axis=1).fillna(0.0)
    cmp_["share0"] = cmp_["t0"] / cmp_["t0"].sum() * 100
    cmp_["share1"] = cmp_["t1"] / cmp_["t1"].sum() * 100
    cmp_["change_pp"] = cmp_["share1"] - cmp_["share0"]
    new = cmp_[(cmp_["t0"] == 0) & (cmp_["t1"] > 0)]
    gone = cmp_[(cmp_["t0"] > 0) & (cmp_["t1"] == 0)]
    col1, col2 = st.columns(2)
    for col, title, asc in ((col1, "Largest share gains", False), (col2, "Largest share losses", True)):
        col.markdown(f"**{title}** ({y0} to {y1})")
        col.dataframe(
            cmp_.sort_values("change_pp", ascending=asc)
            .head(6)[["share0", "share1", "change_pp"]]
            .rename(columns={"share0": f"{y0} %", "share1": f"{y1} %", "change_pp": "pp change"})
            .round(2),
            width="stretch",
        )
    st.write(
        f"Destinations with no records in {y0} but some in {y1}: **{len(new)}**. Present in {y0} and absent in {y1}: "
        f"**{len(gone)}**. An absent record means no reported trade, which can be a real stop or non-reporting."
    )

st.subheader("Mirror statistics (importers' own reports)")
mir = da.mirror(con, cmd)
if mir.empty:
    st.info(
        "No mirror data loaded. Mirror data are partners' reports of their imports from the exporter (optional connector)."
    )
else:
    mir["year"] = mir["period"].dt.year
    mm = mir[mir["year"] == sel_year].groupby("reporter_name", as_index=False)["net_wgt_t"].sum()
    mm_months = mir[mir["year"] == sel_year]["period"].nunique()
    mine = yearly[yearly["year"] == sel_year][["partner", "net_wgt_t"]].rename(
        columns={"net_wgt_t": "exporter_reported_t"}
    )
    j = mine.merge(
        mm.rename(columns={"reporter_name": "partner", "net_wgt_t": "importer_reported_t"}), on="partner", how="inner"
    )
    j["importer / exporter"] = j["importer_reported_t"] / j["exporter_reported_t"]
    j = j.sort_values("exporter_reported_t", ascending=False).head(12)
    st.dataframe(
        j.style.format(
            {"exporter_reported_t": "{:,.0f}", "importer_reported_t": "{:,.0f}", "importer / exporter": "{:.2f}"}
        ),
        hide_index=True,
        width="stretch",
    )
    st.caption(
        f"{sel_year}: exporter-reported tonnage against what partners report importing ({mm_months} month(s) of mirror "
        "data). Differences are expected: exports are valued FOB and imports CIF, shipment and arrival months differ, "
        "goods can be re-routed or recorded under another country of origin or consignment, partners may not report "
        "every month, and quantity definitions can differ. A ratio far from 1 flags something to investigate, not an "
        "error in either source."
    )
