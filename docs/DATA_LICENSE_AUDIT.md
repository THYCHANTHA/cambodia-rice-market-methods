# Data licence audit (methods-and-code release)

Audit date: 2026-11-01. Scope: the contents of this repository, the three sources the code can read, and the providers'
published terms. **This is a documentation audit by the author, not legal advice.** Where a provider's text is silent or
ambiguous this document says so. Written clarification from the Ministry of Economy and Finance / Data EF and from UN
Comtrade has **not** been obtained; that is why this release excludes results, screenshots and quoted values.

## 1. Position by source

| Source | What the repository contains | Position |
|---|---|---|
| UN Comtrade | A **connector** (opt-in, call-budgeted) and **parsers**; no records, no API responses, no figures | Code only; nothing redistributed. Users decide whether and how to use the API under the provider's terms |
| Cambodia Data EF / MEF | A **manual-import validator** and **parser**; no files, no dataset identifiers, no endpoint; no downloader | The terms prohibit "data mining" of the site and name no redistribution conditions, so automated retrieval is disabled |
| World Bank Pink Sheet | A parser and an optional download of the public workbook; no workbook | Attribution and a modification statement are specified; CC BY 4.0 is relied on only for the World Bank compilation |

## 2. UN Comtrade: documents read and what they say

Read on 2026-11-01: the Help Center *Policy on Comtrade Data Use*, *FAQs on Use and Re-dissemination* and *Read Me First
(Disclaimer)*, plus the legacy licence page. Not readable with the tooling used: the Comtrade+ Terms of Use and the older
policy PDF.

- Policy: Comtrade data "are provided for internal use only and may not be re-disseminated in any form" without UNSD's
  permission, with a limited-amount exemption; citation: "UN Comtrade". Use is "subject to a license agreement ... regardless
  of whether the data is accessed via free or premium access".
- FAQ Q1 lists uses needing no permission, including "Publication of limited amounts of UN Comtrade data in a few tables,
  graphs, visualization" and "Free-of-charge data visualization and/or data analytics application".
- FAQ Q4 lists as **transformed**: "Creating new indicators, indices, or analytical measures", "Producing geographic, sectoral,
  or other aggregations", and "Performing calculations that generate new analytical outputs, such as growth rates, market
  shares, or derived metrics". **Not** transformed: rounding, changing format or structure ("pivoting, sorting, filtering, or
  reformatting tables"), renaming variables, converting file formats. FAQ Q8 and Q10: "UN Comtrade does not copyright
  transformed data".
- FAQ Q5: a "limited amount" is "a database containing fewer than 100,000 records in total".
- Disclaimer: imports reported by one country "do not coincide with exports reported by its trading partner"; Comtrade "does not
  contain estimates for missing data".
- The legacy licence agreement (dated 2012) states internal use only; no document read reconciles it with the FAQ.

**Consequence for this release.** It contains no Comtrade records, graphs of Comtrade figures, quoted values or derived
results, so the FAQ's re-dissemination rules are not engaged by the repository itself. The analytics (shares, HHI, growth
rates) are the kinds of calculation the FAQ lists as transformed data, which is why the *methods* are released; whether
a user's *outputs* are covered depends on what they publish. The FAQ does not address publishing code that calls the API.

### Connector review (fair use)

| Behaviour | Implementation |
|---|---|
| Explicit opt-in | `--accept-comtrade-terms` is required; not part of the default pipeline |
| Request rate | Strictly sequential; a pause of about 3.6 s after each download; exponential back-off on HTTP 429 and 5xx |
| Call budget | `--max-calls` (default 60 per run); the run stops and can be resumed later |
| Quota | A 403 "quota" response stops the run with a clear message; there is no retry loop and no attempt to circumvent limits |
| Caching | A month already stored is never requested again; absent months are recorded as facts |
| Identification | The User-Agent is generic by default and can be set with `RICE_MARKET_USER_AGENT` |
| Key handling | An optional key is read from `COMTRADE_API_KEY` and sent as a request header; it is never stored, logged or committed (`.env.example` is empty) |
| Transport | TLS verification is never disabled |
| Scope | One reporter, rice codes only, monthly; no bulk or record-level export feature |

## 3. World Bank Pink Sheet

- The workbook contains no licence or citation text (every sheet was searched). Its source notes credit Bloomberg Finance
  L.P., the US Department of Agriculture and the World Bank for the rice series.
- The World Bank Data Catalog states CC BY 4.0 as the default licence "for all Datasets produced by the World Bank itself" and
  that other datasets carry other, labelled licences. A catalogue record for the commodity price data lists "Creative
  Commons Attribution 4.0" but does not name the Pink Sheet or mention third-party sources.
- The World Bank's terms page forbids implying World Bank endorsement and notes that other parties may own rights in some
  material.
- **Decision.** The attribution and modification statement in `DATA_PROVENANCE.md` is used; CC BY 4.0 is not assumed to transfer
  rights in third-party quotations; the workbook is not committed; the dashboard states that benchmark quotations are not
  exporter prices.

## 4. Cambodia Data EF / MEF

- Terms of Use (read 2026-11-01): users can use the content "for commercial or non-commercial purposes"; "Any use of data ...
  must include an attribution or reference to the data's source"; published data "is protected by the intellectual property
  laws of the Kingdom of Cambodia"; no licence is named; no redistribution conditions are given; "data mining" or abnormal
  activity on the site is prohibited; content is "for informational purposes only".
- Public access is not treated as permission to redistribute.
- **Decision.** No downloader, endpoint, dataset identifier or sample file is included. The repository offers a local-file import
  with a strict validator. Automated retrieval, results, charts of the series and quoted values stay out of the release until
  the publisher confirms in writing what is permitted.

## 5. Inventory of what the repository contains

| Category | Classification |
|---|---|
| Source code and SQL | Original work (MIT) |
| Documentation | Original work; quotes of provider terms are short and attributed |
| Tests and fixtures | Invented values in fictional years (2030 onward), labelled synthetic |
| Demonstration generator | Invented numbers from a seeded random generator; partner names and exporter code are fictional |
| Configuration (`configs/experiments.yaml`) | Settings only |
| Data, results, images, JSON, caches | **None** (enforced by `tests/test_repo_hygiene.py`) |

## 6. Verification performed before this release

| Check | Method |
|---|---|
| No source data, caches or results tracked | `git ls-files` scan for data extensions, `data/`, `reports/`, images and JSON; automated test |
| No real value in code, tests or documents | Every monthly and annual figure held in the author's private warehouse (MEF, Comtrade world level, partner and mirror totals) was searched, in plain and thousands-separated form, across all tracked files and across the whole Git history of this repository; the result is recorded in the release report. The scan lists are not stored here because they would themselves be the values |
| No finding phrases | Denylist of finding wording and period labels searched across tracked files and history |
| No MEF endpoint or identifiers | Pattern scan and automated test |
| No credentials, e-mail addresses or local paths | Pattern scans and automated test |
| Fresh history | Single initial commit; the private repository's history was not rewritten or included |

## 7. Outstanding

- Written clarification from MEF / Data EF and from UN Comtrade (activities and outputs described in the private project's
  drafted requests). Until received: no results, quoted values, screenshots or hosted dashboard.
- The Comtrade+ Terms of Use and the exact Pink Sheet licence page were not readable; they should be read in a browser.
- Terms can change; re-read them before relying on this audit.
