"""
Discharge Agent.

Owns `discharge_workflows` + `discharge_summaries` (and the
`patient_current_state.discharge_status` mirror via the floor
aggregator).

Triggers
--------
1. ``BedNeedRequest`` from the Bed Agent — bed pressure: pick a
   clinically-clear patient, run the workflow, eventually emit
   ``BedReleased`` so the bed flips and Facilities can clean.
2. ``POST /discharge/start`` from the dashboard — manual / scheduled
   discharge, independent of bed pressure.

Workflow stages (order matters)
-------------------------------
``initiated`` -> ``summary_drafted`` -> ``transport_booked``
-> ``room_released`` -> ``completed``

After each transition the agent persists the workflow row AND
notifies the Floor Aggregator so the patient card on the dashboard
shows the latest stage badge.

Claude integration
------------------
Two summaries are generated per workflow: English and the language
requested by the caller (default ``es``). Falls back to a static
template if ANTHROPIC_API_KEY is missing or any single Claude call
errors — the live demo never blocks on a model call.
"""

from __future__ import annotations

import asyncio
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from aiohttp import web
from dotenv import load_dotenv
from uagents import Agent, Context

from .messages import (
    BedNeedRequest,
    BedReleased,
    DischargeRequest,
    DischargeStatusUpdate,
)
from .supabase_writer import (
    fetch_clinically_clear_patient,
    persist_discharge_summary,
    persist_transport_request,
    persist_workflow_update,
    update_patient_discharge_status,
)

load_dotenv()

DISCHARGE_HTTP_PORT = int(os.environ.get("DISCHARGE_HTTP_PORT", "8103"))

# Compressed-time knobs (see plan §"Compressed-time policy"). Real
# values would be 30 / 30 / 15 minutes; demo values fit a stage beat.
BED_DISCHARGE_PAPERWORK_SECONDS = float(
    os.environ.get("BED_DISCHARGE_PAPERWORK_SECONDS", "4")
)
BED_TRANSPORT_SECONDS = float(os.environ.get("BED_TRANSPORT_SECONDS", "8"))

DEFAULT_SECONDARY_LANGUAGE = os.environ.get("DEFAULT_DISCHARGE_LANGUAGE", "es")

_CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age":       "86400",
}

discharge_agent = Agent(
    name="discharge_agent_3west",
    seed=os.environ.get("DISCHARGE_AGENT_SEED",
                        "vitalwatch-discharge-3west-demo-seed"),
    port=8203,
    endpoint=["http://127.0.0.1:8203/submit"],
)


# ---------------------------------------------------------------------------
# Cross-agent address discovery (set by scripts.run_all)
# ---------------------------------------------------------------------------

TARGETS: dict[str, str] = {"bed": "", "facilities": "", "floor": ""}


def set_targets(*, bed: str, facilities: str, floor: str) -> None:
    TARGETS["bed"] = bed
    TARGETS["facilities"] = facilities
    TARGETS["floor"] = floor


# In-memory map of in-flight workflows so HTTP responders can poll.
workflows: dict[str, dict[str, Any]] = {}                # id -> snapshot


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Claude EN+ES summary generator
# ---------------------------------------------------------------------------

_LANGUAGE_LABELS = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "zh": "Mandarin Chinese",
    "vi": "Vietnamese",
}

_FALLBACK_TEMPLATES = {
    "en": (
        "Discharge summary for {name} (Room {room}, dx: {dx}). "
        "You are clinically stable and ready to go home. Continue "
        "your prescribed medications, drink fluids, and rest. "
        "Follow up with your primary doctor within 7 days. Return "
        "to the ED if you develop fever > 38.5C, chest pain, "
        "shortness of breath, or worsening symptoms."
    ),
    "es": (
        "Resumen de alta para {name} (Habitación {room}, dx: {dx}). "
        "Está clínicamente estable y lista para regresar a casa. "
        "Continúe sus medicamentos recetados, beba líquidos y "
        "descanse. Visite a su médico de cabecera dentro de 7 días. "
        "Regrese a Urgencias si desarrolla fiebre > 38.5°C, dolor "
        "de pecho, dificultad para respirar o si los síntomas "
        "empeoran."
    ),
}

_anthropic_client = None
_anthropic_lock = threading.Lock()


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is not None:
        return _anthropic_client
    with _anthropic_lock:
        if _anthropic_client is not None:
            return _anthropic_client
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic  # type: ignore
        except ImportError:
            return None
        _anthropic_client = anthropic.Anthropic()
        return _anthropic_client


