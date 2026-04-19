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

| Layer           | Technology                                   | Purpose                                 |
| --------------- | -------------------------------------------- | --------------------------------------- |
| Agent framework | Fetch.ai uAgents 0.24+                       | All department agents, async messaging  |
| Agent discovery | Almanac contract / Agentverse Mailbox        | Cross-machine reachability              |
| Database        | Supabase (PostgreSQL)                        | Persistent state, schema, RLS           |
| Realtime        | Supabase Realtime                            | WebSocket push to dashboard             |
| AI reasoning    | Anthropic Claude (Sonnet)                    | Notes, summaries, NL query, escalations |
| Frontend        | React + Vite + Supabase JS                   | Nurse station + executive dashboards    |
| Analytics       | Supabase Postgres + Claude-generated reports | Operational & executive reporting       |
| Mock data       | `mock_vitals.py` scenario presets            | Demo-ready vital streams                |

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

## 17. Work Division — Team of 4

Four people, four vertical slices. Each owner takes one layer of the system end-to-end across what's shipped (Phase 1), what's in flight (Phase 1.5), and what they'll seed for the post-hackathon roadmap (Phase 2+, see §7). Where two slices have to meet, the integration is called out explicitly.

### 17.1 At a glance

| Role                          | Owner   | Layer owned                                             |    Phase 1     |  Phase 1.5   | Phase 2 seed (roadmap)                         |
| ----------------------------- | ------- | ------------------------------------------------------- | :------------: | :----------: | ---------------------------------------------- |
| **P1 — Agent Infrastructure** | _Manas_ | uAgents mesh, NEWS2, Bureau, staff HTTP endpoint        |   ✅ shipped   | 🟡 in flight | Bed / ER Triage / Lab agent skeletons          |
| **P2 — Data & AI Layer**      | _name_  | Supabase schema, persistence writer, Claude prompts     |   ✅ shipped   | 🟡 in flight | Lab results, pharmacy inventory, bed snapshots |
| **P3 — Dashboard Frontend**   | _Jacob_ | React app, Realtime glue, manual controls, freshness UI |   ✅ shipped   | 🟡 in flight | Bed heatmap, ER queue card, NL query box       |
| **P4 — Demo & Integration**   | _name_  | End-to-end script, rehearsal, slide deck, screenshots   | ⏳ in progress | 🟡 in flight | Demo video, sponsor-tag write-up, one-pager    |

Phase 1.5 maps 1:1 onto the four items in §6.5 — the table below restates them per owner so nobody has to cross-reference.

---

### 17.2 P1 — Agent Infrastructure

> Owns every Python agent process, the inter-agent message contracts (`agents/messages.py`), the `Bureau` runner (`scripts/run_all.py`), and the Floor Aggregator's HTTP surface for human-in-the-loop input.

| Phase | Status | Tasks                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 |
| ----- | :----: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     |   ✅   | uAgents Bureau hosting 4 Patient Vitals Agents + 1 Floor Aggregator; `mock_vitals.py` with 5 clinical scenarios; **NEWS2 (RCP 2017)** scoring in `thresholds.py`; per-room scenario / oxygen / ACVPU env overrides; graceful degrade when Anthropic / Supabase creds are absent                                                                                                                                                                                                                                                                                                                                                                                                                       |
| 1.5   |   🟡   | **(item 1)** Add `score_news2_partial()` + `preliminary_news2_score` / `preliminary_news2_risk` fields on `VitalsUpdate`; emit alongside the full score every tick. **(item 2b — co-owned with P2)** Stamp `nibp_set_at` / `temp_set_at` in `supabase_writer.py` only when a fresh value actually arrives (value-changed check). **(item 3a)** Mount a small HTTP handler on the Floor Aggregator's Bureau server: `POST /staff/patient/{id}/manual` upserts O₂ / ACVPU / overrides + stamps the matching `*_set_at`. **(item 4)** New `agents/staff_agent.py` stub running in the same Bureau, polling `acvpu_set_at` / `o2_set_at` and raising an `OverdueCheck` event when either exceeds protocol |
| 2+    |   ⏸    | Skeletons for Bed / ER Triage / Lab agents reusing the Phase 1 primitives (interval polling, transition-driven side effects, supabase_writer dispatch)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |

