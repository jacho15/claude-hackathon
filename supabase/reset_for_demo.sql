-- ============================================================
-- VITALWATCH — full transient-data reset
--
-- Wipes every event/audit/state table in the database and re-stages
-- the floor to the Phase 2 §5 demo-start state. Identity rows
-- (hospitals, floors, patients, staff) are preserved.
--
-- Run this when:
--   * The dashboard / database has accumulated junk from many demo
--     runs (cancelled workflows, stale transfer requests, megabytes
--     of vitals history).
--   * You want a guaranteed-clean slate before recording the demo.
--
-- Idempotent. Safe to run as many times as you like.
--
-- After this script:
--   * vitals_readings, doctor_calls, flags: empty.
--   * bed_history, room_status_history, transfer_requests,
--     discharge_workflows, discharge_summaries, transport_requests,
--     cleaning_jobs: empty.
--   * patient_current_state: reset to the seeded "first frame"
--     values (Maria watch / Lin watch / David stable / James critical),
--     with the §19 step 8 freshness mix preserved.
--   * beds: 4 telemetry beds, Maria room 301 = clinically_clear
--     cardiac (the discharge candidate), other 3 occupied.
--   * patients: Maria's chart aligned with the cardiac demo framing.
-- ============================================================

-- 1. Truncate everything transient ------------------------------------
-- TRUNCATE ... RESTART IDENTITY CASCADE clears auto-increment
-- counters and follows FK chains so you don't have to order the
-- statements by dependency. CASCADE is safe here because every table
-- listed is something we *want* to wipe.
TRUNCATE TABLE
vitals_readings,
  flags,
  doctor_calls,
  transfer_requests,
  discharge_summaries,
  discharge_workflows,
  transport_requests,
  cleaning_jobs,
  bed_history,
  room_status_history
RESTART IDENTITY CASCADE;

-- 2. Reset patient_current_state to the seeded first-frame values ----
-- These are the same values as in seed.sql lines 47-98. We use a
-- single UPSERT so this works whether the rows exist or not. The
-- *_set_at columns are set to NOW() - INTERVAL form so the §19
-- step-8 freshness mix (Maria BP fresh, ACVPU stale) is recreated
-- on every reset.
INSERT INTO patient_current_state
  (patient_id, hr, bp_sys, bp_dia, spo2, temp_c, rr, flag, ai_note,
   news2_score, news2_risk,
   preliminary_news2_score, preliminary_news2_risk,
   on_oxygen, consciousness, spo2_scale,
   nibp_set_at, temp_set_at, o2_set_at, acvpu_set_at,
   discharge_status,
   last_updated)
VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001',
   95, 124, 78, 93.5, 38.5, 18, 'watch',
   'Awaiting first agent reading.',
   4, 'low',
   4, 'low',
   FALSE, 'A', 1,
   NOW() - INTERVAL '3 minutes',
   NOW() - INTERVAL '4 minutes',
   NULL,
   NOW() - INTERVAL '47 minutes',
   NULL,
   NOW()),
  ('aaaaaaaa-0000-0000-0000-000000000002',
   88, 124, 78, 93.5, 37.0, 18, 'watch',
   'Awaiting first agent reading.',
   2, 'low',
   2, 'low',
   FALSE, 'A', 1,
   NOW() - INTERVAL '6 minutes',
   NOW() - INTERVAL '6 minutes',
   NULL,
   NOW() - INTERVAL '90 minutes',
   NULL,
   NOW()),
  ('aaaaaaaa-0000-0000-0000-000000000003',
   78, 118, 74, 98.0, 36.7, 16, 'stable',
   'Awaiting first agent reading.',
   0, 'none',
   0, 'none',
   FALSE, 'A', 1,
   NOW() - INTERVAL '4 minutes',
   NOW() - INTERVAL '4 minutes',
   NULL,
   NOW() - INTERVAL '20 minutes',
   NULL,
   NOW()),
  ('aaaaaaaa-0000-0000-0000-000000000004',
   44, 104, 66, 90.5, 36.6, 15, 'critical',
   'Awaiting first agent reading.',
   5, 'medium',
   5, 'medium',
   FALSE, 'A', 1,
   NOW() - INTERVAL '8 minutes',
   NOW() - INTERVAL '8 minutes',
   NULL,
   NOW() - INTERVAL '35 minutes',
   NULL,
   NOW())
