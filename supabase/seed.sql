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
  ('aaaaaaaa-0000-0000-0000-000000000001',
   '22222222-0000-0000-0000-000000000001',
   '301', 'Maria Gonzalez', '1957-03-14', 'F',
   72.0, 'Post-op abdominal surgery', 'Dr. Patel'),
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
-- these rows on its first message.
INSERT INTO patient_current_state
  (patient_id, hr, bp_sys, bp_dia, spo2, temp_c, rr, flag, ai_note,
   news2_score, news2_risk, on_oxygen, consciousness, spo2_scale)
VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001',
   88, 124, 78, 93.5, 37.0, 18, 'watch',
   'Awaiting first agent reading.',
   2, 'low', FALSE, 'A', 1),
  ('aaaaaaaa-0000-0000-0000-000000000002',
   88, 124, 78, 93.5, 37.0, 18, 'watch',
   'Awaiting first agent reading.',
   2, 'low', FALSE, 'A', 1),
  ('aaaaaaaa-0000-0000-0000-000000000003',
   78, 118, 74, 98.0, 36.7, 16, 'stable',
   'Awaiting first agent reading.',
   0, 'none', FALSE, 'A', 1),
  ('aaaaaaaa-0000-0000-0000-000000000004',
   44, 104, 66, 90.5, 36.6, 15, 'critical',
   'Awaiting first agent reading.',
   5, 'medium', FALSE, 'A', 1);

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
