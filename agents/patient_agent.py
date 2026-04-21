"""
Patient Agent factory.

A single Patient Agent monitors one room: every `PATIENT_POLL_SECONDS`
seconds it asks its `VitalsStream` for a fresh reading, runs it through
`evaluate_flag()`, optionally calls Claude for a 1-line clinical note,
and sends a `VitalsUpdate` to the Floor Aggregator.

This file exposes `build_patient_agent(...)` so the same code can be
used three different ways:

  1. `python -m agents.patient_agent`           -> single demo agent (room 301)
  2. `python -m scripts.run_all`                -> floor + 4 patients in one
                                                   asyncio loop (Person 1's
                                                   default end-to-end run)
  3. `python -m agents.patient_agent --room 305 --port 8005`
                                                -> standalone process for one
                                                   room (used when distributing
                                                   across machines / Agentverse)
"""

from __future__ import annotations

import argparse
import os
from typing import Optional

from dotenv import load_dotenv
from uagents import Agent, Context

from .messages import VitalsAck, VitalsUpdate
from .mock_vitals import DEMO_ROSTER, VitalsStream
from .thresholds import score_news2, score_news2_partial

load_dotenv()


def _maybe_call_claude(
    vitals: dict,
    flag: str,
    *,
    patient_id: str,
    news2_score: int,
    news2_risk: str,
    on_oxygen: bool,
    consciousness: str,
) -> str:
    """
    Defer to ``agents.claude_notes.call_claude_for_note`` if the
    module is importable and ``ANTHROPIC_API_KEY`` is set; otherwise
    return a deterministic stub. ``claude_notes`` itself caches per
    ``(patient_id, flag)`` so this is cheap to call every tick.
    """
    try:
        from .claude_notes import call_claude_for_note  # type: ignore
    except Exception:
        return _stub_note(vitals, flag)
    try:
        return call_claude_for_note(
            vitals,
            flag,
            patient_id=patient_id,
            news2_score=news2_score,
            news2_risk=news2_risk,
            on_oxygen=on_oxygen,
            consciousness=consciousness,
        )
    except Exception:
        return _stub_note(vitals, flag)


def _stub_note(vitals: dict, flag: str) -> str:
    if flag == "critical":
        return (
            f"CRITICAL: HR {vitals['hr']:.0f}, SpO2 {vitals['spo2']:.0f}%, "
            f"T {vitals['temp_c']:.1f}C. Escalate to attending."
        )
    if flag == "watch":
        return (
            f"Watch: borderline vitals (HR {vitals['hr']:.0f}, "
            f"SpO2 {vitals['spo2']:.0f}%). Recheck in 10 min."
        )
    return "Stable. Continue routine monitoring."


