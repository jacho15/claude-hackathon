"""
Bed Agent — owns the `beds` table for one floor.

Responsibilities
----------------
* Maintains an in-memory inventory of beds (room_number -> snapshot)
  loaded once on startup from Supabase, then updated by the agent
  itself on every state transition.
* Exposes an HTTP endpoint on :8102 (`POST /bed/reserve`) that the
  dashboard hits when an inbound transfer needs a bed.
* Brokers between Discharge and Facilities to walk a room through
  ``occupied -> clinically_clear -> cleaning -> ready -> reserved``.
* Persists each transition via :mod:`agents.supabase_writer` so the
  dashboard's Bed Board sees every state change live via Realtime.

Wire model
----------
Inbound:
    HTTP POST /bed/reserve            (BedReservationRequest envelope)
    BedReleased                       (from Discharge Agent)
    RoomReady                         (from Facilities Agent)
Outbound:
    BedNeedRequest                    (-> Discharge Agent, when no
                                       bed is immediately freeable)
    RoomNeedsCleaning                 (-> Facilities Agent, when a
                                       clinically-clear bed exists
                                       and we want it cleaned NOW)

Compressed-time policy
----------------------
``BED_CLEANING_SECONDS`` / ``BED_TRANSPORT_SECONDS`` /
``BED_DISCHARGE_PAPERWORK_SECONDS`` are read at import time from the
environment (defaults: 12 / 8 / 4). The bed agent only needs the
cleaning value for ``cleaning_eta``; the rest are read by the
discharge / facilities agents.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from aiohttp import web
from dotenv import load_dotenv
from uagents import Agent, Context

from .messages import (
    BedNeedRequest,
    BedReleased,
    BedReservationRequest,
    DischargeRequest,
    RoomNeedsCleaning,
    RoomReady,
)
from .supabase_writer import (
    fetch_all_beds,
    persist_bed_update,
    persist_transfer_request,
)

load_dotenv()

BED_HTTP_PORT = int(os.environ.get("BED_HTTP_PORT", "8102"))
BED_CLEANING_SECONDS = float(os.environ.get("BED_CLEANING_SECONDS", "12"))

_CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age":       "86400",
}

bed_agent = Agent(
    name="bed_agent_3west",
    seed=os.environ.get("BED_AGENT_SEED", "vitalwatch-bed-3west-demo-seed"),
    port=8102 + 100,                     # uAgents protocol port (8202)
    endpoint=[f"http://127.0.0.1:{8102 + 100}/submit"],
)


# ---------------------------------------------------------------------------
# Cross-agent address discovery.
#
# scripts.run_all calls set_targets() AFTER all three Phase 2 agents
# are constructed (we need each other's addresses for ctx.send) but
# BEFORE bureau.run() — so handlers always see populated values.
# ---------------------------------------------------------------------------

TARGETS: dict[str, str] = {"discharge": "", "facilities": ""}


def set_targets(*, discharge: str, facilities: str) -> None:
    TARGETS["discharge"] = discharge
    TARGETS["facilities"] = facilities


# ---------------------------------------------------------------------------
# In-memory bed state. The DB is the source of truth on boot; after
# that this dict is, and we mirror every change via persist_bed_update.
# ---------------------------------------------------------------------------

bed_state: dict[str, dict[str, Any]] = {}                 # room_number -> snap
pending_transfers: list[dict[str, Any]] = []              # FIFO queue of
                                                          # transfer_requests
                                                          # waiting for a
                                                          # cleaning_clear/ready
                                                          # bed.


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _set_bed(room_number: str, **changes: Any) -> dict[str, Any]:
    """Merge ``changes`` into the in-memory snapshot and persist."""
    snap = bed_state.setdefault(room_number, {"room_number": room_number})
    snap.update(changes)
    snap["last_change"] = _now_iso()
    persist_bed_update(snap)
    return snap


def _find_bed(ward: str, status: str) -> Optional[dict[str, Any]]:
    """First bed in the ward with the requested status, or any-ward
    fallback if none in-ward (so a 'cardiac' request can still be
    served by a general-ward bed if cardiac is dry — surfaces as a
    cohorting decision in the demo)."""
    for snap in bed_state.values():
        if snap.get("ward") == ward and snap.get("status") == status:
            return snap
    for snap in bed_state.values():
        if snap.get("status") == status:
            return snap
    return None


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------


def _bad_request(msg: str) -> web.Response:
    return web.json_response({"error": msg}, status=400, headers=_CORS_HEADERS)


async def _handle_options(_request: web.Request) -> web.Response:
    return web.Response(headers=_CORS_HEADERS)


async def _handle_post_reserve(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _bad_request("body must be valid JSON")

    if not isinstance(body, dict):
        return _bad_request("body must be a JSON object")

    ward = body.get("ward")
    if not isinstance(ward, str) or not ward.strip():
        return _bad_request("ward (string) is required")

    urgency = body.get("urgency", "urgent")
    if urgency not in {"routine", "urgent", "emergent"}:
        return _bad_request("urgency must be routine|urgent|emergent")

    reason = body.get("reason") if isinstance(body.get("reason"), str) else None
    requested_by = body.get("requested_by", "dashboard")
    request_id = body.get("request_id") or str(uuid.uuid4())

    req = {
        "id": request_id,
        "ward": ward,
        "urgency": urgency,
        "reason": reason,
        "status": "pending",
        "created_at": _now_iso(),
    }
    persist_transfer_request(req)

    bed_agent._logger.info(  # type: ignore[attr-defined]
        f"++ reservation request {request_id[:8]} ward={ward} "
        f"urgency={urgency} reason={reason!r}"
    )

    # Hand off to the agent loop so we don't block the HTTP response
    # on the (potentially slow) inter-agent ctx.send path.
    asyncio.create_task(_dispatch_request(req))

    return web.json_response(
        {"request_id": request_id, "status": "queued"},
        status=202, headers=_CORS_HEADERS,
    )


async def _start_http_server() -> None:
    app = web.Application()
    app.router.add_post("/bed/reserve",   _handle_post_reserve)
    app.router.add_options("/bed/reserve", _handle_options)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", BED_HTTP_PORT)
    await site.start()
    bed_agent._logger.info(  # type: ignore[attr-defined]
        f"bed HTTP endpoint listening on http://0.0.0.0:{BED_HTTP_PORT}"
        f"/bed/reserve (CORS open)"
    )


# ---------------------------------------------------------------------------
# Reservation matching
# ---------------------------------------------------------------------------


async def _dispatch_request(req: dict[str, Any]) -> None:
    """
    Try to satisfy a reservation in priority order:
      1. A `ready` bed in the ward -> reserve immediately.
      2. A `clinically_clear` bed -> dispatch Discharge for that bed's
         occupant. The discharge workflow runs the full Claude EN/ES
         summary + 5-stage timeline, then emits BedReleased, which the
         bed agent's existing handler chains into Facilities cleaning.
         End result: the audience sees both the discharge story AND
         the cleaning countdown from a single click.
      3. Otherwise -> ask Discharge to find ANY clinically-clear
         patient (pre-Phase 2 fallback path).
    """
    ward = req["ward"]

    ready = _find_bed(ward, "ready")
    if ready is not None:
        await _reserve_bed_for_request(ready["room_number"], req)
        return

    clear = _find_bed(ward, "clinically_clear")
    if clear is not None:
        pending_transfers.append(req)
        await _request_targeted_discharge(clear, req)
        return

    pending_transfers.append(req)
    await _request_discharge(req)


async def _reserve_bed_for_request(room_number: str,
                                   req: dict[str, Any]) -> None:
    snap = _set_bed(
        room_number,
        status="reserved",
        reserved_for=req.get("reason") or f"{req['ward']} transfer",
        ready_at=_now_iso(),
    )
    persist_transfer_request({
        "id": req["id"],
        "status": "fulfilled",
        "target_room": room_number,
        "fulfilled_at": _now_iso(),
    })
    bed_agent._logger.info(  # type: ignore[attr-defined]
        f"** reserved room {room_number} for request {req['id'][:8]} "
        f"(ward={snap.get('ward')})"
    )


async def _request_cleaning(room_number: str, request_id: str) -> None:
    if not TARGETS["facilities"]:
        bed_agent._logger.warning(  # type: ignore[attr-defined]
            "no facilities target wired; cannot dispatch cleaning"
        )
        return
    eta_iso = (datetime.now(timezone.utc)
               + timedelta(seconds=BED_CLEANING_SECONDS)).isoformat()
    _set_bed(room_number, status="cleaning", cleaning_eta=eta_iso)
    persist_transfer_request({
        "id": request_id,
        "status": "waiting_cleanup",
        "target_room": room_number,
        "eta": eta_iso,
    })
    # Schedule via the agent context — but we don't have a Context
    # here, only inside a handler. Use the bed_agent's send method
    # via a dedicated coroutine.
    await _send_message(TARGETS["facilities"], RoomNeedsCleaning(
        room_number=room_number,
        request_id=request_id,
        requested_at=_now_iso(),
    ))


async def _request_targeted_discharge(
    bed_snapshot: dict[str, Any], req: dict[str, Any]
) -> None:
    """Case-2 fast path: we already know exactly whose bed we want
    (the clinically_clear occupant). Send DischargeRequest with that
    patient_id so the discharge agent skips its candidate search and
    runs the full workflow immediately. Threading the original
    transfer_request id through ``triggered_by_request_id`` ensures
    that when BedReleased eventually reaches us, ``handle_room_ready``
    matches the freed bed back to the waiting reservation precisely."""

    occupant = bed_snapshot.get("occupant_patient_id")
    if not occupant:
        bed_agent._logger.warning(  # type: ignore[attr-defined]
            f"clinically_clear bed {bed_snapshot.get('room_number')} has "
            "no occupant; falling back to BedNeedRequest"
        )
        await _request_discharge(req)
        return
    if not TARGETS["discharge"]:
        bed_agent._logger.warning(  # type: ignore[attr-defined]
            "no discharge target wired; cannot dispatch DischargeRequest"
        )
        return
    persist_transfer_request({
        "id":     req["id"],
        "status": "matched",
    })
    await _send_message(TARGETS["discharge"], DischargeRequest(
        patient_id=occupant,
        requested_by=f"bed_agent (transfer {req['id'][:8]})",
        triggered_by_request_id=req["id"],
    ))
    bed_agent._logger.info(  # type: ignore[attr-defined]
        f">> targeted discharge for room {bed_snapshot.get('room_number')} "
        f"patient={occupant[:8]} (transfer {req['id'][:8]})"
    )


async def _request_discharge(req: dict[str, Any]) -> None:
    if not TARGETS["discharge"]:
        bed_agent._logger.warning(  # type: ignore[attr-defined]
            "no discharge target wired; cannot dispatch BedNeedRequest"
        )
        return
    persist_transfer_request({
        "id":     req["id"],
        "status": "matched",
    })
    await _send_message(TARGETS["discharge"], BedNeedRequest(
        request_id=req["id"],
        ward=req["ward"],
        urgency=req["urgency"],
    ))
    bed_agent._logger.info(  # type: ignore[attr-defined]
        f">> bed-need to discharge agent (request={req['id'][:8]} "
        f"ward={req['ward']})"
    )


# uAgents only exposes ctx.send inside handlers; HTTP handlers and
# asyncio.create_task callbacks live outside that. We synthesise a
# fresh InternalContext on demand via the agent's own builder so any
# coroutine on the bureau's event loop can fire-and-forget messages.
async def _send_message(destination: str, message: Any) -> None:
    try:
        ctx = bed_agent._build_context()  # type: ignore[attr-defined]
        await ctx.send(destination, message)
    except Exception as exc:
        bed_agent._logger.warning(  # type: ignore[attr-defined]
            f"send failed ({type(message).__name__}): {exc}"
        )


# ---------------------------------------------------------------------------
# Inbound agent messages
# ---------------------------------------------------------------------------


@bed_agent.on_message(model=BedReleased)
async def handle_bed_released(ctx: Context, sender: str, msg: BedReleased) -> None:
    """Discharge agent confirms patient X has formally left room Y.
    Flip to clinically_clear, then immediately dispatch Facilities and
    flip to cleaning so the audience sees both transitions."""

    snap = _set_bed(
        msg.room_number,
        status="clinically_clear",
        occupant_patient_id=None,
    )
    ctx.logger.info(
        f"<- BedReleased room {msg.room_number} by patient {msg.by_patient_id[:8]}"
    )

    # Brief visible pause so the dashboard renders clinically_clear,
    # then move to cleaning. ~1.5 s is enough for the Realtime push to
    # arrive and the human eye to register the pill colour change.
    await asyncio.sleep(1.5)

    await _request_cleaning(msg.room_number, msg.request_id)


@bed_agent.on_message(model=RoomReady)
async def handle_room_ready(ctx: Context, sender: str, msg: RoomReady) -> None:
    """Facilities crew finished. Move the bed to `ready`, then try to
    fulfil the oldest pending transfer for the matching ward."""

    snap = _set_bed(
        msg.room_number,
        status="ready",
        cleaning_eta=None,
        ready_at=msg.ready_at,
    )
    ctx.logger.info(f"<- RoomReady room {msg.room_number}")

    target_req = None
    for req in list(pending_transfers):
        if req["id"] == msg.request_id:
            target_req = req
            break
    if target_req is None:
        for req in list(pending_transfers):
            if req.get("ward") == snap.get("ward"):
                target_req = req
                break

    if target_req is not None:
        pending_transfers.remove(target_req)
        await _reserve_bed_for_request(msg.room_number, target_req)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@bed_agent.on_event("startup")
async def announce(ctx: Context) -> None:
    ctx.logger.info("=" * 72)
    ctx.logger.info("Bed Agent (3 West) is up.")
    ctx.logger.info(f"  agent address : {bed_agent.address}")
    ctx.logger.info(f"  HTTP endpoint : http://0.0.0.0:{BED_HTTP_PORT}/bed/reserve")
    ctx.logger.info("=" * 72)

    rows = fetch_all_beds()
    if rows:
        for row in rows:
            rn = row.get("room_number")
            if not rn:
                continue
            bed_state[rn] = {
                "room_number":         rn,
                "ward":                row.get("ward"),
                "status":              row.get("status", "occupied"),
                "occupant_patient_id": row.get("occupant_patient_id"),
                "reserved_for":        row.get("reserved_for"),
                "cleaning_eta":        row.get("cleaning_eta"),
                "ready_at":            row.get("ready_at"),
                "last_change":         row.get("last_change") or _now_iso(),
            }
        ctx.logger.info(f"loaded {len(bed_state)} beds from Supabase")
    else:
        ctx.logger.info("no beds in Supabase yet — running with empty inventory")

    try:
        await _start_http_server()
    except Exception as exc:
        ctx.logger.warning(f"bed HTTP endpoint failed to start: {exc}")


@bed_agent.on_interval(period=20.0)
async def print_inventory(ctx: Context) -> None:
    if not bed_state:
        return
    ctx.logger.info("---- bed inventory ----")
    for snap in sorted(bed_state.values(), key=lambda s: s.get("room_number", "")):
        ctx.logger.info(
            f"  room {snap.get('room_number'):>3} "
            f"[{snap.get('ward','?'):<7}] {snap.get('status','?'):<17} "
            f"occupant={(snap.get('occupant_patient_id') or '—')[:8]} "
            f"reserved_for={snap.get('reserved_for') or '—'}"
        )
    if pending_transfers:
        ctx.logger.info(f"  + {len(pending_transfers)} pending transfer(s)")
    ctx.logger.info("-----------------------")


if __name__ == "__main__":
    bed_agent.run()
