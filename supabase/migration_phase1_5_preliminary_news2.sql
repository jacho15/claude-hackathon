-- ============================================================
-- VITALWATCH — Phase 1.5 migration: preliminary NEWS2 score
--
-- Adds two columns to patient_current_state:
--
--   preliminary_news2_score INT
--   preliminary_news2_risk  TEXT  ('none'|'low'|'medium'|'high')
--
-- The patient agent emits this alongside the full NEWS2 every
-- tick. It's the same scoring function with on_oxygen=FALSE and
-- consciousness='A' forced — i.e. "what we know from passive
-- sensors alone" — and the dashboard surfaces it whenever the
-- matching manual fields (o2_set_at / acvpu_set_at) are stale or
-- absent. The floor is never blind.
--
-- Idempotent: safe to re-run, safe to apply against a populated
-- database. Existing rows backfill to 0 / 'none' (the column
-- defaults); the patient agents will overwrite both on their
-- next tick.
--
-- Paste into the Supabase SQL editor in one shot.
-- ============================================================

ALTER TABLE patient_current_state
  ADD COLUMN IF NOT EXISTS preliminary_news2_score INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS preliminary_news2_risk  TEXT    DEFAULT 'none';

-- Add the CHECK constraint separately so the migration stays
-- idempotent even if the column already exists without it.
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
     WHERE conname = 'patient_current_state_preliminary_news2_risk_check'
  ) THEN
    ALTER TABLE patient_current_state
      ADD CONSTRAINT patient_current_state_preliminary_news2_risk_check
      CHECK (preliminary_news2_risk IN ('none','low','medium','high'));
  END IF;
END$$;

-- Sanity check: confirm both columns are present and the existing
-- rows have been backfilled. Expect 2 rows back.
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name  = 'patient_current_state'
  AND column_name IN ('preliminary_news2_score',
                      'preliminary_news2_risk')
ORDER BY column_name;
