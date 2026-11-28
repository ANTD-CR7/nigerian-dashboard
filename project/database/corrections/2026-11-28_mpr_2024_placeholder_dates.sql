-- Correction: 6 "mpr" (CBN Monetary Policy Rate) rows for 2024 are stored
-- under a placeholder "first of month" obs_date instead of the real CBN
-- MPC meeting date. The rate VALUES themselves are correct -- only the
-- dates are wrong. Found during the Phase 0/1 audit (not an original
-- AUDIT_FINDINGS.md item).
--
-- NOT APPLIED by this script being present in the repo. Per CLAUDE.md
-- Hard Rule #1, no agent write/update ran against the live database --
-- this is a reviewable script for a human to run in the Supabase SQL
-- Editor after checking the citations below.
--
-- Convention check: the 6 "mpr" rows already in the DB for 2025
-- (2025-02-19, 2025-03-25, 2025-05-20, 2025-07-22, 2025-09-23,
-- 2025-11-19) store the FIRST day of each 2-day MPC meeting as obs_date
-- (e.g. the 299th meeting, "February 19-20, 2025", is stored as
-- 2025-02-19). The corrections below follow that same existing
-- first-day-of-meeting convention for consistency.
--
-- Sources (CBN's own communiques/filenames, cross-checked against a CBN
-- decisions-page summary and independent news coverage of the Nov 2024
-- meeting; MPR values below match what is already stored -- verified,
-- not re-guessed):
--   293rd meeting, 26-27 Feb 2024, MPR -> 22.75%  (CBN/MPC/COM/150/293)
--     https://www.cbn.gov.ng/FeaturedArticles/2024/articles/MPC_Feb2024.asp
--   294th meeting, 25-26 Mar 2024, MPR -> 24.75%  (CBN/MPC/COM/151/294)
--     https://www.cbn.gov.ng/Out/2024/CCD/UPDATE%20DDG%20EP%20MPC%20Communique%20No.%20151%20March%202024.pdf
--     https://www.cbn.gov.ng/Out/2024/CCD/Notice%20of%20the%20294th%20Meeting%20of%20the%20Monetary%20Policy%20Committee.pdf
--   295th meeting, 20-21 May 2024, MPR -> 26.25%  (Communique No. 152)
--     https://www.cbn.gov.ng/Out/2024/CCD/MPC%20Communique%20No.%20152%20of%20the%20MPC%20May%2021%202024%20.pdf
--   296th meeting, 22-23 Jul 2024, MPR -> 26.75%  (Communique No. 153,
--     "held on Tuesday, 23rd July, 2024")
--     https://cbn.gov.ng/Out/2024/CCD/Central%20Bank%20of%20Nigeria%20Communique%20No.153%20of%20the%20296th%20Meeting%20of%20Monetary%20Policy%20Committee%20held%20on%20Tuesday,%2023rd%20July,%202024.pdf
--   297th meeting, 23-24 Sep 2024, MPR -> 27.25%  (Communique No. 154,
--     dated "September 24 2024")
--     https://cbn.gov.ng/Out/2024/CCD/FINAL%20MPC%20Communique%20No.%20154%20September%2024%202024%20.pdf
--   298th meeting, 25-26 Nov 2024, MPR -> 27.50%  (Communique No. 155,
--     CBN/MPC/COM/155/298, dated "November 26 2024")
--     https://www.cbn.gov.ng/Out/2024/CCD/FINAL%20MPC%20Communique%20No.%20155%20November%2026%202024%2015.08pm.pdf
--
-- Pre-flight checks run (read-only) before writing this script:
--   * No "mpr" row already exists at any of the 6 corrected dates
--     (verified via SELECT ... WHERE obs_date IN (...) -> 0 rows).
--   * observations has no UNIQUE constraint on (indicator_id, obs_date),
--     only a PRIMARY KEY on id and a FOREIGN KEY on indicator_id -- so
--     this UPDATE cannot collide with an existing row.
--   * The 6 values below (22.75, 24.75, 26.25, 26.75, 27.25, 27.50)
--     already match what is stored under the wrong dates -- this
--     corrects obs_date only, not value.

BEGIN;

UPDATE observations
   SET obs_date = '2024-02-26'
 WHERE indicator_id = 'mpr' AND obs_date = '2024-02-01' AND value = 22.75;

UPDATE observations
   SET obs_date = '2024-03-25'
 WHERE indicator_id = 'mpr' AND obs_date = '2024-03-01' AND value = 24.75;

UPDATE observations
   SET obs_date = '2024-05-20'
 WHERE indicator_id = 'mpr' AND obs_date = '2024-05-01' AND value = 26.25;

UPDATE observations
   SET obs_date = '2024-07-22'
 WHERE indicator_id = 'mpr' AND obs_date = '2024-07-01' AND value = 26.75;

UPDATE observations
   SET obs_date = '2024-09-23'
 WHERE indicator_id = 'mpr' AND obs_date = '2024-09-01' AND value = 27.25;

UPDATE observations
   SET obs_date = '2024-11-25'
 WHERE indicator_id = 'mpr' AND obs_date = '2024-11-01' AND value = 27.50;

-- observation_vintages is append-only by design (never UPDATE/DELETE it --
-- see project/database/setup.sql's LOCKDOWN section). Record the
-- correction as a new vintage row per date, citing the source, rather
-- than rewriting history.
INSERT INTO observation_vintages (indicator_id, obs_date, value, source, is_backfill, revision_note) VALUES
  ('mpr', '2024-02-26', 22.75, 'CBN', true, 'Corrected obs_date from placeholder 2024-02-01 to real 293rd MPC meeting date (26-27 Feb 2024, CBN/MPC/COM/150/293); value unchanged.'),
  ('mpr', '2024-03-25', 24.75, 'CBN', true, 'Corrected obs_date from placeholder 2024-03-01 to real 294th MPC meeting date (25-26 Mar 2024, CBN/MPC/COM/151/294); value unchanged.'),
  ('mpr', '2024-05-20', 26.25, 'CBN', true, 'Corrected obs_date from placeholder 2024-05-01 to real 295th MPC meeting date (20-21 May 2024, CBN Communique No. 152); value unchanged.'),
  ('mpr', '2024-07-22', 26.75, 'CBN', true, 'Corrected obs_date from placeholder 2024-07-01 to real 296th MPC meeting date (22-23 Jul 2024, CBN Communique No. 153); value unchanged.'),
  ('mpr', '2024-09-23', 27.25, 'CBN', true, 'Corrected obs_date from placeholder 2024-09-01 to real 297th MPC meeting date (23-24 Sep 2024, CBN Communique No. 154); value unchanged.'),
  ('mpr', '2024-11-25', 27.50, 'CBN', true, 'Corrected obs_date from placeholder 2024-11-01 to real 298th MPC meeting date (25-26 Nov 2024, CBN Communique No. 155, CBN/MPC/COM/155/298); value unchanged.');

COMMIT;

-- Verification query to run after COMMIT:
-- SELECT obs_date, value, source FROM observations WHERE indicator_id = 'mpr' ORDER BY obs_date;
-- Expect exactly 6 rows between 2024-02-26 and 2024-11-25, no row left at
-- the 1st-of-month placeholder dates, and no row duplicated.
