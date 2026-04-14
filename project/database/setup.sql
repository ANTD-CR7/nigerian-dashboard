-- ============================================================
-- FILE: database/setup.sql
-- PURPOSE: Create all tables for the Nigerian Financial Data
--          Aggregation System
-- RUN THIS: In Supabase SQL Editor, paste this and click Run
-- ============================================================

-- Step 1: Create the indicators table
-- This stores one row of info per economic indicator
CREATE TABLE IF NOT EXISTS indicators (
    id          VARCHAR(50) PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    unit        VARCHAR(100) NOT NULL,
    description TEXT,
    source      VARCHAR(20) NOT NULL
);

-- Step 2: Create the data_sources table
-- This stores info about each institution that publishes data
CREATE TABLE IF NOT EXISTS data_sources (
    code        VARCHAR(20) PRIMARY KEY,
    full_name   VARCHAR(200) NOT NULL,
    website     VARCHAR(200)
);

-- Step 3: Create the observations table
-- This is the main table - every single data point goes here
-- One row = one value for one indicator at one point in time
CREATE TABLE IF NOT EXISTS observations (
    id           SERIAL PRIMARY KEY,
    indicator_id VARCHAR(50) REFERENCES indicators(id),
    obs_date     DATE NOT NULL,
    value        DECIMAL(15, 4) NOT NULL,
    source       VARCHAR(20) NOT NULL,
    created_at   TIMESTAMP DEFAULT NOW()
);

-- Step 4: Create an index so date queries run fast
CREATE INDEX IF NOT EXISTS idx_indicator_date
ON observations(indicator_id, obs_date);

-- Step 5: Insert the data sources
INSERT INTO data_sources (code, full_name, website) VALUES
('CBN',  'Central Bank of Nigeria',          'https://www.cbn.gov.ng'),
('NBS',  'National Bureau of Statistics',    'https://nigerianstat.gov.ng'),
('WB',   'World Bank Open Data',             'https://data.worldbank.org')
ON CONFLICT (code) DO NOTHING;

-- Step 6: Insert the indicators
INSERT INTO indicators (id, name, unit, description, source) VALUES
('gdp_growth',    'GDP Growth Rate',         'Percent (%)',         'Real GDP growth rate at 2010 constant basic prices, published quarterly by the NBS',  'NBS'),
('gdp_usd',       'Nominal GDP (USD Bn)',    'USD Billions',        'Nominal GDP in current US Dollars, published annually by the World Bank',             'WB'),
('inflation',     'Headline Inflation Rate', 'Percent (%)',         'Year-on-year consumer price index change, published monthly by the NBS',              'NBS'),
('exchange_rate', 'Exchange Rate (NGN/USD)', 'Naira per USD',       'Official NGN/USD exchange rate, published daily by the CBN and averaged monthly',    'CBN'),
('mpr',           'Monetary Policy Rate',   'Percent (%)',         'CBN benchmark interest rate, set at bimonthly MPC meetings',                         'CBN')
ON CONFLICT (id) DO NOTHING;
