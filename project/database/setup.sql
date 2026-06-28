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

-- Step 4b: Remove existing duplicates before enforcing uniqueness.
-- If the loader was run more than once, this keeps the most recent row id
-- for each indicator/date pair and removes older duplicates.
DELETE FROM observations old_row
USING observations new_row
WHERE old_row.indicator_id = new_row.indicator_id
  AND old_row.obs_date = new_row.obs_date
  AND old_row.id < new_row.id;

-- Step 4c: Prevent duplicate observations for the same indicator/date.
-- This supports repeatable ingestion: a later upload can update an existing
-- value instead of creating a duplicate time-series point.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_observation_indicator_date
ON observations(indicator_id, obs_date);

-- Step 5 & 6: Seed data_sources, indicators (122 rows) and observations
-- (12,100 rows) by running the loader script after this file:
--
--     python project/database/seed/load_seed.py
--
-- That script reads project/database/seed/*.csv -- a reproducible snapshot
-- of the live dataset -- and upserts everything, so it's always safe to
-- re-run. It replaces the old hand-written INSERT list that used to live
-- here, which only ever covered the original 5 indicators and had drifted
-- far out of sync with the live 122-indicator dataset.