def _fallback_summary(language: str, *, name: str, room: str, dx: str) -> str:
    tmpl = _FALLBACK_TEMPLATES.get(language) or _FALLBACK_TEMPLATES["en"]
    return tmpl.format(name=name, room=room, dx=dx or "post-op recovery")


def _generate_summary_sync(language: str, *, name: str, room: str, dx: str) -> str:
    client = _get_anthropic()
    if client is None:
        return _fallback_summary(language, name=name, room=room, dx=dx)
    try:
        prompt = (
            f"You are a hospital discharge nurse. Write a short, "
            f"patient-readable post-discharge summary in "
            f"{_LANGUAGE_LABELS.get(language, language)} for an "
            f"adult inpatient about to leave the ward. Plain prose, "
            f"no markdown, ≤120 words. Cover: 1) why they were "
            f"admitted, 2) home care instructions, 3) medication "
            f"reminders, 4) when to come back to the ED.\n\n"
            f"Patient: {name}, Room {room}.\n"
            f"Primary diagnosis: {dx or 'post-op recovery'}.\n"
            f"Status at discharge: clinically clear, vitals stable."
        )
        message = client.messages.create(
            model=os.environ.get("ANTHROPIC_MODEL",
                                 "claude-sonnet-4-5-20250929"),
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
        chunks: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                chunks.append(text)
        out = " ".join(c.strip() for c in chunks).strip()
        return out or _fallback_summary(language, name=name, room=room, dx=dx)
    except Exception as exc:
        discharge_agent._logger.warning(  # type: ignore[attr-defined]
            f"Claude summary failed ({language}): {exc}"
        )
        return _fallback_summary(language, name=name, room=room, dx=dx)


async def _generate_summary(language: str, *, name: str, room: str, dx: str) -> str:
    return await asyncio.to_thread(
        _generate_summary_sync, language, name=name, room=room, dx=dx
    )


# ---------------------------------------------------------------------------
# Workflow lifecycle
# ---------------------------------------------------------------------------


async def _send_message(destination: str, message: Any) -> None:
    if not destination:
        discharge_agent._logger.warning(  # type: ignore[attr-defined]
            f"no destination wired; dropping {type(message).__name__}"
        )
        return
    try:
        ctx = discharge_agent._build_context()  # type: ignore[attr-defined]
        await ctx.send(destination, message)
    except Exception as exc:
        discharge_agent._logger.warning(  # type: ignore[attr-defined]
            f"send failed ({type(message).__name__}): {exc}"
        )


def _set_workflow(wf_id: str, **changes: Any) -> dict[str, Any]:
    wf = workflows.setdefault(wf_id, {"id": wf_id})
    wf.update(changes)
    persist_workflow_update(wf)
    pid = wf.get("patient_id")
    stage = wf.get("status")
    if pid and stage:
        update_patient_discharge_status(pid, stage)
        if TARGETS["floor"]:
            asyncio.create_task(_send_message(
                TARGETS["floor"],
                DischargeStatusUpdate(
                    patient_id=pid,
                    workflow_id=wf_id,
                    stage=stage,
                    updated_at=_now_iso(),
                ),
            ))
    return wf


async def _run_workflow(
    *,
    workflow_id: str,
    patient: dict[str, Any],
    room_number: str,
    language: str,
    requested_by: str,
    triggered_by_request_id: Optional[str],
) -> None:
    """The full discharge state machine. Each stage:
       1. updates discharge_workflows.status
       2. mirrors to patient_current_state.discharge_status
       3. notifies the Floor Aggregator (DischargeStatusUpdate)
       4. waits its compressed-time delay
       5. moves to the next stage."""

    pid = patient["id"]
    name = patient.get("full_name") or "Patient"
    dx = patient.get("primary_dx") or ""

    _set_workflow(
        workflow_id,
        patient_id=pid,
        requested_by=requested_by,
        language=language,
        triggered_by_request_id=triggered_by_request_id,
        status="initiated",
        started_at=_now_iso(),
    )

    discharge_agent._logger.info(  # type: ignore[attr-defined]
        f"++ discharge workflow {workflow_id[:8]} initiated for "
        f"{name} (room {room_number}) lang={language} by={requested_by}"
    )

    # Stage 2: draft EN + secondary-language summaries via Claude.
    await asyncio.sleep(BED_DISCHARGE_PAPERWORK_SECONDS)
    en_summary = await _generate_summary("en", name=name, room=room_number, dx=dx)
    persist_discharge_summary(workflow_id, "en", en_summary)
    if language and language != "en":
        secondary = await _generate_summary(language, name=name, room=room_number, dx=dx)
        persist_discharge_summary(workflow_id, language, secondary)

    _set_workflow(workflow_id, status="summary_drafted")

    # Stage 3: book transport (mock).
    transport_id = str(uuid.uuid4())
    transport_eta = (datetime.now(timezone.utc)
                     + timedelta(seconds=BED_TRANSPORT_SECONDS)).isoformat()
    persist_transport_request({
        "id":          transport_id,
        "workflow_id": workflow_id,
        "mode":        "wheelchair",
        "eta":         transport_eta,
        "status":      "booked",
    })
    _set_workflow(workflow_id, status="transport_booked")

    # Stage 4: release the room. This is the moment the Bed Agent
    # has been waiting for — emit BedReleased, the bed flips to
    # clinically_clear, then the bed agent dispatches Facilities.
    await asyncio.sleep(BED_TRANSPORT_SECONDS)

    _set_workflow(workflow_id, status="room_released")

    if TARGETS["bed"]:
        await _send_message(TARGETS["bed"], BedReleased(
            room_number=room_number,
            by_patient_id=pid,
            request_id=triggered_by_request_id or workflow_id,
            released_at=_now_iso(),
        ))

    persist_transport_request({
        "id":     transport_id,
        "status": "completed",
    })

    # Stage 5: complete the workflow row.
    _set_workflow(
        workflow_id,
        status="completed",
        completed_at=_now_iso(),
    )

    # Phase 2 (post-fix): keep `completed` sticky on the patient card.
    # The earlier behaviour cleared the badge to None at this point so
    # a hypothetical next admit started clean — but in practice that
    # also caused the card to look "alive" again, with vitals
    # continuing to tick every 2s. The desired demo behaviour is the
    # opposite: once discharged, the card greys out and freezes. The
    # floor aggregator gates vitals persistence on this sticky value.

    discharge_agent._logger.info(  # type: ignore[attr-defined]
        f"== discharge workflow {workflow_id[:8]} completed for {name} "
        f"(card frozen, vitals updates suppressed)"
    )


# ---------------------------------------------------------------------------
# Inbound HTTP
# ---------------------------------------------------------------------------


def _bad_request(msg: str) -> web.Response:
    return web.json_response({"error": msg}, status=400, headers=_CORS_HEADERS)


async def _handle_options(_request: web.Request) -> web.Response:
    return web.Response(headers=_CORS_HEADERS)


async def _handle_post_start(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _bad_request("body must be valid JSON")
    if not isinstance(body, dict):
        return _bad_request("body must be a JSON object")

    pid = body.get("patient_id")
    if not isinstance(pid, str) or not pid:
        return _bad_request("patient_id (string) is required")

    requested_by = body.get("requested_by", "dashboard")
    language = body.get("language") or DEFAULT_SECONDARY_LANGUAGE

    bed = await asyncio.to_thread(_lookup_bed_for_patient, pid)
    if bed is None:
        return _bad_request(
            f"no bed currently assigned to patient {pid} — refusing to "
            "start a discharge against an unknown room"
        )

    workflow_id = str(uuid.uuid4())
    asyncio.create_task(_run_workflow(
        workflow_id=workflow_id,
        patient={
            "id": pid,
            "full_name": bed.get("patient_full_name"),
            "primary_dx": bed.get("patient_primary_dx"),
        },
        room_number=bed["room_number"],
        language=language,
        requested_by=requested_by,
        triggered_by_request_id=None,
    ))

    return web.json_response(
        {"workflow_id": workflow_id, "status": "queued"},
        status=202, headers=_CORS_HEADERS,
    )


def _lookup_bed_for_patient(patient_id: str) -> Optional[dict[str, Any]]:
    """Find the bed currently occupied by this patient. Pulled into
    a sync function so the HTTP handler can offload it via to_thread."""
    from .supabase_writer import _get_client                         # noqa: PLC0415

    client = _get_client()
    if client is None:
        return None
    try:
        beds_res = (client.table("beds")
                          .select("room_number, ward, occupant_patient_id")
                          .eq("occupant_patient_id", patient_id)
                          .limit(1)
                          .execute())
        if not beds_res.data:
            return None
        bed = beds_res.data[0]
        try:
            p_res = (client.table("patients")
                           .select("full_name, primary_dx")
                           .eq("id", patient_id)
                           .single()
                           .execute())
            if p_res.data:
                bed["patient_full_name"] = p_res.data.get("full_name")
                bed["patient_primary_dx"] = p_res.data.get("primary_dx")
        except Exception:
            pass
        return bed
    except Exception:
        return None


async def _start_http_server() -> None:
    app = web.Application()
    app.router.add_post("/discharge/start",   _handle_post_start)
    app.router.add_options("/discharge/start", _handle_options)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", DISCHARGE_HTTP_PORT)
    await site.start()
    discharge_agent._logger.info(  # type: ignore[attr-defined]
        f"discharge HTTP endpoint listening on http://0.0.0.0:"
        f"{DISCHARGE_HTTP_PORT}/discharge/start (CORS open)"
    )


# ---------------------------------------------------------------------------
# Inbound agent messages
# ---------------------------------------------------------------------------


@discharge_agent.on_message(model=DischargeRequest)
async def handle_discharge_request(
    ctx: Context, sender: str, msg: DischargeRequest
) -> None:
    """Targeted discharge for a specific patient. Sent by the Bed
    Agent in the case-2 fast path (a clinically_clear bed has been
    earmarked for an inbound transfer and we want the audience to
    see the full Claude EN/ES summary + 5-stage timeline beat,
    not just a cleaning countdown). Mirrors POST /discharge/start
    so a single click can drive both bed flow and discharge flow."""

    ctx.logger.info(
        f"<- DischargeRequest patient={msg.patient_id[:8]} "
        f"by={msg.requested_by} "
        f"triggered_by={(msg.triggered_by_request_id or '—')[:8]}"
    )

    bed = await asyncio.to_thread(_lookup_bed_for_patient, msg.patient_id)
    if bed is None:
        ctx.logger.warning(
            f"no bed currently assigned to patient {msg.patient_id} — "
            "ignoring DischargeRequest"
        )
        return

    workflow_id = str(uuid.uuid4())
    asyncio.create_task(_run_workflow(
        workflow_id=workflow_id,
        patient={
            "id":         msg.patient_id,
            "full_name":  bed.get("patient_full_name"),
            "primary_dx": bed.get("patient_primary_dx"),
        },
        room_number=bed["room_number"],
        language=msg.language or DEFAULT_SECONDARY_LANGUAGE,
        requested_by=msg.requested_by,
        triggered_by_request_id=msg.triggered_by_request_id,
    ))


@discharge_agent.on_message(model=BedNeedRequest)
async def handle_bed_need(ctx: Context, sender: str, msg: BedNeedRequest) -> None:
    """Bed agent has a transfer request and no free bed in the ward.
    Pick a clinically-clear patient (preferring same ward) and run
    the full discharge workflow."""

    ctx.logger.info(
        f"<- BedNeedRequest ward={msg.ward} urgency={msg.urgency} "
        f"req={msg.request_id[:8]}"
    )

    bed = await asyncio.to_thread(fetch_clinically_clear_patient, msg.ward)
    if bed is None:
        bed = await asyncio.to_thread(fetch_clinically_clear_patient, None)
    if bed is None:
        ctx.logger.warning(
            "no clinically-clear patient available to free a bed — "
            "request stays pending"
        )
        return

    patient = bed.get("patient") or {
        "id": bed.get("occupant_patient_id"),
        "full_name": "Patient",
        "primary_dx": "",
    }
    pid = patient.get("id")
    room_number = bed.get("room_number")
    if not pid or not room_number:
        ctx.logger.warning("clinically-clear bed has no occupant; skipping")
        return

    workflow_id = str(uuid.uuid4())
    asyncio.create_task(_run_workflow(
        workflow_id=workflow_id,
        patient=patient,
        room_number=room_number,
        language=DEFAULT_SECONDARY_LANGUAGE,
        requested_by=f"bed_agent ({msg.request_id})",
        triggered_by_request_id=msg.request_id,
    ))


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


@discharge_agent.on_event("startup")
async def announce(ctx: Context) -> None:
    ctx.logger.info("=" * 72)
    ctx.logger.info("Discharge Agent (3 West) is up.")
    ctx.logger.info(f"  agent address : {discharge_agent.address}")
    ctx.logger.info(f"  HTTP endpoint : http://0.0.0.0:{DISCHARGE_HTTP_PORT}/discharge/start")
    ctx.logger.info(
        f"  pacing        : paperwork={BED_DISCHARGE_PAPERWORK_SECONDS}s "
        f"transport={BED_TRANSPORT_SECONDS}s"
    )
    if _get_anthropic() is None:
        ctx.logger.info("  Claude        : disabled (using fallback templates)")
    else:
        ctx.logger.info("  Claude        : enabled (live EN + secondary summary)")
    ctx.logger.info("=" * 72)

    try:
        await _start_http_server()
    except Exception as exc:
        ctx.logger.warning(f"discharge HTTP endpoint failed to start: {exc}")


if __name__ == "__main__":
    discharge_agent.run()
