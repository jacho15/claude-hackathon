# Nucleus — Autonomous Hospital Operating System

> Hackathon project · originally 5 hours / 4 people · now positioned as a multi-phase build  
> Stack: **Fetch.ai uAgents** · **Anthropic Claude (Sonnet)** · **Supabase** (Postgres + Realtime) · **React + Vite** dashboard · Claude-generated operational reports over Supabase SQL

---

## 1. The Vision

Hospitals are extraordinary at medicine and shockingly inefficient at coordination. Most of the chaos a patient experiences is not a clinical problem — it's a logistics problem. Beds aren't where they should be, results sit unread, supplies run out without warning, and nurses spend roughly **35 % of every shift on admin** instead of patients.

**Nucleus is an AI brain for the entire hospital** — not replacing doctors, but handling every operational decision that currently falls through the cracks or wastes human time.

| Today                                                            | With Nucleus                                                                                     |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Bed turnover from discharge to ready-for-admit: **3–4 hours**    | Cleaning queued automatically the moment discharge is logged: **30–60 min**                      |
| Critical lab result paged manually after a delay                 | Lab Agent flags the value, Claude summarizes it, the right specialist is notified within seconds |
| Pharmacy stockouts discovered when a nurse pulls an empty drawer | Pharmacy Agent forecasts depletion days in advance, auto-orders within budget                    |
| Shift handover = 40 chart notes per patient, read at 2 am        | Claude generates a 5-bullet handoff per patient, ranked by what changed                          |
| ER triage by gut-feel, beds allocated by phone calls             | Triage Agent scores severity, negotiates with Bed Agent, patient flows in under an hour          |

None of these are medical decisions. They are **coordination and data problems** — exactly what an autonomous-agent architecture solves.

---

## 2. The Agent Ecosystem (target architecture)

Each department gets a dedicated autonomous agent that observes its slice of the hospital, acts on it, and **negotiates with sibling agents** over Fetch.ai's messaging fabric. Claude is the reasoning core that any agent can consult when a situation is too novel for rule-based logic.

| Agent                                        | Owns                             | Primary inputs                              | Auto-actions                                                        |
| -------------------------------------------- | -------------------------------- | ------------------------------------------- | ------------------------------------------------------------------- |
| 🛏 **Bed Agent**                             | Floor-by-floor bed inventory     | EHR admit/discharge, Facilities ready-flag  | Suggests transfers, holds beds for inbound ER cases                 |
| 🧑‍⚕ **Staff Agent**                           | Nurse / doctor workload by shift | Assignment data, NEWS2 burden per nurse     | Reallocates patients during surges, flags burnout risk              |
| 🚑 **ER Triage Agent**                       | Incoming patient queue           | Vitals at intake, presenting complaint      | Scores urgency, books beds via Bed Agent                            |
| 💊 **Pharmacy Agent**                        | Drug inventory + reorder         | Dispense events, supplier lead times        | Forecasts stockout, places orders within budget                     |
| 🧪 **Lab Agent**                             | Pending tests + result delivery  | LIS feed, reference ranges                  | Flags critical values, pages the right clinician via Claude summary |
| 🧹 **Facilities Agent**                      | Room status + cleaning crew      | Discharge events, EVS roster                | Auto-dispatches cleaning, reports ready-for-admit                   |
| 📋 **Discharge Agent**                       | Patients ready to leave          | Vitals trend, attending sign-off, transport | Coordinates paperwork, transport, follow-up booking                 |
| 🩺 **Patient Vitals Agent** _(× N rooms)_    | One per patient room             | Bedside monitor / mock stream               | Computes NEWS2, raises clinical flags — **shipped in Phase 1**      |
| 🏛 **Floor Aggregator Agent** _(× N floors)_ | Roll-up for one ward             | All Patient Vitals Agents on the floor      | Persists state, opens doctor calls — **shipped in Phase 1**         |

> ✅ The two **bold-italicised rows** are live and verified in the current codebase. Everything else is roadmapped — the architecture is identical, only the data sources change.

### How agents negotiate (worked example)

When a patient is **discharged** at 14:00:

```
Discharge Agent  ── "Room 305 cleared at 14:00, transport at 14:30" ─►  Facilities Agent
Facilities Agent ── "EVS dispatched, ETA 30 min" ─►                     Bed Agent
Bed Agent        ── "Room 305 will be ready 15:00" ─►                   ER Triage Agent
ER Triage Agent  ── "Inbound chest-pain patient #4421 → Room 305" ─►    Bed Agent + Claude
Claude           ── generates pre-admission summary for cardiologist ─► Staff Agent
```

This chain currently takes hours of phone calls, sticky notes, and pages. Nucleus does it in seconds, autonomously, with a complete audit trail.

---

## 3. Claude — the Intelligence Layer

Claude is not a chatbot bolted on the side. It is the **reasoning surface** that every agent calls into when rules aren't enough.

| Use case                                       | Caller                  | Output                                                                |
| ---------------------------------------------- | ----------------------- | --------------------------------------------------------------------- |
| **Clinical notes per patient** _(shipped)_     | Patient Vitals Agent    | 1–2 sentence note with suggested action                               |
| **Shift handoff briefings**                    | Staff Agent             | Per-patient 5-bullet summary, ranked by what changed since last shift |
| **Discharge summaries in plain language**      | Discharge Agent         | Patient-readable + caregiver-readable + GP-readable versions          |
| **Natural-language query over hospital state** | Dashboard               | "Which patients on Ward 3 are likely ready for discharge today?"      |
| **Critical-value escalation reports**          | Lab Agent               | Result + clinical context + suggested specialist + draft page text    |
| **Multilingual patient communication**         | Discharge Agent         | Procedure / consent / aftercare in patient's language                 |
| **Incident / root-cause reports**              | Any agent on failure    | Timeline + contributing factors + recommended changes                 |
| **Ethical triage support during scarcity**     | ER Triage Agent → human | Frames the decision criteria; never decides                           |

