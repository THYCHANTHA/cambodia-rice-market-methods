# Methodology

This document describes the **methods** implemented in the code. It states no result about any real dataset.

## Pipeline

user-supplied or optionally downloaded raw files (`data/raw`, kept unchanged, hashed) → parsers
(`src/rice_market/transformation`) → DuckDB warehouse (`sql/schema.sql`, primary keys and CHECK constraints) →
checks and reconciliation (`src/rice_market/validation`) → analytics (`analytics/metrics.py`) → forecast evaluation
(`forecasting/`) → Streamlit app (`app/`). DuckDB is used because the data are small, single-user and read-only at serving time.
Any source may be absent: the build runs with whatever exists and records the absence.

## Grains and keys

| Table | Grain | Primary key |
|---|---|---|
| `raw_mef_monthly` | file × month, exactly as parsed (blank = NULL) | (dataset, period) |
| `raw_mef_annual` | file × year (a file's own "Yearly Export" total) | (dataset, year) |
| `fct_export_monthly` | series × month; missing months are rows with `status = 'missing'` | (series_id, period) |
| `fct_export_annual` | series × calendar year | (series_id, year) |
| `fct_partner_monthly` | month × HS code × destination | (period, cmd_code, partner_code) |
| `fct_mirror_monthly` | month × HS code × importing country | (period, cmd_code, reporter_code) |
| `fct_price_monthly` | benchmark series × month | (period, series) |
| `dq_issue`, `dq_reconciliation`, `src_snapshot`, `forecast_*` | see [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | |

## Rules applied

1. **Units.** MEF-style values are plain numbers of metric tons; a value containing a thousands separator is refused by the parser,
   not guessed. Comtrade net weight is kilograms and is divided by 1,000. Converting units, renaming columns and re-keying months
   are standardisation, not transformation.
2. **Missing is not zero.** Blank cells, months or codes with no record, and spreadsheet error cells become NULL or
   `status = 'missing'`. Nothing is interpolated or forward-filled.
3. **No merging of sources.** Each publisher's series keeps its own id (for example `sows_mef`, `comtrade_<HS>`). Series are compared in
   `dq_reconciliation` and plotted side by side, never spliced.
4. **Overlapping MEF files.** Files are compared month by month. A month is reported if any file reports it; if files disagree
   beyond 0.5 t, the narrower file (covering fewer months) is used and the disagreement is logged.
5. **Partial years.** A year is complete only when all 12 months are reported. Annual sums use reported months only; charts hatch
   partial years; `like_for_like_yoy` compares only the same months in both years.
6. **Growth.** Month-over-month and year-over-year changes exist only where both months are reported and exactly 1 or 12 months
   apart. Rolling means need a full window.
7. **Seasonal index.** Mean of each calendar month divided by the mean of complete years only.
8. **Concentration.** Shares = partner tonnage / total partner tonnage in the year; HHI = sum of squared shares × 10,000.
9. **Unit value.** Value / net weight from the same record, labelled "export unit value", never "price".
10. **Benchmark comparison.** Aligned on common months only; growth-rate comparison by default; exploratory, no causal reading.

## Reconciliation tests (stored in `dq_reconciliation` and `dq_issue`)

- MEF file overlap and each file's "Yearly Export" total against the sum of its months (tolerance 0.5 t).
- Comtrade partner rows against the world row, and HS 1006 against the sum of its four children (tolerance 0.1 %).
- An MEF-style series against alternative Comtrade definitions over their common months (5 % agreement band).
- Mirror statistics: importers' reports against the exporter's report (a diagnostic; differences are expected and explained
  in the app).

## Forecast evaluation design

- **Series and span:** configured in `configs/experiments.yaml`, or detected as the longest gap-free run of reported months. Choose
  spans from your own coverage audit, not from forecast results. A series is labelled *primary* only if it has at least four
  complete annual cycles, otherwise *exploratory*.
- **Protocol:** expanding-window rolling origin; minimum training window and horizons from the settings file. A model receives only
  observations up to the origin (a test shows that changing future values does not change earlier forecasts).
- **Models (fixed specifications, no search):** naive; seasonal naive (lag 12); mean of the training window; simple exponential
  smoothing; additive Holt-Winters without trend (needs at least 24 observations); ARIMA(1,1,0); SARIMA(1,0,0)(0,1,0)₁₂ (statsmodels).
- **Metrics:** MAE, RMSE, sMAPE (0-200 scale) and MAE relative to the naive and seasonal-naive baselines, on origin × step cells that
  every model produced.
- **Uncertainty:** paired origin bootstrap of the MAE difference against seasonal naive (2,000 resamples, fixed seed). It resamples
  origins independently and ignores serial dependence, so intervals are optimistic.
- **Not done:** machine-learning models, prediction intervals and forward forecasts. Backtests describe past fit, not future
  accuracy.

## Tests

Software tests use invented values only (`tests/conftest.py`, `src/rice_market/demo.py`). They cover parsing, unit handling, duplicate and
gap detection, annual reconciliation, shares, HHI, price alignment, forecast splits, baselines, metrics, manual import,
connector budgets, absent sources, dashboard states and release hygiene.
