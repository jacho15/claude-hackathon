-- ============================================================
-- VITALWATCH — Phase 1.5 demo re-stage (Maria Gonzalez)
--
-- Run this in the Supabase SQL editor right BEFORE the demo to
-- reset Maria's row to the §19 step-8 starting state:
--
--   * Vitals tuned to preliminary NEWS2 = 4 (low / watch)
--   * BP fresh   (3 m ago)        — green badge
--   * Temp fresh (4 m ago)        — green badge
--   * ACVPU stale (47 m ago)      — red "cold" badge
--   * On-room-air, ACVPU = A (so a single tap to ACVPU=V adds
--     +3 → full NEWS2 = 7 → critical)
--
-- It also clears any pending doctor calls for Maria so the
-- queue is empty when the demo starts. Idempotent — safe to
-- re-run as many times as you like.
--
-- The patient agents will continue to overwrite hr/bp/spo2/
-- temp/rr on every tick; the *_set_at columns survive because
-- the writer only stamps them when the staff endpoint pushes
-- a manual update (see agents/supabase_writer.py).
-- ============================================================

UPDATE patient_current_state
SET
  hr            = 95,
  bp_sys        = 124,
  bp_dia        = 78,
  spo2          = 93.5,
  temp_c        = 38.5,
  rr            = 18,
  flag          = 'watch',
  news2_score   = 4,
  news2_risk    = 'low',
  preliminary_news2_score = 4,
  preliminary_news2_risk  = 'low',
  on_oxygen     = FALSE,
  consciousness = 'A',
  spo2_scale    = 1,
  ai_note       = 'Passive vitals stable in watch band; ACVPU not assessed in 47 m.',
  nibp_set_at   = NOW() - INTERVAL '3 minutes',
  temp_set_at   = NOW() - INTERVAL '4 minutes',
  o2_set_at     = NULL,
  acvpu_set_at  = NOW() - INTERVAL '47 minutes',
  last_updated  = NOW()
WHERE patient_id = 'aaaaaaaa-0000-0000-0000-000000000001';

-- Clear any pending / notified calls so the queue is empty for the demo
DELETE FROM doctor_calls
WHERE patient_id = 'aaaaaaaa-0000-0000-0000-000000000001'
  AND status IN ('pending', 'notified');

-- Clear any unacknowledged flags so the ack-loop demo works cleanly
DELETE FROM flags
WHERE patient_id = 'aaaaaaaa-0000-0000-0000-000000000001'
  AND acknowledged = FALSE;
