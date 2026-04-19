# Supabase setup (Person 2)

5-minute setup to take VitalWatch from mock-only to full
agent → Supabase → Realtime pipeline.

## 1. Create the project

1. Go to <https://supabase.com> → New Project.
2. Note the **Project URL**, **anon key**, and **service_role key**
   (Project Settings → API).

## 2. Run the schema + seed

In the Supabase **SQL Editor**:

1. Paste the contents of `supabase/schema.sql` and run.
2. Paste the contents of `supabase/seed.sql` and run.

`schema.sql` is destructive (drops + recreates) — safe to re-run
to reset the demo state.

After this you should see in Table Editor:
- `hospitals` (1 row), `floors` (1 row), `patients` (4 rows)
- `patient_current_state` (4 rows, all marked "Awaiting first
  agent reading.")
- `staff` (5 rows)
- empty `vitals_readings`, `flags`, `doctor_calls`

## 3. Enable Realtime

`schema.sql` already adds `patient_current_state`, `flags`, and
`doctor_calls` to the `supabase_realtime` publication. Confirm
in **Database → Replication** that the toggles are on for those
three tables. The dashboard subscribes to them.

## 4. Wire credentials

Copy `.env.example` → `.env` and fill in:

```env
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_KEY=<service_role key>     # agents use this
SUPABASE_ANON_KEY=<anon key>                # the dashboard uses this
ANTHROPIC_API_KEY=<sk-ant-...>              # for real Claude notes
```

Re-run the agents:

```bash
PATIENT_POLL_SECONDS=2.0 VITALWATCH_DEBUG=1 python -m scripts.run_all
```

The first message you should now see in the floor agent log is
**not** `Supabase writer disabled: ...`. Instead:

```
INFO:agents.supabase_writer: Supabase writer enabled (url=https://...).
```

Open `patient_current_state` in Supabase Table Editor and you'll
see the rows updating in real time.

## 5. What gets written, and when

| Table                  | Trigger                                  | Cadence |
|------------------------|------------------------------------------|---------|
| `patient_current_state`| every inbound `VitalsUpdate`             | upsert  |
| `vitals_readings`      | every inbound `VitalsUpdate`             | insert  |
| `flags`                | flag transitions to a *worse* state      | insert  |
| `doctor_calls`         | patient *newly* enters `critical`        | insert  |

Transitions are tracked in-memory inside `agents/supabase_writer.py`
(`_last_flag` dict), so a single critical reading produces exactly
one `flags` row and one `doctor_calls` row, not one per tick.

## 6. Schema additions over README §5

Two columns on top of the README's original schema, both populated
by the patient agents:

- `patient_current_state.news2_score` (INT) and
  `news2_risk` (TEXT, none/low/medium/high)
- `patient_current_state.on_oxygen` (BOOL),
  `consciousness` (TEXT, ACVPU letter), `spo2_scale` (SMALLINT)
- `patient_current_state.scenario` (TEXT, mock-data tag — debug)
- `vitals_readings.news2_score` and `news2_risk` for trend graphs
- `flags.news2_score` so the alert log shows severity at flag time

Person 3 should render the NEWS2 score as a coloured badge on each
patient card (none → grey, low → yellow, medium → orange, high → red).

## 7. Disabling Supabase

Unset `SUPABASE_URL` and the writer becomes a no-op (it logs the
reason once and then silently skips). Useful when demoing on a
flight or behind a corporate firewall.
