# VitalWatch Agents (Person 1 deliverable)

Multi-agent layer for the hackathon: 4 Patient Agents + 1 Floor
Aggregator Agent, all on Fetch.AI uAgents, with mock vitals
flowing end-to-end.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# bring up everything in one process (floor + 4 patient agents)
python -m scripts.run_all
```

For the demo you'll want fast polling and verbose logs:

```bash
PATIENT_POLL_SECONDS=2.0 VITALWATCH_DEBUG=1 python -m scripts.run_all
```

## What you should see

Within ~5s of startup the floor agent prints a snapshot every 15s,
including the **NEWS2** score and risk band for every patient:

```
---- floor snapshot ----
  [CRITICAL] room 305 James Okafor       HR  47.5  BP 107.5/69.1   SpO2 90.0 O2  T 36.8  RR 13.3  ACVPU=A  NEWS2= 7 (high)
  [CRITICAL] room 301 Maria Gonzalez     HR  88.6  BP 124.2/73.9   SpO2 94.1     T 37.0  RR 15.2  ACVPU=V  NEWS2= 4 (medium)
  [   WATCH] room 302 Lin Yao            HR  90.3  BP 127.4/78.8   SpO2 94.1     T 37.0  RR 17.6  ACVPU=A  NEWS2= 1 (low)
  [  STABLE] room 303 David Mehta        HR  76.2  BP 127.2/69.0   SpO2 97.2     T 36.6  RR 13.4  ACVPU=A  NEWS2= 0 (none)
------------------------
```

Each polling cycle also logs the message round-trip with the
contributing parameter scores:

```
[patient_room_305]: -> floor: room 305 NEWS2=7 (high); driven by spo2=3, oxygen=2, bp_sys=1, hr=1
[floor_aggregator_3west]: <- room 305 (James Okafor) flag=critical NEWS2=7 (high) ...
[patient_room_305]: <- ack from floor: 2 critical / 1 watch / 4 total ...
```

## NEWS2 scoring

The flag in every snapshot is derived from **NEWS2** — the UK Royal
College of Physicians' National Early Warning Score 2 (2017), the
de-facto standard EWS in the NHS. See `agents/thresholds.py` for
the implementation, and the RCP source:
<https://www.rcp.ac.uk/media/news2-report.pdf>.

Score → flag mapping used by the dashboard:

| NEWS2 aggregate | Risk band | UI flag    |
|-----------------|-----------|------------|
| 0               | none      | `stable`   |
| 1–4 (no single param = 3) | low | `watch` |
| 3 in any single parameter, OR 5–6 | medium | `critical` |
| ≥ 7             | high      | `critical` |

## Demo controls

Override per-room scenarios at launch time:

```bash
VITALWATCH_SCENARIO_301=sepsis \
VITALWATCH_SCENARIO_303=hypoxia \
PATIENT_POLL_SECONDS=2.0 \
python -m scripts.run_all
```

Available scenarios (see `agents/mock_vitals.py`):

| Scenario      | Typical NEWS2 | What it shows                    |
|---------------|---------------|----------------------------------|
| `baseline`    | 0             | All vitals stable                |
| `watch`       | 1–2 (low)     | SpO2 in watch band               |
| `sepsis`      | 5–7 (med/high)| HR↑, temp↑, RR↑                  |
| `bradycardia` | 4–6 (medium)  | HR↓ + SpO2↓                      |
| `hypoxia`     | 8+ (high)     | SpO2↓ + RR↑ + HR↑                |

You can also drive NEWS2 inputs that the bedside monitor doesn't
measure — supplemental oxygen and consciousness level (ACVPU) — per
room, without touching the vitals stream:

```bash
# Put room 305 on supplemental O2 (adds 2 to NEWS2 score):
VITALWATCH_OXYGEN_305=1 python -m scripts.run_all

# Make room 301 voice-responsive (single param = 3 → critical):
VITALWATCH_ACVPU_301=V python -m scripts.run_all

# Switch room 302 to NEWS2 Scale 2 (COPD / hypercapnic target):
VITALWATCH_SPO2SCALE_302=2 python -m scripts.run_all
```

ACVPU letters: `A` alert, `C` new confusion, `V` voice, `P` pain,
`U` unresponsive. Anything other than `A` scores 3.

## Running one room standalone (Agentverse / multi-machine)

```bash
# terminal 1 — floor agent
python -m agents.floor_aggregator
# copy the printed agent address, then in terminal 2:
export FLOOR_AGENT_ADDRESS=agent1q...
python -m agents.patient_agent --room 305 --port 8005 --scenario bradycardia
```

## Hooks for Persons 2/3/4

- **Person 2 (Supabase + Claude)** — implemented; see
  `supabase/README.md` for setup. The agents already call
  `agents/supabase_writer.persist_update()` on every inbound
  message and `agents/claude_notes.call_claude_for_note()` on every
  poll. Both gracefully no-op when their credentials are missing,
  so the demo continues to work in any state.

- **Person 3 (Dashboard)**
  - The floor agent's snapshot already matches the column order the
    dashboard cards need: room, name, HR, BP, SpO2, T, RR, flag.
  - The wire model (`agents/messages.py::VitalsUpdate`) carries the
    pre-computed NEWS2 fields — show `news2_score` as a coloured
    badge (none / low / medium / high) on each card. Person 2 should
    add `news2_score INT`, `news2_risk TEXT`, `on_oxygen BOOL`,
    `consciousness TEXT` columns to `patient_current_state`.
  - Realtime updates land on `patient_current_state` once Person 2
    wires the Supabase write.

- **Person 4 (Doctor queue + demo)**
  - Use scenario env vars above to trigger the sepsis (room 301)
    and bradycardia (room 305) demo beats.
  - Doctor-call queue write should happen inside
    `handle_patient_update` in `floor_aggregator.py` — there's a
    natural place for it right after `persist_to_supabase(msg)`.

## Files

```
agents/
  messages.py            # VitalsUpdate / VitalsAck wire models (carry NEWS2)
  thresholds.py          # NEWS2 (RCP 2017) — score_news2() + evaluate_flag()
  mock_vitals.py         # VitalsStream + scenario presets + DEMO_ROSTER
  patient_agent.py       # build_patient_agent(...) + CLI
  floor_aggregator.py    # floor_agent + persist_to_supabase() dispatch
  claude_notes.py        # Anthropic note generator (cached, fail-safe)
  supabase_writer.py     # patient_current_state / vitals_readings /
                         #   flags / doctor_calls writes
supabase/
  schema.sql             # full DB schema (paste into Supabase SQL editor)
  seed.sql               # demo floor + 4 patients (UUIDs match DEMO_ROSTER)
  README.md              # 5-minute backend setup
scripts/
  run_all.py             # Bureau: floor + 4 patient agents in one process
```
