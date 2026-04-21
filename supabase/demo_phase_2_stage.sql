-- ============================================================
-- VITALWATCH — Phase 2 demo staging (re-run between rehearsals)
--
-- Idempotent: safe to run as many times as you like. Resets the
-- floor to the §5 "bed ready in 40 min, not 4 hours" demo start:
--
--   * 4 telemetry beds, all occupied (2 cardiac, 2 general).
--   * Maria Gonzalez (Room 301) flagged `clinically_clear` so she
--     is the obvious discharge candidate when the bed agent goes
--     looking for one.
--   * No in-flight transfer requests, discharge workflows, or
--     cleaning jobs.
--   * Maria's discharge_status badge cleared.
--
-- After this, click the dashboard's "Simulate ER chest-pain" button
-- and the audience should see Maria walk through the full
-- discharge -> cleaning -> ready -> reserved sequence in ~30s.
-- ============================================================

-- 1. Bed inventory ------------------------------------------------------
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

-- 2. Cancel any in-flight workflow / transfer / cleaning ----------------
UPDATE transfer_requests
   SET status = 'cancelled', fulfilled_at = NOW()
 WHERE status IN ('pending', 'matched', 'waiting_cleanup', 'ready');

UPDATE discharge_workflows
   SET status = 'cancelled', completed_at = NOW()
 WHERE status NOT IN ('completed', 'cancelled');

UPDATE cleaning_jobs
   SET status = 'cancelled', completed_at = NOW()
 WHERE status IN ('queued', 'in_progress');

UPDATE transport_requests
   SET status = 'cancelled'
 WHERE status IN ('booked', 'en_route');

-- 3. Clear Maria's discharge badge so the demo starts clean -------------
UPDATE patient_current_state
   SET discharge_status = NULL
 WHERE patient_id = 'aaaaaaaa-0000-0000-0000-000000000001';

-- 4. Align Maria's chart with the cardiac demo framing -----------------
-- The §5 demo opens with "ER chest-pain inbound (cardiac)" and the
-- bed agent picks Maria's clinically_clear cardiac bed. If her chart
-- still shows the legacy "Post-op abdominal surgery" diagnosis, the
-- Claude discharge summary will read about wound care while the
-- presenter is talking about cardiac telemetry. Snap the chart to a
-- cardiac-aligned dx so EN/ES summaries stay coherent.
UPDATE patients
   SET primary_dx    = 'Stable angina — observation, ruled out ACS',
       attending_doc = 'Dr. Reyes'
 WHERE id = 'aaaaaaaa-0000-0000-0000-000000000001';