A hard architectural rule: **Claude supports clinical judgment, it never replaces it.** Operations are automated; medicine is delegated to humans with better context.

---

## 4. The Command Center

A single dashboard that hospital administrators have never had — every agent's state, ranked and queryable, in one place.

- **Real-time bed occupancy heatmap** across all wards
- **Staff load distribution** — who's overwhelmed right now (NEWS2 burden per nurse)
- **ER wait-time trends** vs. predicted surge times
- **Medication stock** with reorder forecasts
- **Discharge bottleneck tracker** — patients stuck and _why_
- **Live patient grid** _(shipped)_ — Phase 1 nurse station view
- **Doctor call queue** _(shipped)_ — open, in-progress, completed
- **Auto-generated weekly / monthly reports** written by Claude from the operational dataset
- **Natural-language query box** — "show me patients whose NEWS2 has risen by 2 in the last hour"

---

## 5. End-to-End Demo Flow (target)

The story we want to tell on stage. The bold steps are running today.

> 🚑 14:02 — Patient arrives at ER with chest pain. **ER Triage Agent** scores severity 4/5, requests a cardiac-ward bed.
>
> 🛏 14:03 — **Bed Agent** has zero free cardiac beds. It queries **Discharge Agent**: two patients on Ward 3 are clinically clear to leave but waiting on paperwork.
>
> 📋 14:04 — **Discharge Agent** triggers Claude to generate the discharge summary in English + Spanish, schedules transport, books a 1-week follow-up.
>
> 🧹 14:30 — **Facilities Agent** receives the auto-cleaning request, dispatches EVS.
>
> ✅ 15:05 — Bed marked ready. **Bed Agent** confirms reservation. ER patient moves up. _(In a status-quo hospital, this would be the 4-hour mark and the patient would still be in the ER hallway.)_
>
> 🩺 15:18 — Patient is now in Room 305. **Patient Vitals Agent for Room 305** boots, polls the monitor every 10 s. **NEWS2 = 7 (high)** on first reading because of supplemental O₂ + tachycardia.
>
> 🚨 15:18 — **Floor Aggregator** receives the message, persists `patient_current_state`, inserts a `flags` row, and opens a `doctor_calls` entry urgently for cardiology.
>
> 🧪 15:42 — **Lab Agent** observes troponin = 0.8 ng/mL (well above 0.04 critical threshold). Claude summarizes the trajectory, drafts the page text, and pings the on-call cardiologist. Nurse gets a clean handoff card.
>
> 👨‍⚕️ 15:45 — Cardiologist accepts on the dashboard. The whole timeline above is one click away as an audit trail.

That's a single patient, end-to-end, with no human coordinator on the loop.

---

## 6. What's Built Today (Phase 1 — Patient Monitoring)

The current codebase ships the two **most safety-critical** agents in the ecosystem and proves the inter-agent messaging + persistence + AI-note pattern that every other agent will reuse.

### 6.1 Architecture (current)

```
┌─────────────────────────────────────────────────────────┐
│                    BEDSIDE LAYER                        │
│                                                         │
│  [Patient Agent 301]  [Patient Agent 302]  [Agent N]    │
│   • Polls vitals       • Polls vitals                   │
│   • NEWS2 score        • NEWS2 score                    │
│   • Claude note        • Claude note                    │
│   • Sends VitalsUpdate                                  │
└──────────────┬──────────────────────────────────────────┘
               │  uAgents async messaging (ctx.send)
┌──────────────▼──────────────────────────────────────────┐
│                    FLOOR LAYER                          │
│                                                         │
│            [Floor Aggregator Agent]                     │
│   • Subscribes to all patient agents                    │
│   • Ranks by NEWS2 score & flag                         │
│   • Upserts → patient_current_state                     │
│   • Inserts → vitals_readings, flags, doctor_calls      │
└──────────────┬──────────────────────────────────────────┘
               │  Supabase Realtime (WebSocket)
┌──────────────▼──────────────────────────────────────────┐
│                    STATION LAYER                        │
│                                                         │
│   [Nurse Station Dashboard]   [Doctor Call Queue]       │
│   React frontend              Triggered by transitions  │
│   Live patient grid           Urgent / Routine queue    │
└─────────────────────────────────────────────────────────┘
```

### 6.2 What is verified live today

| Capability                                                                         | Status                                             |
| ---------------------------------------------------------------------------------- | -------------------------------------------------- |
| 4 Patient Vitals Agents + 1 Floor Aggregator running in one process                | ✅ verified                                        |
| Mock vitals stream with 5 named clinical scenarios                                 | ✅                                                 |
| **NEWS2 (RCP 2017)** scoring with O₂ + ACVPU per-room overrides                    | ✅                                                 |
| Inter-agent messaging via Fetch.ai uAgents `Bureau`                                | ✅                                                 |
| Supabase persistence (patient_current_state, vitals_readings, flags, doctor_calls) | ✅ code-complete; pending project + creds          |
| Claude clinical-note generator with per-patient cache                              | ✅ code-complete; activates on `ANTHROPIC_API_KEY` |
| Doctor-call queue auto-opened on flag escalation                                   | ✅                                                 |
| Graceful degrade when Supabase / Anthropic creds are absent                        | ✅                                                 |
| React dashboard subscribing to Supabase Realtime                                   | ⏳ Person 3                                        |
| Doctor-queue UI + acknowledge flow                                                 | ⏳ Person 4                                        |
| Agentverse Mailbox registration (cross-machine)                                    | ⏳ optional                                        |