ON CONFLICT (patient_id) DO UPDATE SET
  hr                       = EXCLUDED.hr,
  bp_sys                   = EXCLUDED.bp_sys,
  bp_dia                   = EXCLUDED.bp_dia,
  spo2                     = EXCLUDED.spo2,
  temp_c                   = EXCLUDED.temp_c,
  rr                       = EXCLUDED.rr,
  flag                     = EXCLUDED.flag,
  ai_note                  = EXCLUDED.ai_note,
  news2_score              = EXCLUDED.news2_score,
  news2_risk               = EXCLUDED.news2_risk,
  preliminary_news2_score  = EXCLUDED.preliminary_news2_score,
  preliminary_news2_risk   = EXCLUDED.preliminary_news2_risk,
  on_oxygen                = EXCLUDED.on_oxygen,
  consciousness            = EXCLUDED.consciousness,
  spo2_scale               = EXCLUDED.spo2_scale,
  nibp_set_at              = EXCLUDED.nibp_set_at,
  temp_set_at              = EXCLUDED.temp_set_at,
  o2_set_at                = EXCLUDED.o2_set_at,
  acvpu_set_at             = EXCLUDED.acvpu_set_at,
  discharge_status         = NULL,
  last_updated             = EXCLUDED.last_updated;

-- 3. Re-stage bed inventory to the Phase 2 demo-start state -----------
-- Same payload as demo_phase_2_stage.sql so the two scripts agree.
INSERT INTO beds (room_number, ward, status, occupant_patient_id, last_change)
VALUES
  ('301', 'cardiac', 'clinically_clear', 'aaaaaaaa-0000-0000-0000-000000000001', NOW()),
  ('302', 'general', 'occupied',         'aaaaaaaa-0000-0000-0000-000000000002', NOW()),
  ('303', 'general', 'occupied',         'aaaaaaaa-0000-0000-0000-000000000003', NOW()),
  ('305', 'cardiac', 'occupied',         'aaaaaaaa-0000-0000-0000-000000000004', NOW())
ON CONFLICT (room_number) DO UPDATE SET
  ward                = EXCLUDED.ward,
  status              = EXCLUDED.status,
  occupant_patient_id = EXCLUDED.occupant_patient_id,
  reserved_for        = NULL,
  cleaning_eta        = NULL,
  ready_at            = NULL,
  last_change         = NOW();

-- 4. Align Maria's chart with the cardiac demo framing ----------------
-- See demo_phase_2_stage.sql for rationale. We update here too so a
-- single reset gives you a fully-coherent demo state in one shot.
UPDATE patients
   SET primary_dx    = 'Stable angina — observation, ruled out ACS',
       attending_doc = 'Dr. Reyes'
 WHERE id = 'aaaaaaaa-0000-0000-0000-000000000001';

-- 5. Sanity report ----------------------------------------------------
-- Useful when you run this in Supabase's SQL editor: confirms the
-- floor is in the expected demo-start shape.
SELECT 'beds' AS table_name, COUNT(*) AS rows FROM beds
UNION ALL SELECT 'patients',                  COUNT(*) FROM patients
UNION ALL SELECT 'patient_current_state',     COUNT(*) FROM patient_current_state
UNION ALL SELECT 'vitals_readings',           COUNT(*) FROM vitals_readings
UNION ALL SELECT 'doctor_calls',              COUNT(*) FROM doctor_calls
UNION ALL SELECT 'transfer_requests',         COUNT(*) FROM transfer_requests
UNION ALL SELECT 'discharge_workflows',       COUNT(*) FROM discharge_workflows
UNION ALL SELECT 'discharge_summaries',       COUNT(*) FROM discharge_summaries
UNION ALL SELECT 'cleaning_jobs',             COUNT(*) FROM cleaning_jobs
UNION ALL SELECT 'transport_requests',        COUNT(*) FROM transport_requests
UNION ALL SELECT 'bed_history',               COUNT(*) FROM bed_history
UNION ALL SELECT 'room_status_history',       COUNT(*) FROM room_status_history;
