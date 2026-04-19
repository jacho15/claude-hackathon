"""
Floor Aggregator Agent.

Subscribes to `VitalsUpdate` messages from every Patient Agent on
the floor, keeps an in-memory snapshot of each room's current
state, and prints a compact ranked summary every few seconds.

Person 2 owns the Supabase write path: there is a single
`persist_to_supabase()` hook that's a no-op today and becomes the
real upsert into `patient_current_state` (+ insert into
`vitals_readings`) once the credentials are wired in.

Run directly:
    python -m agents.floor_aggregator
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from uagents import Agent, Context

from .messages import VitalsAck, VitalsUpdate

load_dotenv()

FLAG_RANK = {"critical": 0, "watch": 1, "stable": 2}

floor_agent = Agent(
    name="floor_aggregator_3west",
    seed=os.environ.get("FLOOR_AGENT_SEED", "vitalwatch-floor-3west-demo-seed"),
    port=8100,
    endpoint=["http://127.0.0.1:8100/submit"],
)


# In-memory snapshot: {patient_id: dict(latest reading)}.
# This is the single source of truth the aggregator hands to Supabase.
floor_state: dict[str, dict] = {}


def persist_to_supabase(state: dict) -> None:
    """
    Hand the full snapshot to the Supabase writer. The writer is
    a no-op when SUPABASE_URL / *_KEY are missing, so calling this
    with no credentials just logs a one-time warning.

    Imported lazily so the mock-only Person 1 pipeline never has to
    have the supabase package installed.
    """
    try:
        from .supabase_writer import persist_update
    except Exception:
        return
    try:
        persist_update(state)
    except Exception as exc:
        # The writer already logs internally per-table; this is a
        # belt-and-braces guard so the floor agent loop stays alive
        # under any backend failure mode.
        ctx_logger = floor_agent._logger  # type: ignore[attr-defined]
        ctx_logger.warning(f"supabase persist failed: {exc}")


def _summary_line(state: dict) -> str:
    score = state.get("news2_score", 0)
    risk = state.get("news2_risk", "?")
    o2 = " O2" if state.get("on_oxygen") else "   "
    acvpu = state.get("consciousness", "A")
    return (
        f"  [{state['flag'].upper():>8}] room {state['room']:>3} "
        f"{state['full_name']:<18} "
        f"HR {state['hr']:>5.1f}  BP {state['bp_sys']:>5.1f}/{state['bp_dia']:<5.1f}  "
        f"SpO2 {state['spo2']:>4.1f}{o2}  T {state['temp_c']:>4.1f}  "
        f"RR {state['rr']:>4.1f}  ACVPU={acvpu}  "
        f"NEWS2={score:>2} ({risk})"
    )


def render_floor_snapshot() -> str:
    if not floor_state:
        return "  (no patient updates yet)"
    rows = sorted(
        floor_state.values(),
        key=lambda s: (FLAG_RANK.get(s["flag"], 9), s["room"]),
    )
    return "\n".join(_summary_line(r) for r in rows)


@floor_agent.on_event("startup")
async def announce(ctx: Context) -> None:
    ctx.logger.info("=" * 72)
    ctx.logger.info("Floor Aggregator (3 West) is up.")
    ctx.logger.info(f"  agent address : {floor_agent.address}")
    ctx.logger.info(f"  endpoint      : http://127.0.0.1:8100/submit")
    ctx.logger.info("Export this address so the patient agents can reach you:")
    ctx.logger.info(f"  export FLOOR_AGENT_ADDRESS={floor_agent.address}")
    ctx.logger.info("=" * 72)
    try:
        from .supabase_writer import clear_session_data
        clear_session_data()
    except Exception:
        pass


@floor_agent.on_message(model=VitalsUpdate, replies=VitalsAck)
async def handle_patient_update(
    ctx: Context, sender: str, msg: VitalsUpdate
) -> None:
    floor_state[msg.patient_id] = {
        "patient_id": msg.patient_id,
        "room": msg.room,
        "full_name": msg.full_name,
        "hr": msg.hr,
        "bp_sys": msg.bp_sys,
        "bp_dia": msg.bp_dia,
        "spo2": msg.spo2,
        "temp_c": msg.temp_c,
        "rr": msg.rr,
        "flag": msg.flag,
        "ai_note": msg.ai_note,
        "scenario": msg.scenario,
        "news2_score": msg.news2_score,
        "news2_risk": msg.news2_risk,
        "on_oxygen": msg.on_oxygen,
        "consciousness": msg.consciousness,
        "spo2_scale": msg.spo2_scale,
        "agent_address": sender,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }

    ctx.logger.info(
        f"<- room {msg.room} ({msg.full_name}) flag={msg.flag} "
        f"NEWS2={msg.news2_score} ({msg.news2_risk}) "
        f"from {sender[:18]}…"
    )

    persist_to_supabase(floor_state[msg.patient_id])

    crit_n = sum(1 for s in floor_state.values() if s["flag"] == "critical")
    watch_n = sum(1 for s in floor_state.values() if s["flag"] == "watch")
    await ctx.send(
        sender,
        VitalsAck(
            patient_id=msg.patient_id,
            received_at=datetime.now(timezone.utc).isoformat(),
            floor_status=f"{crit_n} critical / {watch_n} watch / "
                          f"{len(floor_state)} total",
        ),
    )


@floor_agent.on_interval(period=15.0)
async def print_snapshot(ctx: Context) -> None:
    ctx.logger.info("---- floor snapshot ----")
    for line in render_floor_snapshot().splitlines():
        ctx.logger.info(line)
    ctx.logger.info("------------------------")


if __name__ == "__main__":
    floor_agent.run()
