"""Chronological forecast evaluation: baselines, ETS, (S)ARIMA, error metrics and rolling-origin backtests.

Every model is a function (train: pd.Series with a monthly DatetimeIndex, h: int) -> np.ndarray of length h that sees
ONLY the training data. There is no random splitting anywhere in this module.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable

import numpy as np
import pandas as pd

SEASON = 12


# ---------------------------------------------------------------- metrics
def mae(actual, forecast) -> float:
    a, f = np.asarray(actual, float), np.asarray(forecast, float)
    return float(np.mean(np.abs(a - f)))


def rmse(actual, forecast) -> float:
    a, f = np.asarray(actual, float), np.asarray(forecast, float)
    return float(np.sqrt(np.mean((a - f) ** 2)))


def smape(actual, forecast) -> float:
    """Symmetric MAPE in percent (0-200 scale). Terms with a zero denominator are skipped."""
    a, f = np.asarray(actual, float), np.asarray(forecast, float)
    den = np.abs(a) + np.abs(f)
    ok = den > 0
    return float(np.mean(2 * np.abs(a - f)[ok] / den[ok]) * 100) if ok.any() else float("nan")


# ---------------------------------------------------------------- origins
def expanding_origins(n: int, min_train: int, horizon: int, step: int = 1) -> list[int]:
    """Training-set sizes (the forecast origins). Each origin t forecasts positions t .. t+horizon-1 from y[:t]."""
    return list(range(min_train, n - horizon + 1, step))


# ---------------------------------------------------------------- models
def naive(train: pd.Series, h: int) -> np.ndarray:
    return np.repeat(float(train.iloc[-1]), h)


def seasonal_naive(train: pd.Series, h: int) -> np.ndarray:
    if len(train) < SEASON:
        raise ValueError("seasonal naive needs at least one full season")
    last = train.iloc[-SEASON:].to_numpy(float)
    return np.array([last[i % SEASON] for i in range(h)])


def mean_model(train: pd.Series, h: int) -> np.ndarray:
    return np.repeat(float(train.mean()), h)


def ets_simple(train: pd.Series, h: int) -> np.ndarray:
    from statsmodels.tsa.holtwinters import SimpleExpSmoothing

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = SimpleExpSmoothing(train.to_numpy(float), initialization_method="estimated").fit()
        return np.asarray(fit.forecast(h), float)


def ets_seasonal(train: pd.Series, h: int) -> np.ndarray:
    """Additive-seasonal Holt-Winters without trend. Needs at least two full seasons to be estimable."""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    if len(train) < 2 * SEASON:
        raise ValueError("seasonal ETS needs at least two full seasons")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = ExponentialSmoothing(
            train.to_numpy(float),
            trend=None,
            seasonal="add",
            seasonal_periods=SEASON,
            initialization_method="estimated",
        ).fit()
        return np.asarray(fit.forecast(h), float)


def arima_110(train: pd.Series, h: int) -> np.ndarray:
    from statsmodels.tsa.arima.model import ARIMA

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return np.asarray(ARIMA(train.to_numpy(float), order=(1, 1, 0)).fit().forecast(h), float)


def sarima_100_010(train: pd.Series, h: int) -> np.ndarray:
    """SARIMA(1,0,0)(0,1,0)_12: seasonal differencing plus one AR term. Fixed specification (no search)."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    if len(train) < SEASON + 8:
        raise ValueError("SARIMA needs more than one season of history")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        fit = SARIMAX(
            train.to_numpy(float),
            order=(1, 0, 0),
            seasonal_order=(0, 1, 0, SEASON),
            enforce_stationarity=False,
            enforce_invertibility=False,
        ).fit(disp=False)
        return np.asarray(fit.forecast(h), float)


MODELS: dict[str, Callable[[pd.Series, int], np.ndarray]] = {
    "naive": naive,
    "seasonal_naive": seasonal_naive,
    "mean": mean_model,
    "ets_simple": ets_simple,
    "ets_seasonal": ets_seasonal,
    "arima_110": arima_110,
    "sarima_100_010": sarima_100_010,
}


# ---------------------------------------------------------------- backtest
def rolling_origin(
    y: pd.Series, models: dict[str, Callable] | None = None, horizon: int = 6, min_train: int = 24, step: int = 1
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Expanding-window backtest. Returns (forecasts, skipped).

    forecasts: one row per model x origin x step-ahead. skipped: model/origin pairs a model could not run
    (reported, never silently dropped).
    y must be continuous monthly with no NaN; the caller decides how gaps are treated.
    """
    if y.isna().any():
        raise ValueError("series contains missing values; evaluate on a gap-free span")
    models = models or MODELS
    rows, skipped = [], []
    for t in expanding_origins(len(y), min_train, horizon, step):
        train, test = y.iloc[:t], y.iloc[t : t + horizon]
        for name, fn in models.items():
            try:
                pred = fn(train, horizon)
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"[:120]
                skipped.append({"model": name, "origin": y.index[t - 1], "reason": reason})
                continue
            for k in range(horizon):
                rows.append(
                    {
                        "model": name,
                        "origin": y.index[t - 1],
                        "train_size": t,
                        "step": k + 1,
                        "target_period": test.index[k],
                        "actual": float(test.iloc[k]),
                        "forecast": float(pred[k]),
                    }
                )
    return pd.DataFrame(rows), pd.DataFrame(skipped, columns=["model", "origin", "reason"])


def summarise(fc: pd.DataFrame, horizons: tuple[int, ...] = (1, 3, 6)) -> pd.DataFrame:
    """Error metrics per model and forecast horizon, plus MAE relative to the seasonal-naive and naive baselines.

    Models are compared on the (origin, step) cells that EVERY model produced, so a model that fails at some origins
    is not flattered by an easier subset.
    """
    if fc.empty:
        return pd.DataFrame()
    n_models = fc["model"].nunique()
    cnt = fc.groupby(["origin", "step"])["model"].transform("nunique")
    common = fc[cnt == n_models]
    rows = []
    for h in horizons:
        d = common[common["step"] == h]
        for m, g in d.groupby("model"):
            rows.append(
                {
                    "horizon": h,
                    "model": m,
                    "n": len(g),
                    "mae": mae(g.actual, g.forecast),
                    "rmse": rmse(g.actual, g.forecast),
                    "smape": smape(g.actual, g.forecast),
                }
            )
    out = pd.DataFrame(rows)
    for base in ("naive", "seasonal_naive"):
        ref = out[out["model"] == base].set_index("horizon")["mae"]
        out[f"mae_vs_{base}"] = out["mae"] / out["horizon"].map(ref)
    return out.sort_values(["horizon", "mae"]).reset_index(drop=True)
