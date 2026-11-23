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

-- ============================================================
-- THE LEDGER -- append-only vintage archive.
--
-- observations (above) stays exactly as-is forever: it's the fast "current
-- value" table every existing read path already uses. This table is purely
-- additive. Every value ever written -- the original and every later
-- revision -- is kept here permanently, in the order it was recorded.
-- Nothing here is ever updated or deleted: see the GRANT/RLS lockdown below.
-- ============================================================

CREATE TABLE IF NOT EXISTS observation_vintages (
    id            BIGSERIAL PRIMARY KEY,
    indicator_id  VARCHAR(50) NOT NULL REFERENCES indicators(id),
    obs_date      DATE NOT NULL,
    value         DECIMAL(15, 4) NOT NULL,
    source        VARCHAR(20) NOT NULL,
    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_backfill   BOOLEAN NOT NULL DEFAULT FALSE,
    revision_note TEXT
);

-- No UNIQUE(indicator_id, obs_date): that constraint is exactly what forces
-- the overwrite behavior in `observations`. Every distinct value gets its
-- own row here, keyed by when it was recorded, not by date alone.
CREATE INDEX IF NOT EXISTS idx_vintage_indicator_date_recorded
  ON observation_vintages(indicator_id, obs_date, recorded_at);

-- Point-in-time read: "what did this series look like as of some past
-- moment." supabase-py's query builder can't express DISTINCT ON, so this
-- is exposed as an RPC function instead. Nothing calls this yet -- it's
-- part of the Ledger's own read contract, built now so the next entity
-- (the Rater) doesn't need another schema change later to use it.
CREATE OR REPLACE FUNCTION observations_as_of(p_indicator_id VARCHAR, p_as_of TIMESTAMPTZ)
RETURNS TABLE(obs_date DATE, value DECIMAL, recorded_at TIMESTAMPTZ) AS $BODY$
  SELECT DISTINCT ON (obs_date) obs_date, value, recorded_at
  FROM observation_vintages
  WHERE indicator_id = p_indicator_id AND recorded_at <= p_as_of
  ORDER BY obs_date, recorded_at DESC;
$BODY$ LANGUAGE sql STABLE;

-- Immutability: GRANT and RLS are two different layers, and both are needed.
-- GRANT controls which SQL commands a role may even attempt; RLS controls
-- which rows a permitted command may touch. Revoking UPDATE/DELETE outright
-- means those commands are rejected before RLS is even consulted -- and
-- there's deliberately no UPDATE/DELETE policy below either, so even if the
-- GRANT were ever loosened by mistake, no policy would permit the row.
--
-- Caveat (not solved here, by design -- out of scope for this plan): the
-- table owner and any BYPASSRLS role bypass RLS entirely. This app only
-- ever writes with the Supabase ANON key (see main.py's SUPABASE_KEY), so
-- this guarantee holds for the app's own write path. It would NOT hold if a
-- service-role key were ever introduced -- if that ever happens, this
-- comment is the reminder to revisit this lockdown.
-- TRUNCATE is revoked too: Postgres grants it by default alongside the other
-- table privileges, it is just as destructive as DELETE (wipes every row at
-- once), and it bypasses RLS entirely by design -- no policy could stop it
-- even if one existed. Found via live verification after the first deploy
-- of this table; REVOKE UPDATE, DELETE alone left this gap open.
ALTER TABLE observation_vintages ENABLE ROW LEVEL SECURITY;
REVOKE UPDATE, DELETE, TRUNCATE ON observation_vintages FROM anon, authenticated;
GRANT SELECT, INSERT ON observation_vintages TO anon, authenticated;

DROP POLICY IF EXISTS vintages_select ON observation_vintages;
DROP POLICY IF EXISTS vintages_insert ON observation_vintages;
CREATE POLICY vintages_select ON observation_vintages FOR SELECT USING (true);
CREATE POLICY vintages_insert ON observation_vintages FOR INSERT WITH CHECK (true);
-- No UPDATE or DELETE policy exists at all -- those commands are denied outright.

-- One-time backfill: every existing observations row becomes a vintage,
-- marked is_backfill = true since recorded_at here is only an approximation
-- (observations.created_at -- when the row was inserted into this DB, not
-- the indicator's true original publish date). Safe to re-run: it only
-- inserts rows for observations that don't already have a backfill vintage.
INSERT INTO observation_vintages (indicator_id, obs_date, value, source, recorded_at, is_backfill)
SELECT o.indicator_id, o.obs_date, o.value, o.source, o.created_at, true
FROM observations o
WHERE NOT EXISTS (
    SELECT 1 FROM observation_vintages v
    WHERE v.indicator_id = o.indicator_id
      AND v.obs_date = o.obs_date
      AND v.is_backfill = true
);
