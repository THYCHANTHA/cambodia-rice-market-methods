-- Analytical warehouse (DuckDB). Every table states its grain; primary keys are enforced.
-- Source values are never overwritten: raw_* tables keep what each source said, fct_* tables are standardised views.

CREATE TABLE dim_series (
    series_id          VARCHAR PRIMARY KEY,   -- grain: one row per published series
    source             VARCHAR NOT NULL,
    label              VARCHAR NOT NULL,
    product_definition VARCHAR NOT NULL,      -- what the series actually measures
    unit               VARCHAR NOT NULL,
    flow               VARCHAR NOT NULL
);

CREATE TABLE raw_mef_monthly (                -- grain: file x month, exactly as published (blank stays NULL)
    dataset VARCHAR NOT NULL,
    period  DATE    NOT NULL,
    tonnes  DOUBLE,
    status  VARCHAR NOT NULL CHECK (status IN ('reported', 'missing')),
    PRIMARY KEY (dataset, period)
);

CREATE TABLE raw_mef_annual (                 -- grain: file x year ("Yearly Export" row as published)
    dataset          VARCHAR NOT NULL,
    year             INTEGER NOT NULL,
    reported_total_t DOUBLE,
    PRIMARY KEY (dataset, year)
);

CREATE TABLE fct_export_monthly (             -- grain: series x month; missing months are rows with status 'missing'
    series_id VARCHAR NOT NULL REFERENCES dim_series (series_id),
    period    DATE    NOT NULL,
    tonnes    DOUBLE CHECK (tonnes IS NULL OR tonnes >= 0),
    fob_usd   DOUBLE,
    status    VARCHAR NOT NULL CHECK (status IN ('reported', 'missing')),
    PRIMARY KEY (series_id, period)
);

CREATE TABLE fct_export_annual (              -- grain: series x calendar year
    series_id       VARCHAR NOT NULL REFERENCES dim_series (series_id),
    year            INTEGER NOT NULL,
    tonnes          DOUBLE,                   -- sum of REPORTED months only
    months_reported INTEGER NOT NULL,
    is_complete     BOOLEAN NOT NULL,         -- TRUE only when all 12 months are reported
    PRIMARY KEY (series_id, year)
);

CREATE TABLE fct_partner_monthly (            -- grain: month x HS code x destination (Cambodia as reporter, exports)
    period    DATE    NOT NULL,
    cmd_code  VARCHAR NOT NULL,
    partner_code INTEGER NOT NULL,
    partner_name VARCHAR,
    iso3      VARCHAR,
    is_group  BOOLEAN,
    net_wgt_t DOUBLE CHECK (net_wgt_t IS NULL OR net_wgt_t >= 0),
    fob_usd   DOUBLE,
    PRIMARY KEY (period, cmd_code, partner_code)
);

CREATE TABLE fct_mirror_monthly (             -- grain: month x HS code x importing country (partner-reported imports from Cambodia)
    period    DATE    NOT NULL,
    cmd_code  VARCHAR NOT NULL,
    reporter_code INTEGER NOT NULL,
    reporter_name VARCHAR,
    net_wgt_t DOUBLE,
    cif_usd   DOUBLE,
    PRIMARY KEY (period, cmd_code, reporter_code)
);

CREATE TABLE fct_price_monthly (              -- grain: benchmark series x month; blanks are NULL (never interpolated)
    period         DATE    NOT NULL,
    series         VARCHAR NOT NULL,
    usd_per_tonne  DOUBLE,
    PRIMARY KEY (period, series)
);

CREATE TABLE dq_issue (                       -- grain: one detected issue
    check_name VARCHAR NOT NULL,
    severity   VARCHAR NOT NULL,
    dataset    VARCHAR NOT NULL,
    detail     VARCHAR NOT NULL,
    decision   VARCHAR NOT NULL
);

CREATE TABLE dq_reconciliation (              -- grain: one comparison between two statements of the same quantity
    kind     VARCHAR NOT NULL,
    key      VARCHAR NOT NULL,
    a_label  VARCHAR NOT NULL,
    a_value  DOUBLE,
    b_label  VARCHAR NOT NULL,
    b_value  DOUBLE,
    diff     DOUBLE,
    rel_diff DOUBLE,
    agrees   BOOLEAN
);

CREATE TABLE forecast_backtest (              -- grain: series x model x origin x step
    series_id VARCHAR NOT NULL,
    model VARCHAR NOT NULL,
    origin DATE NOT NULL,
    train_size INTEGER NOT NULL,
    step INTEGER NOT NULL,
    target_period DATE NOT NULL,
    actual DOUBLE NOT NULL,
    forecast DOUBLE NOT NULL,
    PRIMARY KEY (series_id, model, origin, step)
);

CREATE TABLE forecast_summary (               -- grain: series x horizon x model
    series_id VARCHAR NOT NULL,
    horizon INTEGER NOT NULL,
    model VARCHAR NOT NULL,
    n INTEGER NOT NULL,
    mae DOUBLE, rmse DOUBLE, smape DOUBLE,
    mae_vs_naive DOUBLE, mae_vs_seasonal_naive DOUBLE,
    PRIMARY KEY (series_id, horizon, model)
);

CREATE TABLE src_snapshot (                   -- grain: one downloaded file (latest retrieval per local path)
    source        VARCHAR NOT NULL,
    path          VARCHAR PRIMARY KEY,
    url           VARCHAR NOT NULL,
    retrieved_utc VARCHAR NOT NULL,
    sha256        VARCHAR NOT NULL,
    bytes         BIGINT  NOT NULL
);

CREATE TABLE forecast_series (                -- grain: one evaluated series per run (span chosen by the experiment)
    series_id     VARCHAR PRIMARY KEY,
    start_period  DATE NOT NULL,
    end_period    DATE NOT NULL,
    n_months      INTEGER NOT NULL,
    annual_cycles DOUBLE NOT NULL,
    role          VARCHAR NOT NULL,           -- 'primary' (>= 4 annual cycles) or 'exploratory'
    span_source   VARCHAR NOT NULL            -- 'detected' (longest gap-free run) or 'configured'
);
