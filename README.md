# Cambodia Rice Market Methods

**Open methods and code for analysing rice export statistics: ingestion, validation, reconciliation, market analytics and
forecast evaluation.**

> **This is a methods-and-code release, not a publication of the analytical findings.**
> It contains no source data, no research results, no screenshots and no real export figures. Everything the dashboard shows
> comes from **synthetic demonstration data** (clearly labelled) or from data **you** load yourself under each provider's
> terms. The author's own results are unpublished pending written clarification from the data providers.
> The project is independent and **not endorsed by** the Cambodian Government, the Ministry of Economy and Finance /
> Data EF, the Cambodia Rice Federation, the United Nations / UN Comtrade or the World Bank Group.
> Status: research pre-release, not a production application.

## What it does

| Layer | What the code does |
|---|---|
| Ingestion | **Manual import** of MEF / Data EF CSV files (validated, no network); **optional** connectors for UN Comtrade (explicit opt-in, call budget) and the World Bank Pink Sheet workbook |
| Transformation | Strict parsers (units, thousands separators refused, blanks stay missing), a DuckDB warehouse with explicit grains and primary-key / CHECK constraints (`sql/schema.sql`) |
| Validation | Duplicate, gap, negative-value, annual-total, overlap, partner-sum, HS-children and mirror-statistics checks; every disagreement is recorded, nothing is silently overwritten |
| Analytics | Growth rates, rolling means, seasonal index, partial-year handling, destination shares, HHI, export unit value, lagged correlations (exploratory) |
| Forecast evaluation | Expanding-window rolling-origin backtests of naive, seasonal naive, mean, ETS, ARIMA and SARIMA baselines; MAE / RMSE / sMAPE; a paired bootstrap against the seasonal-naive baseline. **No forward forecasts** |
| Dashboard | A 7-page Streamlit app (localhost only) that shows a clear **empty state** when no data exist, **synthetic demo data** when you ask for them, or your own warehouse |

Not included, by design: any cached provider data, any numeric result about real rice exports, forecasts or model metrics,
screenshots of real data, hosted deployments, and any **automated retrieval from the MEF / Data EF website**
(see [docs/RELEASE_LIMITATIONS.md](docs/RELEASE_LIMITATIONS.md)). Full list: [docs/RELEASE_SCOPE.md](docs/RELEASE_SCOPE.md).

## Quick start (no data needed)

```
python -m venv .venv && .venv/Scripts/activate        # Windows; use bin/activate elsewhere
pip install -r requirements.txt && pip install -e . --no-deps
python scripts/make_demo.py                            # writes SYNTHETIC files under data/demo and builds a demo warehouse
streamlit run app/Home.py                              # every page carries a "SYNTHETIC DEMONSTRATION DATA" banner
pytest && ruff check .
```

Without any warehouse the app shows **"No data available"** and instructions; it never substitutes invented numbers by itself.

## Using your own data

1. **MEF / Data EF files:** download the CSV files yourself from the portal under its terms of use, then
   `python scripts/import_mef.py file1.csv file2.csv`. Each file is validated first; if any is refused nothing is copied.
2. **UN Comtrade (optional):** read the provider's terms, then
   `python scripts/fetch_comtrade.py --accept-comtrade-terms --view exports --start YYYYMM --end YYYYMM --max-calls 60`.
   The connector is sequential, paused, cached, budget-limited and stops cleanly if the provider's quota is used up. It works
   without a key (free preview endpoint); an optional key can be set in the environment (see `.env.example`), never in code.
3. **World Bank Pink Sheet (optional):** `python scripts/fetch_optional_sources.py --pink-sheet --comtrade-reference`.
4. Build and evaluate: `python scripts/run_pipeline.py`, then `streamlit run app/Home.py`.
   Evaluation settings (series, spans, horizons) are in `configs/experiments.yaml`; by default each series' longest gap-free
   run of reported months is used, and you should choose spans from your own coverage audit.

Outputs you create from provider data are subject to those providers' terms; check them before you publish anything.

## Data sources and licences

The **code** is MIT-licensed ([LICENSE](LICENSE)). **No dataset is covered by that licence** and none is included.

| Source | Attribution to use if you load it | Terms status (details: [docs/DATA_LICENSE_AUDIT.md](docs/DATA_LICENSE_AUDIT.md)) |
|---|---|---|
| UN Comtrade | "Source: UN Comtrade" | Subject to the UN Comtrade licence and policy on use and re-dissemination; derived indicators are addressed by its FAQ, original figures are restricted. Written clarification of this project's use has **not** been obtained |
| Cambodia Data EF / MEF (Secretariat One Window Service) | "Source: Secretariat One Window Service, via Data EF (data.mef.gov.kh)" | Terms allow use with attribution but name no licence and no redistribution conditions; **automated retrieval is disabled** until the publisher confirms in writing |
| World Bank Commodity Price Data (The Pink Sheet) | "World Bank Commodity Price Data (The Pink Sheet); rice quotations credited in the file to Bloomberg Finance L.P., the US Department of Agriculture and the World Bank. Series were selected, charted and re-calculated by the user; the World Bank has not endorsed this use." | World Bank datasets default to CC BY 4.0; the workbook carries no licence text and credits third-party quotation sources, so reliance on CC BY 4.0 is limited |

## Layout

`src/rice_market/{ingestion,transformation,validation,analytics,forecasting}` · `sql/schema.sql` · `app/` · `scripts/` ·
`configs/` · `tests/` (synthetic fixtures only) · `docs/`. Table grains and keys: [docs/DATA_DICTIONARY.md](docs/DATA_DICTIONARY.md).
Methods: [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Tests and hygiene

`pytest` runs on synthetic data only and includes release gates over the tracked files: no data, results, images or JSON;
no raw Comtrade fields; no local paths, secrets or e-mail addresses; an empty `.env.example`; no MEF downloader; attribution
and scope statements present. The dashboard source is also checked for hard-coded findings.

## Limitations

See [docs/RELEASE_LIMITATIONS.md](docs/RELEASE_LIMITATIONS.md). In short: no data, no findings, no projections; the connectors
depend on third-party services and terms that can change; GitHub Actions has not been run for this repository; Python 3.11,
other operating systems and narrow (mobile) layouts are untested.