### 6.3 Why these two agents first

The Patient + Floor pair is the highest-stakes piece of the entire ecosystem (people die when vitals are missed) and the smallest piece that exercises every architectural primitive Nucleus needs:

1. **Agent → Agent messaging** — Patient → Floor `VitalsUpdate`
2. **Stateful aggregation** — Floor's in-memory snapshot
3. **Transition-driven side effects** — `flags` and `doctor_calls` only on escalations, never spam
4. **Persistence + Realtime fan-out** — `patient_current_state` upsert + WebSocket push
5. **Claude reasoning loop** — note generation with cache, fail-safe stub
6. **Clinically validated logic** — NEWS2 scoring per published RCP table

Every additional agent (Bed, Lab, Pharmacy, etc.) reuses these exact primitives. Phase 1 is the **proof the architecture works**; Phases 2+ are scope.

### 6.4 NEWS2 — what's sensed vs what needs a human

The seven NEWS2 inputs split cleanly into two groups, and the system treats them differently. In the Phase 1.5 build target, **five of seven** parameters are continuously sensed; only the two genuinely human-judgment fields remain manual.

| Parameter                       | Source                                        | Refresh               | Treatment                                 |
| ------------------------------- | --------------------------------------------- | --------------------- | ----------------------------------------- |
| Heart rate                      | ECG / SpO₂ probe (continuous)                 | every ~10 s           | **passive** — agent updates every tick    |
| SpO₂                            | Pulse oximeter (continuous)                   | every ~10 s           | **passive**                               |
| Respiratory rate                | Chest impedance / capnography (continuous)    | every ~10 s           | **passive**                               |
| Systolic BP                     | Auto-cycling NIBP cuff                        | every ~5–15 min       | **passive** — surfaced with `nibp_set_at` |
| Temperature                     | Continuous skin probe / auto-cycling tympanic | every ~1–5 min        | **passive** — surfaced with `temp_set_at` |
| Supplemental O₂ (on/off + flow) | Nurse-set on the wall flowmeter               | event-driven          | **manual** — dashboard tap                |
| Consciousness (ACVPU)           | Nurse assessment                              | per protocol (~1–4 h) | **manual** — dashboard tap                |

The two manual fields are the only places where a human still has to _put a number into the system_. Everything else is a sensor read.

### 6.5 Phase 1.5 — passive sensing × human-in-the-loop

Four small additions turn the current passive-only mesh into a complete real-time NEWS2 surface that visibly distinguishes "we measured this" from "we're inferring this." No new apps; everything rides on the existing dashboard and the existing Supabase Realtime channel.

**1. Preliminary NEWS2 score**

The patient agent already computes the full NEWS2. We add a sibling field `preliminary_news2_score` computed from only the five passively-sensed parameters (HR, SpO₂, RR, BP, temp), assuming room air and ACVPU = A by default. This is what the dashboard shows when the two manual fields haven't been set or have gone stale, so the floor is never blind.

**2. Per-field freshness**

`patient_current_state` gains four `*_set_at TIMESTAMPTZ` columns:

```sql
nibp_set_at  TIMESTAMPTZ,   -- when last BP reading actually arrived
temp_set_at  TIMESTAMPTZ,   -- when last temperature reading actually arrived
o2_set_at    TIMESTAMPTZ,   -- when a nurse last touched O₂ status
acvpu_set_at TIMESTAMPTZ    -- when a nurse last assessed consciousness
```

The agent only writes `nibp_set_at` / `temp_set_at` when a fresh monitor value actually shows up — so a brief monitor outage surfaces as stale, not as silently old data. The dashboard renders a small per-field badge: `BP 122/78 · 4 m` (green) → `· 12 m` (amber) → `· 32 m` (red).

**3. Inline manual controls — on the same dashboard, no separate app**

The existing nurse station patient cards grow a 3-control strip:

- **ACVPU** dropdown — A / C / V / P / U
- **Supplemental O₂** toggle + flow-rate field
- **Manual override** — opens BP / temp inputs for the rare case the auto-cycle hasn't fired

Each interaction is a single `POST /staff/patient/{id}/manual` to a new endpoint hosted by the Floor Aggregator's HTTP server. The handler upserts the row, stamps the matching `*_set_at`, and Supabase Realtime fans the row out to every connected dashboard, which re-runs `score_news2()` instantly. Two seconds of nurse work; no second app, no separate auth surface, no mobile build.

**4. Staff Agent — overdue manual checks (first slice)**

A minimal early Staff Agent reads `acvpu_set_at` and `o2_set_at` and surfaces a soft alert when either has gone untouched beyond protocol (e.g. ACVPU > 4 h, O₂ > 2 h). Renders as a small "ACVPU due" badge on the patient card. This is the natural seed of the full Phase-4 Staff Agent — same pattern, reused later for nurse-burden balancing and shift handover triggers.

**Why these four belong together.** They convert NEWS2 from a background number into a live, accountable surface that visibly distinguishes machine sensing from human judgment — and they unlock the cleanest end-to-end demo beat in the system:

> The floor shows Maria Gonzalez at **NEWS2 = 4** (medium) from continuously-sensed vitals.  
> A nurse standing at the station taps **ACVPU = V** on her card.  
> The card immediately re-renders at **NEWS2 = 7** (high) because of NEWS2's single-parameter-3 rule.  
> A `doctor_calls` row opens automatically. The Realtime fan-out updates every other connected screen in under a second.

One tap, eight seconds of stage time, the entire human-in-the-loop story.

---

## 7. Roadmap

| Phase                                 | Agents added                                         | Demo unlock                                                                         | Status             |
| ------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------ |
| **1 — Patient Monitoring**            | Patient Vitals · Floor Aggregator                    | Live patient grid + NEWS2 + auto doctor calls                                       | ✅ shipped         |
| **1.5 — Passive + Human-in-the-Loop** | Staff Agent (overdue-check slice)                    | Preliminary NEWS2, per-field freshness, inline manual controls, ACVPU-tap demo beat | planned (see §6.5) |
| **2 — Bed & Discharge**               | Bed Agent · Discharge Agent · Facilities Agent       | "Bed ready in 40 min, not 4 hours" demo beat                                        | next               |
| **3 — Lab & Pharmacy**                | Lab Agent · Pharmacy Agent                           | Critical-value page + auto-reorder                                                  |                    |
| **4 — ER & Staff**                    | ER Triage Agent · Staff Agent                        | Full patient-journey narrative end-to-end                                           |                    |
| **5 — Command Center**                | Executive dashboard, NL query, weekly Claude reports | Hospital-administrator view                                                         |                    |
| **6 — Multi-hospital**                | Hospital-level federation, cross-site bed transfers  | Network-of-hospitals demo                                                           | stretch            |

---

## 8. Technical Architecture (Phase 1 reference)

The rest of this document is the **Phase 1 implementation reference** — schema, code shapes, clinical thresholds, and the work split that produced the current build. Future phases extend this; they don't replace it.

### 8.1 Agent communication (Fetch.ai uAgents)

- Each **Patient Vitals Agent** runs on `@agent.on_interval(period=10.0)` — polling every 10 seconds.
- Agents communicate via `await ctx.send(FLOOR_AGENT_ADDRESS, VitalsUpdate(...))`.
- The **Floor Aggregator Agent** uses `@agent.on_message(model=VitalsUpdate)` to receive all patient updates.
- All agents register on the **Almanac contract** for discovery (or run locally via `Bureau` for the demo).
- The Floor Agent calls into `agents/supabase_writer.py` after each aggregation cycle.

### 8.2 Real-time dashboard (Supabase Realtime)

- The React dashboard subscribes to Supabase Realtime on the `patient_current_state` table.
- On each `INSERT` or `UPDATE` event, the dashboard re-renders the patient grid.
- Doctor call queue uses its own Realtime channel on `doctor_calls`.

---

## 9. Patient Vitals Agent (current implementation)

```python
from uagents import Agent, Context, Model
from agents.thresholds import score_news2
from agents.claude_notes import call_claude_for_note

class VitalsUpdate(Model):
    patient_id: str
    room: str
    full_name: str
    hr: float; bp_sys: float; bp_dia: float
    spo2: float; temp_c: float; rr: float
    flag: str            # "critical" | "watch" | "stable"
    ai_note: str         # Claude-generated clinical note
    news2_score: int = 0
    news2_risk: str = "none"   # "none" | "low" | "medium" | "high"
    on_oxygen: bool = False
    consciousness: str = "A"   # ACVPU
    spo2_scale: int = 1

@patient_agent.on_interval(period=10.0)
async def monitor_vitals(ctx: Context):
    vitals = read_vitals_from_mock()           # or real monitor API
    result = score_news2(
        vitals,
        on_oxygen=on_oxygen,
        consciousness=consciousness,
        spo2_scale=spo2_scale,
    )
    note = call_claude_for_note(
        vitals, result.flag,
        patient_id=patient_id,
        news2_score=result.score,
        news2_risk=result.risk,
        on_oxygen=on_oxygen,
        consciousness=consciousness,
    )
    await ctx.send(FLOOR_AGENT_ADDRESS, VitalsUpdate(
        patient_id=patient_id, room=room, full_name=full_name,
        flag=result.flag, ai_note=note,
        news2_score=result.score, news2_risk=result.risk,
        on_oxygen=on_oxygen, consciousness=consciousness,
        spo2_scale=spo2_scale,
        **vitals,
    ))
```

### 9.1 Flag evaluation — NEWS2 (RCP 2017)

Phase 1 uses **NEWS2** — the UK Royal College of Physicians' National Early Warning Score 2 (2017), the de-facto standard EWS in the NHS and widely adopted internationally.

Score → flag mapping:

| NEWS2 aggregate                   | Risk band | UI flag    |
| --------------------------------- | --------- | ---------- |
| 0                                 | none      | `stable`   |
| 1–4 (no single param = 3)         | low       | `watch`    |
| 3 in any single parameter, OR 5–6 | medium    | `critical` |
| ≥ 7                               | high      | `critical` |

