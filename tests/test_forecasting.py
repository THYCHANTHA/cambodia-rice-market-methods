"""Forecast split, baseline and metric tests (synthetic data)."""

import numpy as np
import pandas as pd
import pytest

from rice_market.forecasting import evaluation as F


def series(n=48, seasonal=True):
    idx = pd.date_range("2030-01-01", periods=n, freq="MS")
    base = 100 + (np.tile(np.arange(12) * 5.0, n // 12 + 1)[:n] if seasonal else 0)
    return pd.Series(base, index=idx)


def test_metrics_known_values():
    assert F.mae([1, 2, 3], [2, 2, 5]) == pytest.approx(1.0)
    assert F.rmse([0, 0], [3, 4]) == pytest.approx(np.sqrt(12.5))
    assert F.smape([100], [50]) == pytest.approx(2 * 50 / 150 * 100)
    assert F.smape([0, 10], [0, 10]) == 0.0  # zero/zero terms skipped, not NaN-poisoning


def test_origins_are_chronological_and_leave_room_for_horizon():
    o = F.expanding_origins(30, min_train=20, horizon=6, step=1)
    assert o[0] == 20 and o[-1] == 24
    assert F.expanding_origins(10, 20, 3) == []


def test_naive_and_seasonal_naive():
    y = series(24)
    assert (F.naive(y, 3) == y.iloc[-1]).all()
    sn = F.seasonal_naive(y, 14)
    assert sn[0] == y.iloc[-12] and sn[12] == y.iloc[-12]  # wraps after one season
    with pytest.raises(ValueError):
        F.seasonal_naive(y.iloc[:5], 3)


def test_perfectly_seasonal_series_is_forecast_exactly_by_seasonal_naive():
    y = series(48)
    fc, _ = F.rolling_origin(y, {"seasonal_naive": F.seasonal_naive}, horizon=3, min_train=24)
    assert F.mae(fc.actual, fc.forecast) == pytest.approx(0.0)


def test_no_lookahead_models_only_see_training_data():
    y = series(36, seasonal=False)
    seen = []

    def spy(train, h):
        seen.append((train.index[-1], len(train)))
        return np.repeat(train.iloc[-1], h)

    fc, _ = F.rolling_origin(y, {"spy": spy}, horizon=2, min_train=24)
    # every forecast target lies strictly after its origin
    assert (fc["target_period"] > fc["origin"]).all()
    # the model was shown exactly the observations up to the origin
    for origin, size in seen:
        assert y.index.get_loc(origin) + 1 == size


def test_changing_the_future_does_not_change_past_forecasts():
    y = series(40)
    y2 = y.copy()
    y2.iloc[-3:] = 9999.0
    a, _ = F.rolling_origin(y, {"n": F.naive}, horizon=1, min_train=24)
    b, _ = F.rolling_origin(y2, {"n": F.naive}, horizon=1, min_train=24)
    early = a["origin"] < y.index[-4]
    assert np.allclose(a.loc[early, "forecast"], b.loc[early, "forecast"])


def test_rolling_origin_refuses_missing_values_and_reports_skips():
    y = series(30)
    y.iloc[5] = np.nan
    with pytest.raises(ValueError):
        F.rolling_origin(y, {"n": F.naive}, horizon=1, min_train=12)
    fc, skipped = F.rolling_origin(series(30), {"ets_seasonal": F.ets_seasonal}, horizon=1, min_train=12)
    # origins with fewer than two seasons (train sizes 12..23) are skipped and reported; from 24 the model runs
    assert len(skipped) == 12
    assert fc["train_size"].min() == 24


def test_summary_compares_models_on_common_cells():
    y = series(40) + np.random.default_rng(0).normal(0, 1, 40)
    fc, _ = F.rolling_origin(y, {"naive": F.naive, "seasonal_naive": F.seasonal_naive}, horizon=3, min_train=24)
    s = F.summarise(fc, horizons=(1, 3))
    assert set(s["model"]) == {"naive", "seasonal_naive"}
    assert (s[s["model"] == "naive"]["mae_vs_naive"] == 1.0).all()
    assert (
        s.loc[(s.model == "seasonal_naive") & (s.horizon == 1), "mae"].item()
        < s.loc[(s.model == "naive") & (s.horizon == 1), "mae"].item()
    )


def test_statistical_models_run_on_enough_data():
    y = series(40) + np.random.default_rng(1).normal(0, 2, 40)
    for name in ("ets_simple", "ets_seasonal", "arima_110", "sarima_100_010"):
        pred = F.MODELS[name](y, 3)
        assert len(pred) == 3 and np.isfinite(pred).all()
