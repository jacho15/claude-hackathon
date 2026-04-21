-- ============================================================
-- VITALWATCH — Phase 2 migration (Bed + Discharge + Facilities)
--
-- Idempotent: safe to re-run on existing databases. Adds 8 new
-- tables, one column on patient_current_state, and grants Realtime
-- on the three tables the dashboard subscribes to.
--
-- After running this, paste the contents of demo_phase_2_stage.sql
-- to seed the demo bed inventory and mark Maria as clinically
-- clear for the §5 demo beat.
-- ============================================================

-- ------------------------------------------------------------
-- beds — one row per physical bed on the floor.
-- The Bed Agent is the sole writer.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS beds (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  room_number          TEXT UNIQUE NOT NULL,
  ward                 TEXT NOT NULL,
  status               TEXT NOT NULL DEFAULT 'occupied'
                       CHECK (status IN ('occupied','clinically_clear',
                                         'cleaning','ready','reserved')),
  occupant_patient_id  UUID REFERENCES patients(id) ON DELETE SET NULL,
  reserved_for         TEXT,                -- free-text label, e.g. "ER chest-pain inbound"
  cleaning_eta         TIMESTAMPTZ,
  ready_at             TIMESTAMPTZ,
  last_change          TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- bed_history — append-only audit trail for every status change.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bed_history (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bed_id      UUID REFERENCES beds(id) ON DELETE CASCADE,
  status      TEXT NOT NULL,
  actor       TEXT,                          -- "bed_agent" | "discharge_agent" | "facilities_agent" | nurse name
  at          TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- transfer_requests — bed reservations the Bed Agent is processing.
-- One row per ER/Triage request; status walks pending -> matched ->
-- waiting_cleanup -> ready -> fulfilled (or cancelled).
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transfer_requests (
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

-- ------------------------------------------------------------
-- discharge_workflows — one row per patient discharge in flight.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS discharge_workflows (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id   UUID REFERENCES patients(id) ON DELETE CASCADE,
  requested_by TEXT NOT NULL,
  language     TEXT NOT NULL DEFAULT 'es',   -- secondary summary language
  status       TEXT NOT NULL DEFAULT 'initiated'
               CHECK (status IN ('initiated','summary_drafted',
                                 'transport_booked','room_released',
                                 'completed','cancelled')),
  triggered_by_request_id UUID REFERENCES transfer_requests(id) ON DELETE SET NULL,
  started_at   TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ
);

-- ------------------------------------------------------------
-- discharge_summaries — Claude-generated text per language.
-- Two rows per workflow: one EN, one in the requested language.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS discharge_summaries (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id  UUID REFERENCES discharge_workflows(id) ON DELETE CASCADE,
  language     TEXT NOT NULL,
  content      TEXT NOT NULL,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- transport_requests — mock transport booking.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transport_requests (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id  UUID REFERENCES discharge_workflows(id) ON DELETE CASCADE,
  mode         TEXT NOT NULL DEFAULT 'wheelchair',
  eta          TIMESTAMPTZ,
  status       TEXT NOT NULL DEFAULT 'booked'
               CHECK (status IN ('booked','en_route','completed','cancelled')),
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- cleaning_jobs — Facilities Agent owns this queue.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cleaning_jobs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  room_number   TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','in_progress','done','cancelled')),
  crew          TEXT,
  requested_at  TIMESTAMPTZ DEFAULT NOW(),
  eta           TIMESTAMPTZ,
  completed_at  TIMESTAMPTZ
);

-- ------------------------------------------------------------
-- room_status_history — append-only audit on room state.
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS room_status_history (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  room_number  TEXT NOT NULL,
  status       TEXT NOT NULL,
  actor        TEXT,
  at           TIMESTAMPTZ DEFAULT NOW()
);

-- ------------------------------------------------------------
-- patient_current_state.discharge_status — surfaces the workflow
-- stage on each PatientCard. Sticky like the Phase 1.5 manual fields.
-- ------------------------------------------------------------
ALTER TABLE patient_current_state
  ADD COLUMN IF NOT EXISTS discharge_status TEXT;

-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_beds_status         ON beds (status);
CREATE INDEX IF NOT EXISTS idx_beds_ward_status    ON beds (ward, status);
CREATE INDEX IF NOT EXISTS idx_bed_history_at      ON bed_history (at DESC);
CREATE INDEX IF NOT EXISTS idx_transfer_status     ON transfer_requests (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_discharge_status    ON discharge_workflows (status, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_discharge_patient   ON discharge_workflows (patient_id);
CREATE INDEX IF NOT EXISTS idx_summaries_workflow  ON discharge_summaries (workflow_id);
CREATE INDEX IF NOT EXISTS idx_cleaning_status     ON cleaning_jobs (status, requested_at DESC);

-- ============================================================
-- REALTIME — Add new tables to the supabase_realtime publication.
-- Wrapped in a DO block because ALTER PUBLICATION ADD TABLE errors
-- if the table is already a member, and the publication itself may
-- not exist on some self-hosted setups.
-- ============================================================

DO $$
DECLARE
  tbl TEXT;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_publication WHERE pubname = 'supabase_realtime') THEN
    RAISE NOTICE 'supabase_realtime publication not found — skipping Realtime grants';
    RETURN;
  END IF;
  FOREACH tbl IN ARRAY ARRAY['beds', 'discharge_workflows', 'cleaning_jobs',
                             'transfer_requests', 'discharge_summaries']
  LOOP
    BEGIN
      EXECUTE format('ALTER PUBLICATION supabase_realtime ADD TABLE %I', tbl);
    EXCEPTION WHEN duplicate_object THEN
      -- already a member; ignore
      NULL;
    END;
  END LOOP;
END$$;
