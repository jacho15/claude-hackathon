-- ============================================================
-- VITALWATCH — seed data (Floor 3 West demo)
--
-- Run AFTER schema.sql. Patient UUIDs match
-- agents/mock_vitals.py::DEMO_ROSTER so the agents and the DB
-- agree on identity from the first message.
-- ============================================================

-- Hospital ---------------------------------------------------------------
INSERT INTO hospitals (id, name) VALUES
  ('11111111-0000-0000-0000-000000000001', 'City General Hospital');

-- Floor ------------------------------------------------------------------
INSERT INTO floors (id, hospital_id, name, wing) VALUES
  ('22222222-0000-0000-0000-000000000001',
   '11111111-0000-0000-0000-000000000001',
   'Floor 3 West', 'General Medicine');

-- Patients ---------------------------------------------------------------
INSERT INTO patients
  (id, floor_id, room_number, full_name, date_of_birth, sex,
   weight_kg, primary_dx, attending_doc) VALUES
  -- Maria: cardiac-aligned dx so the Phase 2 demo (ER chest-pain ->
  -- bed agent picks Maria's clinically_clear cardiac bed -> discharge
  -- agent generates her summary) reads coherently end to end.
  ('aaaaaaaa-0000-0000-0000-000000000001',
   '22222222-0000-0000-0000-000000000001',
   '301', 'Maria Gonzalez', '1957-03-14', 'F',
   72.0, 'Stable angina — observation, ruled out ACS', 'Dr. Reyes'),
  ('aaaaaaaa-0000-0000-0000-000000000002',
   '22222222-0000-0000-0000-000000000001',
   '302', 'Lin Yao', '1983-07-22', 'F',
   58.5, 'Community-acquired pneumonia', 'Dr. Patel'),
  ('aaaaaaaa-0000-0000-0000-000000000003',
   '22222222-0000-0000-0000-000000000001',
   '303', 'David Mehta', '1995-11-09', 'M',
   80.0, 'Appendectomy (day 1 post-op)', 'Dr. Singh'),
  ('aaaaaaaa-0000-0000-0000-000000000004',
   '22222222-0000-0000-0000-000000000001',
   '305', 'James Okafor', '1970-01-30', 'M',
   90.0, 'Cardiac observation — bradycardia', 'Dr. Reyes');

-- Pre-fill the live-state table so the dashboard renders all 4 cards
-- BEFORE the first agent tick arrives. The floor agent will overwrite
-- these rows on its first message — EXCEPT for the *_set_at columns,
-- which it never writes (see supabase_writer.py: it only stamps them
-- when the staff endpoint pushes a manual update). So the freshness
-- timestamps below survive the first tick and drive the §19 step-8
-- demo beat (Maria's BP fresh, ACVPU stale).
INSERT INTO patient_current_state
  (patient_id, hr, bp_sys, bp_dia, spo2, temp_c, rr, flag, ai_note,
   news2_score, news2_risk,
   preliminary_news2_score, preliminary_news2_risk,
   on_oxygen, consciousness, spo2_scale,
   nibp_set_at, temp_set_at, o2_set_at, acvpu_set_at)
VALUES
  -- Maria Gonzalez (Room 301) — Phase 1.5 demo target.
  -- Passive vitals score preliminary NEWS2 = 4 (low / watch); a
  -- nurse tap of ACVPU=V will push the full NEWS2 to 7 (critical).
  -- BP fresh (3 m), Temp fresh (4 m), ACVPU stale (47 m) — the
  -- exact freshness mix called out in §19 step 8.
  ('aaaaaaaa-0000-0000-0000-000000000001',
   95, 124, 78, 93.5, 38.5, 18, 'watch',
   'Awaiting first agent reading.',
   4, 'low',
   4, 'low',
   FALSE, 'A', 1,
   NOW() - INTERVAL '3 minutes',
   NOW() - INTERVAL '4 minutes',
   NULL,
   NOW() - INTERVAL '47 minutes'),
  ('aaaaaaaa-0000-0000-0000-000000000002',
   88, 124, 78, 93.5, 37.0, 18, 'watch',
   'Awaiting first agent reading.',
   2, 'low',
   2, 'low',
   FALSE, 'A', 1,
   NOW() - INTERVAL '6 minutes',
   NOW() - INTERVAL '6 minutes',
   NULL,
   NOW() - INTERVAL '90 minutes'),
  ('aaaaaaaa-0000-0000-0000-000000000003',
   78, 118, 74, 98.0, 36.7, 16, 'stable',
   'Awaiting first agent reading.',
   0, 'none',
   0, 'none',
   FALSE, 'A', 1,
   NOW() - INTERVAL '4 minutes',
   NOW() - INTERVAL '4 minutes',
   NULL,
   NOW() - INTERVAL '20 minutes'),
  ('aaaaaaaa-0000-0000-0000-000000000004',
   44, 104, 66, 90.5, 36.6, 15, 'critical',
   'Awaiting first agent reading.',
   5, 'medium',
   5, 'medium',
   FALSE, 'A', 1,
   NOW() - INTERVAL '8 minutes',
   NOW() - INTERVAL '8 minutes',
   NULL,
   NOW() - INTERVAL '35 minutes');

-- Beds (Phase 2) ---------------------------------------------------------
-- Floor 3 West has 4 telemetry-capable beds. Two are cardiac-rated
-- (301 and 305) and both start occupied — the §5 "ER chest-pain
-- inbound, ward=cardiac" demo beat needs every cardiac bed full so
-- the Bed Agent has to dispatch Discharge to free Maria's room.
INSERT INTO beds
  (room_number, ward, status, occupant_patient_id) VALUES
  ('301', 'cardiac',  'occupied', 'aaaaaaaa-0000-0000-0000-000000000001'),
  ('302', 'general',  'occupied', 'aaaaaaaa-0000-0000-0000-000000000002'),
  ('303', 'general',  'occupied', 'aaaaaaaa-0000-0000-0000-000000000003'),
  ('305', 'cardiac',  'occupied', 'aaaaaaaa-0000-0000-0000-000000000004');

-- Staff (so doctor_calls.doctor_name has plausible targets) -------------
INSERT INTO staff (floor_id, full_name, role, specialty) VALUES
  ('22222222-0000-0000-0000-000000000001',
   'Dr. Patel',  'doctor', 'Internal Medicine'),
  ('22222222-0000-0000-0000-000000000001',
   'Dr. Singh',  'doctor', 'General Surgery'),
  ('22222222-0000-0000-0000-000000000001',
   'Dr. Reyes',  'doctor', 'Cardiology'),
  ('22222222-0000-0000-0000-000000000001',
   'Nurse Park', 'head_nurse', NULL),
  ('22222222-0000-0000-0000-000000000001',
   'Nurse Aaliyah', 'nurse', NULL);
