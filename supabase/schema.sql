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
DROP TABLE IF EXISTS room_status_history  CASCADE;
DROP TABLE IF EXISTS cleaning_jobs        CASCADE;
DROP TABLE IF EXISTS transport_requests   CASCADE;
DROP TABLE IF EXISTS discharge_summaries  CASCADE;
DROP TABLE IF EXISTS discharge_workflows  CASCADE;
DROP TABLE IF EXISTS transfer_requests    CASCADE;
DROP TABLE IF EXISTS bed_history          CASCADE;
DROP TABLE IF EXISTS beds                 CASCADE;
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
  -- Phase 1.5 preliminary NEWS2: same calculation as news2_score
  -- but with on_oxygen=FALSE and consciousness='A' forced. Surfaces
  -- the score we can derive from sensors alone, before any nurse-
  -- supplied manual data has been entered or has gone stale.
  preliminary_news2_score INTEGER DEFAULT 0,
  preliminary_news2_risk  TEXT    DEFAULT 'none'
                CHECK (preliminary_news2_risk IN ('none','low','medium','high')),
  -- Phase 1.5 per-field freshness. Stamped only when an actual
  -- fresh value lands (writer skips if the value is unchanged), so
  -- a stalled cuff or a removed probe surfaces as stale, not as
  -- silently old data. NULL = never set.
  --   nibp_set_at  / temp_set_at  -> stamped by the agent loop
  --   o2_set_at    / acvpu_set_at -> stamped by the staff endpoint
  nibp_set_at   TIMESTAMPTZ,
  temp_set_at   TIMESTAMPTZ,
  o2_set_at     TIMESTAMPTZ,
  acvpu_set_at  TIMESTAMPTZ,
  -- ----------------------------------------------------------
  -- Phase 2: surfaces the discharge workflow stage on the patient
  -- card. NULL = no workflow in flight. Sticky like the manual
  -- fields above; only the discharge agent writes it.
  discharge_status TEXT,
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
-- Phase 2: Bed, Discharge, Facilities
-- ============================================================

CREATE TABLE beds (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  room_number          TEXT UNIQUE NOT NULL,
  ward                 TEXT NOT NULL,
  status               TEXT NOT NULL DEFAULT 'occupied'
                       CHECK (status IN ('occupied','clinically_clear',
                                         'cleaning','ready','reserved')),
  occupant_patient_id  UUID REFERENCES patients(id) ON DELETE SET NULL,
  reserved_for         TEXT,
  cleaning_eta         TIMESTAMPTZ,
  ready_at             TIMESTAMPTZ,
  last_change          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE bed_history (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bed_id      UUID REFERENCES beds(id) ON DELETE CASCADE,
  status      TEXT NOT NULL,
  actor       TEXT,
  at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE transfer_requests (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ward          TEXT NOT NULL,
  urgency       TEXT NOT NULL DEFAULT 'urgent'
                CHECK (urgency IN ('routine','urgent','emergent')),
  reason        TEXT,
  status        TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','matched','waiting_cleanup',
                                  'ready','fulfilled','cancelled')),
  target_room   TEXT,
  released_by_patient_id UUID REFERENCES patients(id) ON DELETE SET NULL,
  eta           TIMESTAMPTZ,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  fulfilled_at  TIMESTAMPTZ
);

CREATE TABLE discharge_workflows (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id   UUID REFERENCES patients(id) ON DELETE CASCADE,
  requested_by TEXT NOT NULL,
  language     TEXT NOT NULL DEFAULT 'es',
  status       TEXT NOT NULL DEFAULT 'initiated'
               CHECK (status IN ('initiated','summary_drafted',
                                 'transport_booked','room_released',
                                 'completed','cancelled')),
  triggered_by_request_id UUID REFERENCES transfer_requests(id) ON DELETE SET NULL,
  started_at   TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

CREATE TABLE discharge_summaries (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id  UUID REFERENCES discharge_workflows(id) ON DELETE CASCADE,
  language     TEXT NOT NULL,
  content      TEXT NOT NULL,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE transport_requests (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id  UUID REFERENCES discharge_workflows(id) ON DELETE CASCADE,
  mode         TEXT NOT NULL DEFAULT 'wheelchair',
  eta          TIMESTAMPTZ,
  status       TEXT NOT NULL DEFAULT 'booked'
               CHECK (status IN ('booked','en_route','completed','cancelled')),
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE cleaning_jobs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  room_number   TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','in_progress','done','cancelled')),
  crew          TEXT,
  requested_at  TIMESTAMPTZ DEFAULT NOW(),
  eta           TIMESTAMPTZ,
  completed_at  TIMESTAMPTZ
);

CREATE TABLE room_status_history (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  room_number  TEXT NOT NULL,
  status       TEXT NOT NULL,
  actor        TEXT,
  at           TIMESTAMPTZ DEFAULT NOW()
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

CREATE INDEX idx_beds_status         ON beds (status);
CREATE INDEX idx_beds_ward_status    ON beds (ward, status);
CREATE INDEX idx_bed_history_at      ON bed_history (at DESC);
CREATE INDEX idx_transfer_status     ON transfer_requests (status, created_at DESC);
CREATE INDEX idx_discharge_status    ON discharge_workflows (status, started_at DESC);
CREATE INDEX idx_discharge_patient   ON discharge_workflows (patient_id);
CREATE INDEX idx_summaries_workflow  ON discharge_summaries (workflow_id);
CREATE INDEX idx_cleaning_status     ON cleaning_jobs (status, requested_at DESC);

-- ============================================================
-- REALTIME — enable on the live tables only.
-- The dashboard subscribes to these.
-- ============================================================

ALTER PUBLICATION supabase_realtime
  ADD TABLE patient_current_state, flags, doctor_calls,
            beds, discharge_workflows, cleaning_jobs,
            transfer_requests, discharge_summaries;