**Deliverable for the demo:** every patient agent emits both a full and a preliminary NEWS2; the Floor Aggregator accepts manual updates over HTTP and the Staff Agent stub raises overdue flags.

---

### 17.3 P2 — Data & AI Layer

> Owns the Supabase project (schema, RLS, Realtime channels), the `supabase_writer.py` persistence pipeline, and the Claude client + prompts in `claude_notes.py`.

| Phase | Status | Tasks                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----- | :----: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     |   ✅   | `supabase/schema.sql` + `seed.sql` covering `patients`, `patient_current_state`, `vitals_readings`, `flags`, `doctor_calls`, `staff` (with NEWS2 columns); `supabase_writer.py` with upsert / insert / transition-only logic; `claude_notes.py` with per-patient cache, 60 s refresh on non-stable patients, fail-safe stub on missing key                                                                                                                                                                                                                                   |
| 1.5   |   🟡   | **(item 2a)** Migration adding `nibp_set_at`, `temp_set_at`, `o2_set_at`, `acvpu_set_at` `TIMESTAMPTZ` columns to `patient_current_state` (and matching columns on `vitals_readings` if trends are needed); update `supabase/README.md` with the migration steps. **(item 2b — co-owned with P1)** Make sure the writer never overwrites `o2_set_at` / `acvpu_set_at` from the agent loop — those columns belong to the staff endpoint. **Optional:** extend the Claude prompt template to mention freshness ("BP from 12 min ago") so the AI note acknowledges stale inputs |
| 2+    |   ⏸    | Schema for `lab_results` + reference ranges, `pharmacy_inventory` + dispense events, `beds` + `bed_history`                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |

**Deliverable for the demo:** the schema migration is applied to the live Supabase project, every Phase 1.5 write lands in the right column with the right freshness stamp, and the AI note adapts to stale-vs-fresh inputs.

---

### 17.4 P3 — Dashboard Frontend

> Owns the entire React + Vite app: live patient grid, doctor queue, and the new manual-input controls + freshness badges that close the human-in-the-loop story.

| Phase | Status | Tasks                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| ----- | :----: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1     |   ✅   | Vite + Supabase JS scaffold; `lib/supabase.js` Realtime hook on `patient_current_state` and `doctor_calls`; `PatientCard.jsx`, `PatientGrid.jsx`, `FlagBadge.jsx`, `SummaryBar.jsx`, `DoctorQueue.jsx`; `lib/mockData.js` fallback so the dashboard renders without backend creds                                                                                                                                                                                                                                                                                                                                                                                                         |
| 1.5   |   🟡   | **(item 3b)** 3-control strip on each `PatientCard`: ACVPU dropdown (A / C / V / P / U), supplemental-O₂ toggle + flow-rate input, and a collapsible "Manual override" exposing BP / temp inputs — each `POST`s to P1's `/staff/patient/{id}/manual`. **(item 3c)** New `FreshnessBadge.jsx` rendering green → amber → red under each field, driven by `*_set_at` deltas (green < 15 min, amber 15–60 min, red > 60 min, configurable per field). Surface the "ACVPU due" pill produced by P1's Staff Agent stub. Show **preliminary NEWS2** when manual fields are stale, and the **full NEWS2** when fresh — small toggle in the corner of each card so the judges can see both at once |
| 2+    |   ⏸    | Bed-occupancy heatmap, ER queue card, NL query box wired to Claude, weekly-report viewer (the Command Center surfaces from §4)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |

**Deliverable for the demo:** every patient card has working manual controls and freshness badges; Realtime fan-out re-renders the score in under a second after a tap.

---

### 17.5 P4 — Demo & Integration Lead

> Owns the end-to-end script, the rehearsal cycle, and any cross-cutting glue that doesn't belong to a single owner. Responsible for the slide deck, the demo screenshots, and the on-stage narration.

