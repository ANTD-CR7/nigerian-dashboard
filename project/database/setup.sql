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
-- DECIMAL(20, 4): wide enough for a raw-dollar macro figure (e.g. a
-- country's GDP in current US$, ~10^11-10^12) without overflowing --
-- DECIMAL(15, 4) only fit values under 10^11 and broke on Nigeria's own
-- GDP in current US$ (~4.5x10^11).
CREATE TABLE IF NOT EXISTS observations (
    id           SERIAL PRIMARY KEY,
    indicator_id VARCHAR(50) REFERENCES indicators(id),
    obs_date     DATE NOT NULL,
    value        DECIMAL(20, 4) NOT NULL,
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
    value         DECIMAL(20, 4) NOT NULL,
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
-- The service-role key is now this app's only write path (see the lockdown
-- section below) -- it bypasses RLS/GRANTs entirely by design, same as the
-- table owner, which this section's original caveat already anticipated.
-- TRUNCATE is revoked too: Postgres grants it by default alongside the other
-- table privileges, it is just as destructive as DELETE (wipes every row at
-- once), and it bypasses RLS entirely by design -- no policy could stop it
-- even if one existed. Found via live verification after the first deploy
-- of this table; REVOKE UPDATE, DELETE alone left this gap open.
ALTER TABLE observation_vintages ENABLE ROW LEVEL SECURITY;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON observation_vintages FROM anon, authenticated;
GRANT SELECT ON observation_vintages TO anon, authenticated;

DROP POLICY IF EXISTS vintages_select ON observation_vintages;
DROP POLICY IF EXISTS vintages_insert ON observation_vintages;  -- live on this table before this change (verified via pg_policies); must be dropped explicitly, not just left uncreated
CREATE POLICY vintages_select ON observation_vintages FOR SELECT USING (true);
-- No INSERT/UPDATE/DELETE policy exists at all for anon/authenticated --
-- those commands are denied outright. Writes come only from the
-- service-role key (collectors/runner.py, project/database/seed/load_seed.py,
-- main.py's store_observation()), which bypasses this layer entirely.

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

-- ============================================================
-- LOCKDOWN -- indicators, data_sources, observations (audit findings #1,
-- #2, #10, #107). These three tables never got the RLS/GRANT treatment
-- observation_vintages got above -- verified live via Supabase's Security
-- Advisor and pg_class/information_schema.role_table_grants: RLS was
-- disabled and anon held SELECT, INSERT, UPDATE, DELETE and TRUNCATE on
-- all three, unrestricted. anon becomes read-only here, same as vintages
-- above; all writes (collectors/runner.py, project/database/seed/
-- load_seed.py, main.py's store_observation()) move to a service-role key,
-- which bypasses this layer entirely by design.
-- ============================================================

ALTER TABLE indicators ENABLE ROW LEVEL SECURITY;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON indicators FROM anon, authenticated;
GRANT SELECT ON indicators TO anon, authenticated;
DROP POLICY IF EXISTS indicators_select ON indicators;
CREATE POLICY indicators_select ON indicators FOR SELECT USING (true);

ALTER TABLE data_sources ENABLE ROW LEVEL SECURITY;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON data_sources FROM anon, authenticated;
GRANT SELECT ON data_sources TO anon, authenticated;
DROP POLICY IF EXISTS data_sources_select ON data_sources;
CREATE POLICY data_sources_select ON data_sources FOR SELECT USING (true);

ALTER TABLE observations ENABLE ROW LEVEL SECURITY;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON observations FROM anon, authenticated;
GRANT SELECT ON observations TO anon, authenticated;
DROP POLICY IF EXISTS observations_select ON observations;
CREATE POLICY observations_select ON observations FOR SELECT USING (true);

-- Verification (run after applying, expect zero rows / rejected commands):
--   select relname, relrowsecurity from pg_class
--     where relname in ('indicators','data_sources','observations','observation_vintages');
--   -- all four should show relrowsecurity = true
--   select table_name, grantee, privilege_type from information_schema.role_table_grants
--     where table_schema = 'public' and grantee in ('anon','authenticated')
--     and table_name in ('indicators','data_sources','observations','observation_vintages');
--   -- only SELECT should appear per table/grantee

-- ============================================================
-- ROOT CAUSE -- this project's own schema-level default privileges, not
-- just these four tables' individual grants, are why this happened at all.
-- Verified live via pg_default_acl: Supabase's project template sets
-- ALTER DEFAULT PRIVILEGES for schema public granting anon/authenticated
-- the full arwdDxtm set (insert/select/update/delete/truncate/references/
-- trigger/maintain) on every TABLE created by the postgres or
-- supabase_admin role -- i.e. every table created in the ordinary way in
-- this project. This is almost certainly how indicators/data_sources/
-- observations ended up wide open above, and why observation_vintages
-- needed its own one-off manual lockdown after creation rather than being
-- safe by default. Without this, any future table (migrations, new
-- features) silently reopens the exact same hole on day one.
--
-- Narrows the *default* down to what every table above is already given
-- explicitly (SELECT only) -- this changes what new tables start with, not
-- any existing grant (those are handled per-table above).
--
-- Only FOR ROLE postgres, not supabase_admin: verified via pg_auth_members
-- that postgres (the role the Supabase SQL Editor connects as, and the one
-- that actually creates this project's own tables -- including every
-- CREATE TABLE in this file) is not a member of supabase_admin, so it has
-- no permission to alter that role's default privileges; the statement
-- would just fail. supabase_admin is Supabase's own internal platform
-- role, not the path this project's tables are created through, so that
-- default isn't this project's risk surface to fix.
-- ============================================================

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public
  REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON TABLES FROM anon, authenticated;

-- Verification (expect postgres's anon/authenticated entries to no longer
-- include INSERT/UPDATE/DELETE/TRUNCATE; supabase_admin's entry is
-- Supabase's own platform default and is expected to still show them):
--   select defaclrole::regrole, defaclacl from pg_default_acl
--     where defaclnamespace = 'public'::regnamespace and defaclobjtype = 'r';

-- ------------------------------------------------------------
-- Security Advisor WARN (function_search_path_mutable), found during the
-- same live audit as the RLS lockdown above: observations_as_of had no
-- search_path pinned. It's SECURITY INVOKER and read-only (a SELECT from
-- observation_vintages), so this was not an active write/RLS-bypass risk --
-- but an unpinned search_path is how a same-named object earlier in the
-- resolution order could hijack an unqualified reference inside a function,
-- so it's fixed here while touching this file for the same reason.
-- ------------------------------------------------------------
ALTER FUNCTION observations_as_of(VARCHAR, TIMESTAMPTZ) SET search_path = public, pg_temp;
