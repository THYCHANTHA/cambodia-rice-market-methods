# Release scope: methods and code only

This repository is a **methods-and-code release**. It is not a publication of the analytical findings of the author's
private research project, and it is not a data release.

## Included

| Area | Files |
|---|---|
| Python source: parsing, validation, analytics, forecasting backtests, data access, UI helpers | `src/rice_market/` |
| DuckDB schema and SQL | `sql/schema.sql` |
| Data parsing and validation functions | `src/rice_market/transformation/`, `src/rice_market/validation/` |
| Market analytics calculations (growth, seasonality, shares, HHI, unit value, correlations) | `src/rice_market/analytics/metrics.py` |
| Forecast backtesting infrastructure and evaluation settings (no results) | `src/rice_market/forecasting/`, `configs/experiments.yaml` |
| **Manual MEF import** and validation interface | `src/rice_market/ingestion/manual_import.py`, `scripts/import_mef.py` |
| **Optional** connectors (Comtrade with opt-in and call budget; Pink Sheet and Comtrade code lists) | `src/rice_market/ingestion/{comtrade,sources,http}.py`, `scripts/fetch_comtrade.py`, `scripts/fetch_optional_sources.py` |
| Dashboard source (7 pages) containing no real figures or findings | `app/`, `.streamlit/config.toml` |
| Synthetic demonstration-data generator and its labelled output script | `src/rice_market/demo.py`, `scripts/make_demo.py` |
| Synthetic test fixtures and tests (the fixtures say they are synthetic) | `tests/` |
| Setup, methodology, provenance and licence documentation | `README.md`, `docs/` |
| `.env.example` (empty template), `.gitignore`, `pyproject.toml`, `requirements.txt`, `LICENSE` (MIT, code only) | repository root |

## Excluded (and enforced by tests where possible)

| Excluded | How it is kept out |
|---|---|
| Cached or downloaded MEF files, Comtrade API responses, Pink Sheet workbooks, any source-data export, log or cache | `data/` is git-ignored; `test_no_source_data_results_or_images_tracked` |
| Actual monthly MEF values or any real export value in code, documents or tests | Scrub verification (see DATA_LICENSE_AUDIT.md, section 6); tests use invented values in fictional years |
| Market-share, HHI, growth, seasonality or volume **findings** about real data | Not written anywhere; the dashboard computes only from the loaded warehouse; `test_dashboard_source_contains_no_hardcoded_market_findings` |
| Forecast results and model metrics from real data | `reports/` is git-ignored; the experiment record is written under `reports/local/` only when you run it |
| Research screenshots and dashboard screenshots | No image files are tracked (tested) |
| Derived result tables built from restricted or unconfirmed datasets | None shipped; the report script of the private project is not included |
| **Automated MEF / Data EF website downloader**, dataset identifiers and endpoint URLs | Removed; `test_no_automated_mef_retrieval_in_tracked_files` |
| Hosted or deployed dashboards | Not deployed; the app is configured for localhost only |
| Private project history | This repository starts from a single fresh commit; the private repository's history was not rewritten and is not included |
| Permission-request drafts and the private audit working notes | Remain in the private project |

## What is deliberately different from the private project

1. MEF data are imported from local files; there is no downloader.
2. The Comtrade connector requires `--accept-comtrade-terms`, has a per-run call budget and is not part of the default pipeline.
3. Forecast evaluation spans are detected or configured instead of fixed in code; roles (primary / exploratory) come from the number
   of annual cycles, not from results.
4. The dashboard has three states: empty (no data), synthetic demonstration, or your own warehouse.
5. Documents describe methods and terms only; findings, quoted values and screenshots are removed.