def build_patient_agent(
    *,
    patient_id: str,
    room: str,
    full_name: str,
    scenario: str,
    port: int,
    floor_address: Optional[str] = None,
    poll_seconds: Optional[float] = None,
) -> Agent:
    """Construct (but do not start) a uAgent for a single patient room."""
    poll = poll_seconds or float(os.environ.get("PATIENT_POLL_SECONDS", "10.0"))
    floor_address = floor_address or os.environ.get("FLOOR_AGENT_ADDRESS", "")

    seed = f"vitalwatch-patient-{room}-demo-seed"
    agent = Agent(
        name=f"patient_room_{room}",
        seed=seed,
        port=port,
        endpoint=[f"http://127.0.0.1:{port}/submit"],
    )

    stream = VitalsStream(
        patient_id=patient_id,
        room=room,
        full_name=full_name,
        scenario=scenario,
        # Deterministic seed per room keeps demos reproducible.
        seed=hash(room) & 0xFFFFFFFF,
    )

    debug = os.environ.get("VITALWATCH_DEBUG", "0") == "1"

    # NEWS2 inputs that the bedside monitor doesn't measure. Defaults match
    # "patient on room air, fully alert". Person 4's demo script can flip
    # these per room via env vars to drive the score up without touching
    # the vitals stream:
    #     VITALWATCH_OXYGEN_305=1
    #     VITALWATCH_ACVPU_301=V        # voice-responsive (scores 3)
    on_oxygen = os.environ.get(f"VITALWATCH_OXYGEN_{room}", "0") == "1"
    consciousness = os.environ.get(f"VITALWATCH_ACVPU_{room}", "A").upper()
    if consciousness not in {"A", "C", "V", "P", "U"}:
        consciousness = "A"
    spo2_scale = int(os.environ.get(f"VITALWATCH_SPO2SCALE_{room}", "1"))

    @agent.on_event("startup")
    async def _startup(ctx: Context) -> None:
        ctx.logger.info(
            f"patient agent ready: room={room} name={full_name} "
            f"scenario={scenario} port={port}"
        )
        ctx.logger.info(f"  agent address : {agent.address}")
        if not floor_address:
            ctx.logger.warning(
                "FLOOR_AGENT_ADDRESS is empty — vitals will not be sent. "
                "Start the floor aggregator first and export its address."
            )

    @agent.on_interval(period=poll)
    async def _monitor(ctx: Context) -> None:
        if not floor_address:
            return
        vitals = stream.next()
        result = score_news2(
            vitals,
            on_oxygen=on_oxygen,
            consciousness=consciousness,  # type: ignore[arg-type]
            spo2_scale=spo2_scale,  # type: ignore[arg-type]
        )
        # Phase 1.5: same vitals scored under "passive only"
        # assumptions (room air, ACVPU=A). The floor uses this as
        # the baseline reading when the matching manual fields are
        # stale or absent.
        partial = score_news2_partial(
            vitals,
            spo2_scale=spo2_scale,  # type: ignore[arg-type]
        )
        note = _maybe_call_claude(
            vitals,
            result.flag,
            patient_id=patient_id,
            news2_score=result.score,
            news2_risk=result.risk,
            on_oxygen=on_oxygen,
            consciousness=consciousness,
        )

        if debug or result.flag != "stable":
            ctx.logger.info(f"-> floor: room {room} {result.explanation}")

        await ctx.send(
            floor_address,
            VitalsUpdate(
                patient_id=patient_id,
                room=room,
                full_name=full_name,
                hr=vitals["hr"],
                bp_sys=vitals["bp_sys"],
                bp_dia=vitals["bp_dia"],
                spo2=vitals["spo2"],
                temp_c=vitals["temp_c"],
                rr=vitals["rr"],
                flag=result.flag,
                ai_note=note,
                scenario=stream.scenario,
                news2_score=result.score,
                news2_risk=result.risk,
                on_oxygen=on_oxygen,
                consciousness=consciousness,
                spo2_scale=spo2_scale,
                preliminary_news2_score=partial.score,
                preliminary_news2_risk=partial.risk,
            ),
        )

    @agent.on_message(model=VitalsAck)
    async def _on_ack(ctx: Context, sender: str, msg: VitalsAck) -> None:
        if debug:
            ctx.logger.info(
                f"<- ack from floor: {msg.floor_status} @ {msg.received_at}"
            )

    return agent


def _cli() -> None:
    p = argparse.ArgumentParser(description="Run a single VitalWatch patient agent.")
    p.add_argument("--room", default="301")
    p.add_argument("--port", type=int, default=8001)
    p.add_argument("--scenario", default=None,
                   help="baseline | watch | sepsis | bradycardia | hypoxia")
    args = p.parse_args()

    spec = next((r for r in DEMO_ROSTER if r["room"] == args.room), None)
    if spec is None:
        raise SystemExit(
            f"Unknown room {args.room!r}. Known rooms: "
            f"{[r['room'] for r in DEMO_ROSTER]}"
        )
    scenario = args.scenario or spec["scenario"]

    agent = build_patient_agent(
        patient_id=spec["patient_id"],
        room=spec["room"],
        full_name=spec["full_name"],
        scenario=scenario,
        port=args.port,
    )
    agent.run()


if __name__ == "__main__":
    _cli()
