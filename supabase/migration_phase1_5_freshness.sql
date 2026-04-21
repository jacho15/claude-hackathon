-- ============================================================
-- VITALWATCH — Phase 1.5 migration: per-field freshness
--
-- Adds four TIMESTAMPTZ columns to patient_current_state so the
-- dashboard can render a freshness badge per measurement and
-- distinguish "we measured this 3 min ago" from "we haven't
-- touched this in 47 min."
--
--   nibp_set_at  / temp_set_at  -> stamped by the agent loop only
--                                  when a *new* value lands (a
--                                  stalled cuff goes stale, not
--                                  silently old)
--   o2_set_at    / acvpu_set_at -> stamped by the floor agent's
--                                  /staff/patient/{id}/manual
--                                  endpoint when a nurse taps
--
-- Idempotent: safe to re-run, safe to apply against a populated
-- database. Existing rows keep all their data; the new columns
-- start as NULL (= "never set, render stale").
--
-- Paste into the Supabase SQL editor in one shot.
-- ============================================================

ALTER TABLE patient_current_state
  ADD COLUMN IF NOT EXISTS nibp_set_at  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS temp_set_at  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS o2_set_at    TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS acvpu_set_at TIMESTAMPTZ;

-- Sanity check: confirm the four columns are present.
-- Expect 4 rows back.
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name  = 'patient_current_state'
  AND column_name IN ('nibp_set_at', 'temp_set_at',
                      'o2_set_at',   'acvpu_set_at')
ORDER BY column_name;
