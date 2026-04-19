-- ============================================================
-- VITALWATCH — schema
--
-- Paste this whole file into the Supabase SQL editor (one shot).
-- Re-running drops & recreates everything, so use the SQL editor's
-- "Run as transaction" toggle if you don't want a partial state.
--
-- After this, run seed.sql to load the demo floor + 4 patients.
-- ============================================================

-- Drop in dependency order so re-runs are clean.
DROP TABLE IF EXISTS doctor_calls         CASCADE;
DROP TABLE IF EXISTS flags                CASCADE;
DROP TABLE IF EXISTS vitals_readings      CASCADE;
DROP TABLE IF EXISTS patient_current_state CASCADE;
DROP TABLE IF EXISTS staff                CASCADE;
DROP TABLE IF EXISTS patients             CASCADE;
DROP TABLE IF EXISTS floors               CASCADE;
DROP TABLE IF EXISTS hospitals            CASCADE;

-- ------------------------------------------------------------
-- Hospitals and floors
-- ------------------------------------------------------------
CREATE TABLE hospitals (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE floors (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  hospital_id  UUID REFERENCES hospitals(id) ON DELETE CASCADE,
  name         TEXT NOT NULL,
  wing         TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Patients
-- ------------------------------------------------------------
CREATE TABLE patients (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  floor_id        UUID REFERENCES floors(id) ON DELETE SET NULL,
  room_number     TEXT NOT NULL,
  full_name       TEXT NOT NULL,
  date_of_birth   DATE,
  sex             TEXT CHECK (sex IN ('M', 'F', 'Other')),
  weight_kg       NUMERIC(5,1),
  primary_dx      TEXT,
  admission_date  DATE DEFAULT CURRENT_DATE,
  attending_doc   TEXT,
  status          TEXT DEFAULT 'admitted'
                  CHECK (status IN ('admitted', 'discharged', 'transferred')),
  notes           TEXT,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Live patient state — one row per patient, upserted by floor agent.
-- Realtime is enabled on this table.
--
-- The NEWS2 columns are added per Person 1's NEWS2 (RCP 2017)
-- implementation in agents/thresholds.py. They give the dashboard
-- a single ranked number per patient + the inputs that fed it.
-- ------------------------------------------------------------
CREATE TABLE patient_current_state (
  patient_id    UUID PRIMARY KEY REFERENCES patients(id) ON DELETE CASCADE,
  hr            NUMERIC(5,1),
  bp_sys        NUMERIC(5,1),
  bp_dia        NUMERIC(5,1),
  spo2          NUMERIC(4,1),
  temp_c        NUMERIC(4,1),
  rr            NUMERIC(4,1),
  flag          TEXT NOT NULL DEFAULT 'stable'
                CHECK (flag IN ('critical', 'watch', 'stable')),
  ai_note       TEXT,
  agent_address TEXT,
  -- NEWS2 (RCP 2017) -----------------------------------------
  news2_score   INTEGER  DEFAULT 0,
  news2_risk    TEXT     DEFAULT 'none'
                CHECK (news2_risk IN ('none','low','medium','high')),
  on_oxygen     BOOLEAN  DEFAULT FALSE,
  consciousness TEXT     DEFAULT 'A'
                CHECK (consciousness IN ('A','C','V','P','U')),
  spo2_scale    SMALLINT DEFAULT 1
                CHECK (spo2_scale IN (1, 2)),
  -- ----------------------------------------------------------
  scenario      TEXT,           -- mock-data scenario tag (debug-only)
  last_updated  TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Vitals history — append-only, written every poll cycle.
-- ------------------------------------------------------------
CREATE TABLE vitals_readings (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id  UUID REFERENCES patients(id) ON DELETE CASCADE,
  hr          NUMERIC(5,1),
  bp_sys      NUMERIC(5,1),
  bp_dia      NUMERIC(5,1),
  spo2        NUMERIC(4,1),
  temp_c      NUMERIC(4,1),
  rr          NUMERIC(4,1),
  flag        TEXT CHECK (flag IN ('critical', 'watch', 'stable')),
  news2_score INTEGER,
  news2_risk  TEXT CHECK (news2_risk IN ('none','low','medium','high')),
  recorded_at TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Flags / alerts log — written when a patient transitions into
-- a non-stable state, or when severity escalates.
-- ------------------------------------------------------------
CREATE TABLE flags (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id    UUID REFERENCES patients(id) ON DELETE CASCADE,
  flag_type     TEXT NOT NULL
                CHECK (flag_type IN ('critical', 'watch',
                                     'medication', 'trend',
                                     'ai_suggestion')),
  severity      INTEGER CHECK (severity BETWEEN 1 AND 5),
  message       TEXT NOT NULL,
  ai_note       TEXT,
  news2_score   INTEGER,
  acknowledged  BOOLEAN DEFAULT FALSE,
  ack_by        TEXT,
  ack_at        TIMESTAMPTZ,
  resolved      BOOLEAN DEFAULT FALSE,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Doctor call queue
-- ------------------------------------------------------------
CREATE TABLE doctor_calls (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id    UUID REFERENCES patients(id) ON DELETE CASCADE,
  doctor_name   TEXT NOT NULL,
  specialty     TEXT,
  urgency       TEXT NOT NULL
                CHECK (urgency IN ('urgent', 'routine', 'follow_up')),
  reason        TEXT,
  status        TEXT DEFAULT 'pending'
                CHECK (status IN ('pending', 'notified',
                                  'in_progress', 'completed',
                                  'cancelled')),
  scheduled_at  TIMESTAMPTZ,
  completed_at  TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- Staff
-- ------------------------------------------------------------
CREATE TABLE staff (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  floor_id    UUID REFERENCES floors(id) ON DELETE SET NULL,
  full_name   TEXT NOT NULL,
  role        TEXT CHECK (role IN ('nurse', 'doctor',
                                   'head_nurse', 'resident')),
  specialty   TEXT,
  on_duty     BOOLEAN DEFAULT TRUE,
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_vitals_patient_time
  ON vitals_readings (patient_id, recorded_at DESC);

CREATE INDEX idx_flags_patient_unresolved
  ON flags (patient_id, resolved, created_at DESC);

CREATE INDEX idx_doctor_calls_status
  ON doctor_calls (status, urgency, created_at);

CREATE INDEX idx_current_state_flag
  ON patient_current_state (flag);

CREATE INDEX idx_current_state_news2
  ON patient_current_state (news2_score DESC);

-- ============================================================
-- REALTIME — enable on the live tables only.
-- The dashboard subscribes to these.
-- ============================================================

ALTER PUBLICATION supabase_realtime
  ADD TABLE patient_current_state, flags, doctor_calls;