| Phase     | Status | Tasks                                                                                                                                                                                                                                                                                                                                                                                  |
| --------- | :----: | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1         |   ⏳   | Tune `VITALWATCH_SCENARIO_*` env vars so the sepsis (Room 301) and bradycardia (Room 305) beats fire reliably during the 5-minute window; capture screenshots of patient grid, doctor queue, and the agent log; draft the §18 walkthrough into talking points                                                                                                                          |
| 1.5       |   🟡   | **(demo beat)** Pre-stage Maria Gonzalez at NEWS2 = 4 from purely passive vitals; rehearse the single ACVPU = V tap that drives the score to 7 and auto-opens a doctor call; verify Realtime latency on a second connected screen. Update the slide deck to lead with the "5 of 7 NEWS2 inputs are sensed passively, 2 take one tap" framing — this is the strongest line in the pitch |
| post-demo |   ⏸    | Trim a 90-second demo video for submission; one-page architecture explainer; sponsor-tag README badges                                                                                                                                                                                                                                                                                 |

**Deliverable for the demo:** a rehearsed 5-minute walkthrough where every beat lands on time, plus a backup version that still works if Phase 1.5 has been cut down (see §17.7).

---

### 17.6 Dependency map (who unblocks whom)

```
        P2 (2a · schema migration)
         │
         ├──► P1 (1 · preliminary score)         ──► P4 (demo beat)
         │
         ├──► P1 + P2 (2b · freshness write)     ──► P3 (3c · badges)
         │
         └──► P1 (3a · /staff endpoint)          ──► P3 (3b · controls)  ──► P4 (demo beat)
                                                                                │
                                                  P1 (4 · staff agent stub) ────┘  (independent, ships last)
```

**One bottleneck only:** P2's schema migration (item 2a). Everything else parallelises after that. P3 can build the controls (3b) against a mocked `fetch` while P1 finishes the endpoint and swap the URL when it lands.

---

### 17.7 Cut order if scope tightens

Drop in this order — each cut still leaves a coherent demo:

1. **Cut item 4 (Staff Agent stub).** "ACVPU due" pill goes away; passive sensing + the manual-tap demo beat are unaffected.
2. **Cut item 3c (Freshness badges).** The numeric values still update every 10 s; you just lose the green / amber / red dots.
3. **Cut the "Manual override" sub-control (part of 3b).** Keep just the ACVPU dropdown + O₂ toggle. The killer demo beat (ACVPU = V tap → NEWS2 → 7) still works.
4. **Cut all of Phase 1.5.** Phase 1 alone is still a winning demo — you lose the human-in-the-loop story but keep the autonomous-agents story.

The reverse order — what to ship first if you only get 2 hours of Phase 1.5 done — is: `2a → 1 → 3a → 3b (ACVPU only) → demo beat`. That five-step minimum is enough to land the headline moment.

---

## 18. Phase 1 Demo Flow (5-minute script)

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

## 19. Why This Wins

| Factor                                       | Why it matters                                                                                      |
| -------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| **Scale**                                    | Touches every department — judges see the full vision, not a toy                                    |
| **Sponsor stacks used deeply**               | Fetch.ai for the agent mesh, Claude as the reasoning surface, Supabase for state + Realtime fan-out |
| **Emotionally resonant**                     | Every judge has been in a hospital. They've felt the chaos                                          |
| **Ethically clean**                          | Doctors still make medical decisions. Nucleus handles only operations                               |
| **Real ROI numbers**                         | Bed misallocation alone costs U.S. hospitals an estimated $20bn / year                              |
| **Architecturally proven, not just a slide** | Phase 1 ships a real, NEWS2-validated agent mesh — not a mockup                                     |
| **Extendable roadmap**                       | Each new agent reuses Phase 1 primitives; no rewrites needed                                        |

---

## 20. MVP Scope vs. Stretch

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

## 21. License & Credits

Hackathon prototype. NEWS2 thresholds © Royal College of Physicians 2017 — implementation is original; clinical use requires licensed sign-off.

Built on Fetch.ai uAgents · Anthropic Claude · Supabase.
