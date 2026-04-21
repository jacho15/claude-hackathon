"""
Facilities Agent.

Owns the cleaning queue (`cleaning_jobs` table). Receives
``RoomNeedsCleaning`` from the Bed Agent, opens a `cleaning_jobs`
row, runs a compressed-time cleaning timer (``BED_CLEANING_SECONDS``,
default 12s), and emits ``RoomReady`` back to the Bed Agent.

A real deployment would model crews, shifts, and concurrency; for
the demo we run jobs serially per room (which is also the realistic
assumption — one room can only be physically cleaned by one crew at
a time anyway).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from dotenv import load_dotenv
from uagents import Agent, Context

from .messages import RoomNeedsCleaning, RoomReady
from .supabase_writer import persist_cleaning_update

load_dotenv()

BED_CLEANING_SECONDS = float(os.environ.get("BED_CLEANING_SECONDS", "12"))
DEFAULT_CREW = os.environ.get("FACILITIES_CREW_LABEL", "Crew Alpha")

facilities_agent = Agent(
    name="facilities_agent_3west",
    seed=os.environ.get("FACILITIES_AGENT_SEED",
                        "vitalwatch-facilities-3west-demo-seed"),
    port=8204,
    endpoint=["http://127.0.0.1:8204/submit"],
)


# Cross-agent address (set by scripts.run_all)
TARGETS: dict[str, str] = {"bed": ""}


def set_targets(*, bed: str) -> None:
    TARGETS["bed"] = bed


# In-memory map of in-flight jobs.
jobs: dict[str, dict[str, Any]] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _send_message(destination: str, message: Any) -> None:
    if not destination:
        facilities_agent._logger.warning(  # type: ignore[attr-defined]
            f"no destination wired; dropping {type(message).__name__}"
        )
        return
    try:
        ctx = facilities_agent._build_context()  # type: ignore[attr-defined]
        await ctx.send(destination, message)
    except Exception as exc:
        facilities_agent._logger.warning(  # type: ignore[attr-defined]
            f"send failed ({type(message).__name__}): {exc}"
        )


async def _run_cleaning_job(*, job_id: str, room_number: str,
                            request_id: str) -> None:
    """Compressed cleaning timer. Updates cleaning_jobs at start, end,
    then notifies the Bed Agent via RoomReady."""

    eta_iso = (datetime.now(timezone.utc)
               + timedelta(seconds=BED_CLEANING_SECONDS)).isoformat()

    job = {
        "id":           job_id,
        "room_number":  room_number,
        "status":       "in_progress",
        "crew":         DEFAULT_CREW,
        "requested_at": _now_iso(),
        "eta":          eta_iso,
    }
    jobs[job_id] = job
    persist_cleaning_update(job)
    facilities_agent._logger.info(  # type: ignore[attr-defined]
        f"++ cleaning job {job_id[:8]} started (room {room_number}, "
        f"crew={DEFAULT_CREW}, eta={BED_CLEANING_SECONDS}s)"
    )

    await asyncio.sleep(BED_CLEANING_SECONDS)

    job.update(status="done", completed_at=_now_iso())
    persist_cleaning_update(job)
    facilities_agent._logger.info(  # type: ignore[attr-defined]
        f"== cleaning job {job_id[:8]} done (room {room_number})"
    )

    await _send_message(TARGETS["bed"], RoomReady(
        room_number=room_number,
        request_id=request_id,
        ready_at=_now_iso(),
    ))


@facilities_agent.on_message(model=RoomNeedsCleaning)
async def handle_room_needs_cleaning(
    ctx: Context, sender: str, msg: RoomNeedsCleaning
) -> None:
    job_id = str(uuid.uuid4())
    ctx.logger.info(
        f"<- RoomNeedsCleaning room {msg.room_number} "
        f"req={msg.request_id[:8]}"
    )
    asyncio.create_task(_run_cleaning_job(
        job_id=job_id,
        room_number=msg.room_number,
        request_id=msg.request_id,
    ))


@facilities_agent.on_event("startup")
async def announce(ctx: Context) -> None:
    ctx.logger.info("=" * 72)
    ctx.logger.info("Facilities Agent (3 West) is up.")
    ctx.logger.info(f"  agent address  : {facilities_agent.address}")
    ctx.logger.info(f"  cleaning timer : {BED_CLEANING_SECONDS}s (compressed)")
    ctx.logger.info(f"  default crew   : {DEFAULT_CREW}")
    ctx.logger.info("=" * 72)


if __name__ == "__main__":
    facilities_agent.run()