Per-parameter scoring tables and the `score_news2()` implementation are in `agents/thresholds.py`. They follow the published RCP table verbatim (with `<` upper-bound encoding so fractional values from the bedside monitor don't fall between bands).

### 9.2 Floor Aggregator Agent

```python
@floor_agent.on_message(model=VitalsUpdate, replies=VitalsAck)
async def handle_patient_update(ctx, sender, msg: VitalsUpdate):
    floor_state[msg.patient_id] = snapshot_from(msg, sender)
    persist_to_supabase(floor_state[msg.patient_id])
    await ctx.send(sender, VitalsAck(...))
```

`persist_to_supabase` fans out into:

1. `patient_current_state` — upsert every tick
2. `vitals_readings` — insert every tick (history)
3. `flags` — insert **only on escalation** (stable→watch, watch→critical)
4. `doctor_calls` — insert **only when newly critical**, with attending physician auto-resolved

Transitions are tracked in-memory inside `agents/supabase_writer.py` so a sustained critical state produces exactly one `flags` row and one `doctor_calls` row, not one per tick.

---

## 10. Supabase Database Schema (Phase 1)

Full SQL lives in `supabase/schema.sql` and `supabase/seed.sql`. Highlights:

```sql
CREATE TABLE patient_current_state (
  patient_id     UUID PRIMARY KEY REFERENCES patients(id),
  hr             NUMERIC(5,1),
  bp_sys         NUMERIC(5,1),
  bp_dia         NUMERIC(5,1),
  spo2           NUMERIC(4,1),
  temp_c         NUMERIC(4,1),
  rr             NUMERIC(4,1),
  flag           TEXT NOT NULL DEFAULT 'stable'
                 CHECK (flag IN ('critical','watch','stable')),
  ai_note        TEXT,
  agent_address  TEXT,
  -- NEWS2 (RCP 2017) -----------------------------------------
  news2_score    INTEGER  DEFAULT 0,
  news2_risk     TEXT     DEFAULT 'none'
                 CHECK (news2_risk IN ('none','low','medium','high')),
  on_oxygen      BOOLEAN  DEFAULT FALSE,
  consciousness  TEXT     DEFAULT 'A'
                 CHECK (consciousness IN ('A','C','V','P','U')),
  spo2_scale     SMALLINT DEFAULT 1
                 CHECK (spo2_scale IN (1, 2)),
  scenario       TEXT,
  last_updated   TIMESTAMPTZ DEFAULT NOW()
);
```

The full schema additionally contains:

- `hospitals`, `floors`, `patients` — facility hierarchy (Phase 1 = 1 hospital, 1 floor, 4 patients)
- `vitals_readings` — append-only history (extends with NEWS2 columns for future trend graphs)
- `flags` — alert log with `acknowledged` / `resolved` workflow fields
- `doctor_calls` — call queue with urgency / status / scheduled / completed lifecycle
- `staff` — nurse / doctor roster per floor

Realtime is enabled on the three live tables: `patient_current_state`, `flags`, `doctor_calls`.

Phases 2+ extend this schema with:

- `beds`, `bed_history`, `transfer_requests` — Bed Agent
- `lab_orders`, `lab_results`, `result_critical_thresholds` — Lab Agent
- `medications`, `pharmacy_inventory`, `dispense_events`, `purchase_orders` — Pharmacy Agent
- `cleaning_jobs`, `room_status_history` — Facilities Agent
- `discharge_workflows`, `discharge_summaries`, `transport_requests` — Discharge Agent
- `er_arrivals`, `triage_scores`, `er_assignments` — ER Triage Agent
- `staff_assignments`, `shift_workload_metrics` — Staff Agent

---

## 11. Clinical Thresholds Reference (Phase 1 NEWS2)

Each parameter scores 0 / 1 / 2 / 3 per the RCP NEWS2 table. The implementation is in `agents/thresholds.py`.

| Parameter                                | 3              | 2      | 1                      | 0         | 1      | 2       | 3     |
| ---------------------------------------- | -------------- | ------ | ---------------------- | --------- | ------ | ------- | ----- |
| RR (breaths/min)                         | ≤ 8            | –      | 9–11                   | 12–20     | –      | 21–24   | ≥ 25  |
| SpO₂ Scale 1                             | ≤ 91           | 92–93  | 94–95                  | ≥ 96      | –      | –       | –     |
| SpO₂ Scale 2 (target 88–92, on O₂ band)¹ | ≤ 83           | 84–85  | 86–87                  | 88–92     | 93–94  | 95–96   | ≥ 97  |
| Air or O₂                                | –              | yes    | –                      | air       | –      | –       | –     |
| SBP (mmHg)                               | ≤ 90           | 91–100 | 101–110                | 111–219   | –      | –       | ≥ 220 |
| Pulse (bpm)                              | ≤ 40           | –      | 41–50                  | 51–90     | 91–110 | 111–130 | ≥ 131 |
| Consciousness (ACVPU)                    | C / V / P / U² | –      | –                      | A         | –      | –       | –     |
| Temp (°C)                                | ≤ 35.0         | ≥ 39.1 | 35.1–36.0 or 38.1–39.0 | 36.1–38.0 | –      | –       | –     |

¹ Scale 2 is opt-in per room — used for hypercapnic respiratory failure (e.g. COPD).  
² ACVPU: **A**lert, new **C**onfusion, responsive to **V**oice / **P**ain, **U**nresponsive.

**Sourcing in Nucleus** (see §6.4 / §6.5): RR, SpO₂ and pulse come from the continuous monitor every ~10 s. Systolic BP and temperature also flow in continuously — BP from the auto-cycling NIBP cuff (typically every 5–15 min) and temperature from a continuous skin probe or auto-cycling tympanic device — and the dashboard tags each with a `*_set_at` freshness badge so a stalled cuff or removed probe is immediately visible. Only **supplemental O₂ status** and **ACVPU** are nurse-set; both are entered with a single tap directly on the existing nurse-station dashboard, no separate app.

---

## 12. Claude Integration

```python
def call_claude_for_note(vitals, flag, *, patient_id, news2_score,
                         news2_risk, on_oxygen, consciousness):
    # Per-(patient_id, flag) cache + 60s refresh on non-stable patients
    # caps spend at ~30–40 calls per 5-min demo.
    cached = _cached_note(patient_id, flag)
    if cached: return cached

    client = _get_client()
    if client is None:                       # no key / lib missing
        return _stub(vitals, flag)

    prompt = _PROMPT_TEMPLATE.format(...)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=120,
        messages=[{"role": "user", "content": prompt}],
    )
    return parse(message)
```

The prompt includes vitals, NEWS2 score, ACVPU, O₂ status, and the current flag. It asks for a single ≤ 40-word clinical note ending with an explicit suggested action when status is watch / critical. **No PHI is sent** — the patient's name is deliberately omitted.

Failure modes (rate limit, bad key, network) all fall back to a deterministic stub so the agent loop never blocks on Claude.

---

## 13. Tech Stack Summary

| Layer           | Technology                            | Purpose                                 |
| --------------- | ------------------------------------- | --------------------------------------- |
| Agent framework | Fetch.ai uAgents 0.24+                | All department agents, async messaging  |
| Agent discovery | Almanac contract / Agentverse Mailbox | Cross-machine reachability              |
| Database        | Supabase (PostgreSQL)                 | Persistent state, schema, RLS           |
| Realtime        | Supabase Realtime                     | WebSocket push to dashboard             |
| AI reasoning    | Anthropic Claude (Sonnet)             | Notes, summaries, NL query, escalations |
| Frontend        | React + Vite + Supabase JS            | Nurse station + executive dashboards    |
| Analytics       | Supabase Postgres + Claude-generated reports | Operational & executive reporting       |
| Mock data       | `mock_vitals.py` scenario presets     | Demo-ready vital streams                |

---

## 14. Folder Structure

```
nucleus/
├── agents/
│   ├── messages.py            # Wire models (VitalsUpdate, VitalsAck, …)
│   ├── thresholds.py          # NEWS2 (RCP 2017) — score_news2()
│   ├── mock_vitals.py         # VitalsStream + 5 clinical scenarios + DEMO_ROSTER
│   ├── patient_agent.py       # build_patient_agent(...) + CLI
│   ├── floor_aggregator.py    # floor_agent + persist_to_supabase() dispatch
│   ├── claude_notes.py        # Anthropic note generator (cached, fail-safe)
│   ├── supabase_writer.py     # patient_current_state / vitals_readings /
│   │                          #   flags / doctor_calls writes
│   └── README.md              # agent-layer runbook
├── supabase/
│   ├── schema.sql             # Full Phase 1 schema (paste into SQL editor)
│   ├── seed.sql               # Demo floor + 4 patients + staff
│   └── README.md              # 5-minute backend setup
├── dashboard/                 # React + Vite (Phase 1 — Person 3)
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── PatientGrid.jsx
│       │   ├── PatientCard.jsx
│       │   ├── FlagBadge.jsx       # also renders NEWS2 badge
│       │   ├── DoctorQueue.jsx
│       │   └── SummaryBar.jsx
│       └── lib/supabase.js
├── scripts/
│   └── run_all.py             # Bureau: floor + 4 patient agents in one process
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md                  # ← you are here
```

---

## 15. Quick Start

```bash
# 1. Python env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. (Optional) Supabase + Claude — see supabase/README.md
cp .env.example .env
# fill in SUPABASE_URL, SUPABASE_SERVICE_KEY, ANTHROPIC_API_KEY

# 3. Run the agent mesh
PATIENT_POLL_SECONDS=2.0 VITALWATCH_DEBUG=1 python -m scripts.run_all

# 4. (Optional) Run the dashboard
cd dashboard && npm install && npm run dev
```

Without any `.env` keys, the system runs in **mock-only** mode: no Supabase writes, no Claude calls, but the full agent mesh + NEWS2 scoring + console snapshots all work, so Person 3 can iterate on the dashboard against the seed data.

---

## 16. Environment Variables

```env
# Fetch.ai (optional — only for Agentverse Mailbox)
AGENTVERSE_API_KEY=
FLOOR_AGENT_ADDRESS=

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_KEY=                 # agents use this

# Claude
ANTHROPIC_API_KEY=

# Runtime knobs
PATIENT_POLL_SECONDS=10.0
VITALWATCH_DEBUG=0
BUREAU_PORT=8200

# Per-room demo overrides (optional)
# VITALWATCH_SCENARIO_301=sepsis
# VITALWATCH_OXYGEN_305=1
# VITALWATCH_ACVPU_301=V
# VITALWATCH_SPO2SCALE_302=2
```

---

## 17. Work Division — Phase 1 sprint (4 people)

### Person 1 — Agent Infrastructure Lead ✅ shipped

**Goal:** Build and run all agents end-to-end with mock data.

| Task                                                             | Status |
| ---------------------------------------------------------------- | ------ |
| Set up Python env, install `uagents`, scaffold project           | ✅     |
| Build `mock_vitals.py` — 5 clinical scenarios                    | ✅     |
| Build `patient_agent.py` — interval polling, NEWS2, send         | ✅     |
| Build `floor_aggregator.py` — aggregation + persistence dispatch | ✅     |
| Bureau-based mesh in one process (skipped Mailbox for now)       | ✅ / ⏸ |
| Integration support: NEWS2, doctor-queue logic, docs             | ✅     |

**Bonus shipped:** full **NEWS2 (RCP 2017)** implementation with O₂ + ACVPU per-room demo overrides.

### Person 2 — AI & Backend Logic ✅ shipped (code-complete, awaiting creds)

**Goal:** Claude API integration + Supabase write logic inside agents.

| Task                                                   | Status          |
| ------------------------------------------------------ | --------------- |
| Supabase project, paste `schema.sql`, run `seed.sql`   | ⏳ user-side    |
| Build `claude_notes.py` — call, prompt, parse, cache   | ✅              |
| Build `thresholds.py` — flag logic (NEWS2 by Person 1) | ✅              |
| Build `supabase_writer.py` — upsert + insert paths     | ✅              |
| Test full cycle: vitals → NEWS2 → Claude → Supabase    | ✅ (cred-gated) |
| Tune prompt, doctor-queue auto-open on transition      | ✅              |

**Deliverable:** Every agent cycle results in a correct Supabase row write + AI note in the DB. ✅

### Person 3 — Dashboard Core ⏳ in progress

**Goal:** React dashboard showing live patient grid with Realtime updates.

| Task                                                                          |
| ----------------------------------------------------------------------------- |
| Scaffold React app (`vite`), install Supabase JS                              |
| `lib/supabase.js` — client + Realtime hook on `patient_current_state`         |
| `PatientCard.jsx` — vitals, flag colour, **NEWS2 badge**, AI note, ack button |
| `PatientGrid.jsx` — sorted by NEWS2 score desc, summary stat bar              |
| Wire Realtime: confirm live updates on Supabase row change                    |
| Polish layout, edge cases (no data, loading state)                            |

### Person 4 — Doctor Queue & Demo Polish ⏳ in progress

**Goal:** Doctor call queue UI + end-to-end demo preparation.

| Task                                                                              |
| --------------------------------------------------------------------------------- |
| `DoctorQueue.jsx` — pending calls, urgency badges, status updates                 |
| Realtime subscription on `doctor_calls`                                           |
| Acknowledge flow — button on PatientCard writes to `flags.acknowledged`           |
| Demo script: tune `VITALWATCH_SCENARIO_*` env vars for sepsis & bradycardia beats |
| Update `README.md` — setup + demo                                                 |
| End-to-end rehearsal, screenshots for slides                                      |

### 17.1 Phase 1.5 work split (passive + human-in-the-loop)

Parallelisable across the same four people. Maps 1:1 onto the four items in §6.5.

| Item                                  | Owner   | Files touched                                                                                                                                                                                                                                                                                        |
| ------------------------------------- | ------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Preliminary NEWS2 score**        | P1      | `agents/thresholds.py` (add `score_news2_partial()` — same scoring, only the 5 passive params, defaults `on_oxygen=False, consciousness="A"`); `agents/messages.py` (`preliminary_news2_score: int`, `preliminary_news2_risk: str`); `agents/patient_agent.py` (compute & emit alongside full score) |
| **2a. Freshness schema**              | P2      | `supabase/schema.sql` — add `nibp_set_at`, `temp_set_at`, `o2_set_at`, `acvpu_set_at` `TIMESTAMPTZ` to `patient_current_state`; mirror in `vitals_readings` if needed; bump `supabase/README.md`                                                                                                     |
| **2b. Freshness write-side**          | P1 + P2 | `agents/supabase_writer.py` — only stamp `nibp_set_at` / `temp_set_at` when an actual fresh reading arrives (need a "value-changed" check or a generation counter from the patient agent); never overwrite `o2_set_at` / `acvpu_set_at` from the agent loop                                          |
| **3a. Floor-agent staff endpoint**    | P1      | `agents/floor_aggregator.py` — small `aiohttp` (or uAgents built-in HTTP) handler `POST /staff/patient/{id}/manual` that upserts the supplied fields + stamps the matching `*_set_at` and lets Supabase Realtime fan it out                                                                          |
| **3b. Inline manual controls**        | P3      | `dashboard/src/components/PatientCard.jsx` — 3-control strip per card: ACVPU dropdown, O₂ toggle + flow input, "Manual override" expanding BP / temp inputs; calls the new endpoint                                                                                                                  |
| **3c. Freshness badges on UI**        | P3      | `dashboard/src/components/FreshnessBadge.jsx` (new) — green / amber / red under each field driven by `*_set_at` deltas                                                                                                                                                                               |
| **4. Staff Agent overdue-check stub** | P1      | `agents/staff_agent.py` (new, ~80 lines) — runs in same Bureau, periodic check on `patient_current_state.acvpu_set_at` / `o2_set_at`, emits a soft `OverdueCheck` message → upserts a `due_check` field on the row → dashboard renders an "ACVPU due" pill                                           |
| **Demo beat wiring**                  | P4      | Demo script: pre-stage Maria Gonzalez at NEWS2 = 4, scripted single ACVPU=V tap, validate the auto-opened doctor call lands in the queue UI within ~1 s                                                                                                                                              |

**Recommended order** so each owner is unblocked: P2 ships 2a → P1 ships 1, 2b, 3a in one pass → P3 ships 3b, 3c against the new endpoint → P1 ships 4 → P4 wires the demo beat.

**Hard cuts if scope tightens:** drop item 4 (Staff Agent stub) first — items 1, 2 and 3 are enough for the killer demo beat. Drop item 4 + the freshness badges (3c) second; the demo still lands on the ACVPU=V tap alone.

---

## 18. Integration Checkpoints

| Time   | Milestone                                                       | Owner              |
| ------ | --------------------------------------------------------------- | ------------------ |
| T+1:30 | Mock vitals flowing patient agent → console                     | P1 ✅              |
| T+2:00 | Supabase `patient_current_state` receiving writes               | P2 ✅ (cred-gated) |
| T+2:30 | Dashboard displaying static Supabase data                       | P3                 |
| T+3:00 | Full chain: agent → Supabase → Realtime → dashboard live update | P1+P2+P3           |
| T+3:30 | Critical NEWS2 → AI note → flag card on dashboard               | P2+P3              |
| T+4:00 | Doctor queue visible and reactive                               | P4                 |
| T+4:30 | End-to-end demo rehearsal                                       | All                |
| T+5:00 | 🎤 Demo                                                         |

**Phase 1.5 add-ons** (run in parallel with Phase 1 once `patient_current_state` exists):

| Time (relative) | Milestone                                                                                         | Owner |
| --------------- | ------------------------------------------------------------------------------------------------- | ----- |
| Δ+0:30          | Schema migration: 4 `*_set_at` columns live in Supabase                                           | P2    |
| Δ+1:15          | Patient agent emitting `preliminary_news2_score` + writer stamping freshness only on real updates | P1    |
| Δ+2:00          | Floor agent `POST /staff/patient/{id}/manual` endpoint reachable from dashboard                   | P1    |
| Δ+3:00          | Inline ACVPU / O₂ / override controls + freshness badges live on dashboard                        | P3    |
| Δ+3:30          | ACVPU = V tap → NEWS2 jumps 4 → 7 → doctor_call row open → queue UI updates                       | All   |
| Δ+4:00          | Staff Agent stub raising "ACVPU due" pill                                                         | P1    |

---

## 19. Phase 1 Demo Flow (5-minute script)

1. Open the dashboard — 4 patients visible. Cards sorted by NEWS2: Room 305 (NEWS2=5, _critical, bradycardia_) at the top, Room 303 (NEWS2=0, _stable_) at the bottom.
2. Trigger sepsis scenario for Room 301: `VITALWATCH_SCENARIO_301=sepsis`. Within 10 s the card flips from _watch (NEWS2=2)_ to _critical (NEWS2=6)_, the AI note updates to a sepsis-recognition message, and a new urgent doctor call appears in the queue.
3. Show the Patient Agent log: **NEWS2 breakdown** explaining which parameters drove the score (`spo2=1, hr=2, rr=2, temp=1`).
4. Show the Floor Aggregator log: **transition detected, flags + doctor_calls inserted**.
5. Trigger bradycardia + on-oxygen for Room 305: `VITALWATCH_OXYGEN_305=1`. NEWS2 jumps from 5 (medium) → 7 (high). Card flashes high-risk.
6. Open the Supabase table editor in another tab — `vitals_readings` is filling row by row in real time, fully audit-trailed.
7. Click "Call Doctor" / "Acknowledge" → entries update in the queue.
8. **(Phase 1.5 beat — if shipped)** Walk to Maria Gonzalez (Room 304), currently sitting at _watch (NEWS2 = 4)_ from purely passive sensing — note the freshness badges showing BP fresh (3 m), ACVPU stale (47 m). Tap **ACVPU = V** on her card. The card flips to _critical (NEWS2 = 7)_ in under a second, the freshness badge resets to "now," and a new urgent doctor call slides into the queue. _"Five of seven NEWS2 inputs are continuously sensed — the score you saw a moment ago. The two that need a human take one tap, on the same screen the nurse is already standing in front of. That's the human-in-the-loop story."_
9. **Land the bigger story:** "This is one ward, two agent types, and NEWS2. The same architecture extends to Bed Agents, Lab Agents, Pharmacy — that's Nucleus, the autonomous hospital OS. Phase 1 proves it works on the most safety-critical layer."

---

## 20. Why This Wins

| Factor                                       | Why it matters                                                                                            |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **Scale**                                    | Touches every department — judges see the full vision, not a toy                                          |
| **Sponsor stacks used deeply**               | Fetch.ai for the agent mesh, Claude as the reasoning surface, Supabase for state + Realtime fan-out |
| **Emotionally resonant**                     | Every judge has been in a hospital. They've felt the chaos                                                |
| **Ethically clean**                          | Doctors still make medical decisions. Nucleus handles only operations                                     |
| **Real ROI numbers**                         | Bed misallocation alone costs U.S. hospitals an estimated $20bn / year                                    |
| **Architecturally proven, not just a slide** | Phase 1 ships a real, NEWS2-validated agent mesh — not a mockup                                           |
| **Extendable roadmap**                       | Each new agent reuses Phase 1 primitives; no rewrites needed                                              |

---

## 21. MVP Scope vs. Stretch

### Phase 1 MVP (must ship in 5 h)

- ✅ Patient agents with mock data, NEWS2 evaluation, Claude notes
- ✅ Floor aggregator writing to Supabase
- ⏳ Dashboard with live Realtime updates
- ⏳ Doctor call queue + acknowledge flow
- ⏳ 2 demo scenarios polished

### Stretch goals

- Trend graph per patient (last 20 readings from `vitals_readings`)
- Multi-floor selector in dashboard
- NEWS2 trend mini-chart on patient card
- Acknowledge flow with nurse-name capture
- Simple "Bed Agent" stub that responds to `flags` table to demonstrate Phase 2 in 30 lines
- Claude-powered handoff brief generator (1-button per patient)
- Multilingual discharge summary demo

### Phase 2+ (post-hackathon)

See §7 roadmap. Same architecture, more agents.

---

## 22. License & Credits

Hackathon prototype. NEWS2 thresholds © Royal College of Physicians 2017 — implementation is original; clinical use requires licensed sign-off.

Built on Fetch.ai uAgents · Anthropic Claude · Supabase.
