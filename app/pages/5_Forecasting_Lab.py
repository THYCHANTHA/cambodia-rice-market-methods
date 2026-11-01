"""Forecasting Lab: rolling-origin backtests of baselines, ETS and SARIMA. No forward forecast is produced."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from rice_market import data_access as da
from rice_market import ui
from rice_market.forecasting import experiment as E

ui.setup("Forecasting Lab", "🔬")
con = ui.con()
st.title("Forecasting Lab")
ui.info(
    "Chronological **rolling-origin** evaluation: at each origin a model sees only earlier months, forecasts the next "
    "months, then the window expands. There is no random splitting. Every model is scored on the same origins. "
    "These are **backtests on past data, not forecasts of the future**."
)

fs = da.forecast_series(con)
if fs.empty:
    st.warning(
        "No forecast results in the warehouse. Run `python scripts/run_forecast_experiment.py` (settings: configs/experiments.yaml)."
    )
    st.stop()
sid = st.sidebar.selectbox("Series", fs["series_id"].tolist())
spec = fs[fs["series_id"] == sid].iloc[0]
summ = da.forecast_summary(con, sid)
horizons = sorted(int(h) for h in summ["horizon"].unique())
horizon = st.sidebar.radio("Forecast horizon (months ahead)", horizons, horizontal=True)

if spec["role"] == "exploratory":
    ui.caveat(
        f"Only {spec['annual_cycles']:.1f} annual cycles ({int(spec['n_months'])} months): below the four-cycle guideline, so "
        "differences between models are anecdotal."
    )
else:
    ui.info(
        f"{spec['annual_cycles']:.1f} annual cycles ({int(spec['n_months'])} months) meet the four-cycle guideline."
    )
n_orig = int(summ[summ["horizon"] == horizon]["n"].max())
st.write(
    f"Evaluated span **{spec['start_period']:%Y-%m} to {spec['end_period']:%Y-%m}** ({spec['span_source']}), "
    f"**{n_orig}** forecast origins at this horizon."
)

d = summ[summ["horizon"] == horizon].sort_values("mae")
fig = go.Figure(
    go.Bar(
        x=d["mae"],
        y=d["model"],
        orientation="h",
        marker_color=[ui.BLUE if m not in ("naive", "seasonal_naive", "mean") else ui.LIGHT_BLUE for m in d["model"]],
        text=[f"{v:,.0f}" for v in d["mae"]],
        textposition="outside",
    )
)
fig.update_layout(yaxis=dict(autorange="reversed"))
fig.update_xaxes(title="MAE (tonnes), lower is better")
st.plotly_chart(
    ui.style(fig, 330, legend_below=False).update_layout(title=f"{horizon}-month-ahead error"), width="stretch"
)
st.dataframe(
    d[["model", "mae", "rmse", "smape", "mae_vs_naive", "mae_vs_seasonal_naive"]]
    .rename(
        columns={
            "mae": "MAE",
            "rmse": "RMSE",
            "smape": "sMAPE %",
            "mae_vs_naive": "MAE / naive",
            "mae_vs_seasonal_naive": "MAE / seasonal naive",
        }
    )
    .style.format(
        {
            "MAE": "{:,.0f}",
            "RMSE": "{:,.0f}",
            "sMAPE %": "{:.1f}",
            "MAE / naive": "{:.2f}",
            "MAE / seasonal naive": "{:.2f}",
        }
    ),
    hide_index=True,
    width="stretch",
)
st.caption(
    "Light bars are baselines. Ratios below 1.00 mean lower error than that baseline. 'ets_seasonal' = additive Holt-Winters "
    "without trend; 'sarima_100_010' = SARIMA(1,0,0)(0,1,0)12; 'arima_110' = non-seasonal ARIMA(1,1,0). Specifications are fixed "
    "in advance, not searched."
)

st.subheader("Is a model's difference from the seasonal-naive baseline distinguishable from noise?")
bt = con.execute("SELECT model, origin, step, actual, forecast FROM forecast_backtest WHERE series_id = ?", [sid]).df()
rows = []
for m in sorted(set(bt["model"]) - {"seasonal_naive"}):
    r = E.paired_origin_bootstrap(bt, m, "seasonal_naive", horizon)
    rows.append(
        {
            "model": m,
            "origins": r["n"],
            "mean MAE difference (t)": r["mean_diff"],
            "95% interval low": r["lo"],
            "95% interval high": r["hi"],
            "interval excludes 0": bool(r["lo"] > 0 or r["hi"] < 0),
        }
    )
st.dataframe(
    pd.DataFrame(rows).style.format(
        {"mean MAE difference (t)": "{:+,.0f}", "95% interval low": "{:+,.0f}", "95% interval high": "{:+,.0f}"}
    ),
    hide_index=True,
    width="stretch",
)
st.caption(
    "Difference = model error minus seasonal-naive error (negative = model better). The interval resamples forecast origins "
    "independently, ignoring serial dependence, so it is optimistic: an interval that includes zero means the model is not "
    "distinguishable from the baseline, and one that excludes zero is only suggestive."
)

st.subheader("Backtest: actual vs forecast")
models = sorted(set(bt["model"]))
model = st.selectbox("Model", models, index=models.index("ets_seasonal") if "ets_seasonal" in models else 0)
b = da.forecast_backtest(con, sid, model, horizon)
base = da.forecast_backtest(con, sid, "seasonal_naive", horizon)
fig = go.Figure()
fig.add_scatter(x=b["target_period"], y=b["actual"], name="Actual", line=dict(color=ui.INK, width=2))
fig.add_scatter(x=b["target_period"], y=b["forecast"], name=model, line=dict(color=ui.BLUE, width=2))
fig.add_scatter(
    x=base["target_period"], y=base["forecast"], name="seasonal_naive", line=dict(color=ui.ORANGE, dash="dot")
)
fig.update_yaxes(title="metric tons")
st.plotly_chart(ui.style(fig, 360), width="stretch")
st.caption(
    f"Each point is a forecast made {horizon} month(s) before its target month, using only data up to that origin."
)

st.subheader("Scope")
st.markdown(
    "- **No prediction intervals and no forward forecast are produced.** Interval coverage cannot be validated on a short "
    "history, and a projection would ignore any regime change.\n"
    "- Machine-learning models are not included: they need a justified feature set and enough observations.\n"
    "- A model that beats a baseline in a short backtest is not shown to be useful; compare with the interval table above."
)
