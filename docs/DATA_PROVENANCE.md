# Data provenance and licensing

This repository ships **no data**. This page says where data come from when *you* load them, how each is recorded, and what
attribution to use. Licence position and evidence: [DATA_LICENSE_AUDIT.md](DATA_LICENSE_AUDIT.md). The MIT licence covers
the code only.

## Sources

| Source | How this toolkit obtains it | Terms status | Attribution |
|---|---|---|---|
| **Cambodia Data EF / Ministry of Economy and Finance** (Secretariat One Window Service rice-export statistics, metric tons per month) | **Manual import only**: you download the CSV files from the portal and run `scripts/import_mef.py`. There is no downloader | The portal's Terms of Use permit use "for commercial or non-commercial purposes" with attribution; they name no licence and no redistribution conditions, and prohibit "data mining" of the site. Written clarification has **not** been obtained | "Source: Secretariat One Window Service, via Data EF (data.mef.gov.kh)" |
| **UN Comtrade** (monthly trade by HS code and partner; mirror imports) | **Optional connector** (`scripts/fetch_comtrade.py`), explicit `--accept-comtrade-terms`, sequential and budget-limited; free preview endpoint without a key, or an optional key from your environment | Use is subject to the UN Comtrade licence agreement and policy on use and re-dissemination (read 2026-11-01; see the audit). Written clarification has **not** been obtained | "Source: UN Comtrade" |
| **World Bank Commodity Price Data (The Pink Sheet)**, monthly workbook | **Optional download** (`scripts/fetch_optional_sources.py --pink-sheet`) | World Bank datasets default to CC BY 4.0; the workbook contains no licence text and credits third-party quotation sources | "World Bank Commodity Price Data (The Pink Sheet). Rice quotations are credited in the file to Bloomberg Finance L.P., the US Department of Agriculture and the World Bank. Selected series were charted and growth rates and volatility were calculated by the author; the data were modified. The World Bank has not endorsed this use." |

Replace "the author" with yourself if you publish your own outputs.

## Records kept for every file that enters `data/raw`

`data/manifests/downloads.jsonl` (git-ignored): source, URL or `local-file:<name>`, UTC retrieval time, SHA-256, size and a
note. A manually imported MEF file is recorded with the note "imported manually by the user; no network access". The
warehouse copies the latest record per file into `src_snapshot`, which the Data Quality page can display.

## Definitions the code relies on (public classifications, not data)

HS (Harmonized System) codes handled: **1006** rice (heading total); **100610** rice in the husk (paddy or rough); **100620**
husked (brown) rice; **100630** semi-milled or wholly milled rice; **100640** broken rice. HS 1006 therefore includes paddy.
Comtrade rows carry the HS revision in which they were originally reported; the code records revisions found in your data but
does not map between revisions.

Pink Sheet rice columns parsed (units `$/mt`, nominal US dollars): "Rice, Thai 5% ", "Rice, Thai 25% ", "Rice, Thai A.1",
"Rice, Viet Namese 5%". The workbook describes them as free-on-board export price indications for Thailand and Viet Nam. They
are **not** prices of any other country, and spreadsheet error cells (such as `#VALUE!`) are stored as missing and logged.

## Reproducing a build

```
python scripts/import_mef.py <your MEF csv files>                   # optional
python scripts/fetch_optional_sources.py --pink-sheet               # optional
python scripts/fetch_comtrade.py --accept-comtrade-terms ...        # optional
python scripts/run_pipeline.py
```

Providers can revise published figures; two builds made at different times may differ. Compare the checksums in
`src_snapshot`.
