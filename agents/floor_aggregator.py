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
from typing import Any, Optional

from aiohttp import web
from dotenv import load_dotenv
from uagents import Agent, Context

from .messages import DischargeStatusUpdate, VitalsAck, VitalsUpdate
from .thresholds import score_news2

load_dotenv()

FLAG_RANK = {"critical": 0, "watch": 1, "stable": 2}

# Port the staff HTTP API binds to. Separate from the agent's
# uAgents protocol port so the dashboard can hit it without
# interfering with inter-agent message routing — and so we can
# enable open CORS here without touching the agent socket.
STAFF_HTTP_PORT = int(os.environ.get("STAFF_HTTP_PORT", "8101"))

# Open CORS — the dashboard is on a separate origin in dev (Vite
# at :5173). For a hackathon demo with mock data this is fine; a
# production deployment would lock this down to the dashboard's
# real origin.
_CORS_HEADERS = {
    "Access-Control-Allow-Origin":  "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age":       "86400",
}

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


# ---------------------------------------------------------------------------
# Phase 1.5: staff HTTP endpoint
# ---------------------------------------------------------------------------
#
# Why a separate aiohttp server?
#   * uAgents 0.24 has on_rest_post but no CORS / OPTIONS support
#     and no path parameters — both needed for a browser client.
#   * Decoupling the dashboard write path from the uAgents
#     protocol socket means we can re-enable strict auth on /submit
#     later without affecting nurses.
#   * One handler, one route, ~80 lines including validation.
#
# Wire format:
#
#   POST /staff/patient/manual
#   {
#     "patient_id":  "<uuid>",          required
#     "set_by":      "Nurse Torres",    required, audit trail
#     "acvpu":       "A|C|V|P|U",       optional -> stamps acvpu_set_at
#     "on_oxygen":   true|false,        optional -> stamps o2_set_at
#     "o2_flow_rate": 4,                optional, informational
#     "spo2_scale":  1|2,               optional -> stamps o2_set_at
#     "bp_sys":      120,               optional -> stamps nibp_set_at
#     "bp_dia":      80,                optional -> stamps nibp_set_at
#     "temp_c":      37.2,              optional -> stamps temp_set_at
#   }
#
# Response 200:
#   {
#     "patient_id": "...", "set_at": "<iso8601>",
#     "fields_set": ["acvpu", "on_oxygen"],
#     "news2_score": 7,           "news2_risk": "high",
#     "preliminary_news2_score": 4, "preliminary_news2_risk": "low",
#     "flag": "critical",
#   }
#
# Response 4xx/5xx:
#   { "error": "<human-readable reason>" }


_VALID_ACVPU = {"A", "C", "V", "P", "U"}
_VALID_SPO2_SCALE = {1, 2}
_NUMERIC_FIELDS = ("bp_sys", "bp_dia", "temp_c", "o2_flow_rate")


def _bad_request(msg: str) -> web.Response:
    return web.json_response(
        {"error": msg}, status=400, headers=_CORS_HEADERS,
    )


def _validate_manual_payload(body: Any) -> tuple[Optional[str], dict]:
    """
    Returns (error_message, normalised_payload).
    On success error_message is None and the payload contains only
    the fields the caller actually supplied (i.e. partial update).
    """
    if not isinstance(body, dict):
        return "request body must be a JSON object", {}

    pid = body.get("patient_id")
    if not isinstance(pid, str) or not pid:
        return "patient_id (string) is required", {}

    set_by = body.get("set_by")
    if not isinstance(set_by, str) or not set_by.strip():
        return "set_by (string) is required for the audit trail", {}

    out: dict[str, Any] = {"patient_id": pid, "set_by": set_by.strip()}

    if "acvpu" in body:
        v = body["acvpu"]
        if not isinstance(v, str) or v.upper() not in _VALID_ACVPU:
            return "acvpu must be one of A,C,V,P,U", {}
        out["acvpu"] = v.upper()

    if "on_oxygen" in body:
        if not isinstance(body["on_oxygen"], bool):
            return "on_oxygen must be a boolean", {}
        out["on_oxygen"] = body["on_oxygen"]

    if "spo2_scale" in body:
        try:
            scale = int(body["spo2_scale"])
        except (TypeError, ValueError):
            return "spo2_scale must be 1 or 2", {}
        if scale not in _VALID_SPO2_SCALE:
            return "spo2_scale must be 1 or 2", {}
        out["spo2_scale"] = scale

    for k in _NUMERIC_FIELDS:
        if k in body:
            try:
                out[k] = float(body[k])
            except (TypeError, ValueError):
                return f"{k} must be numeric", {}

    # At least one settable field beyond patient_id/set_by must
    # be present; an empty PATCH is almost certainly a bug.
    if not (set(out) - {"patient_id", "set_by"}):
        return ("at least one of acvpu, on_oxygen, spo2_scale, "
                "bp_sys, bp_dia, temp_c must be provided"), {}

    return None, out


# Manual fields are nurse-owned. Once the staff endpoint has set
# them, the patient simulator's tick must NOT overwrite them — the
# simulator has no notion of nurse input and always emits its
# defaults (consciousness="A", on_oxygen=False). Both the agent
# tick handler and the staff endpoint reconcile through this list.
_MANUAL_FIELDS = ("consciousness", "on_oxygen", "o2_flow_rate", "spo2_scale")


def _recompute_full_news2(snap: dict) -> None:
    """
    Recompute the full NEWS2 score in-place on ``snap`` using its
    current vitals + manual fields, and update news2_score / risk /
    flag. Used by both the agent tick handler and the staff
    endpoint so the persisted score always agrees with the
    consciousness/on_oxygen the dashboard is rendering.

    ``preliminary_news2_score`` is not touched here — it is by
    definition independent of the manual fields and comes straight
    from the patient agent.
    """
    result = score_news2(
        {
            "hr":     snap["hr"],
            "bp_sys": snap["bp_sys"],
            "bp_dia": snap["bp_dia"],
            "spo2":   snap["spo2"],
            "temp_c": snap["temp_c"],
            "rr":     snap["rr"],
        },
        on_oxygen=bool(snap.get("on_oxygen", False)),
        consciousness=snap.get("consciousness", "A"),  # type: ignore[arg-type]
        spo2_scale=int(snap.get("spo2_scale", 1)),  # type: ignore[arg-type]
    )
    snap["news2_score"] = result.score
    snap["news2_risk"]  = result.risk
    snap["flag"]        = result.flag


def _apply_manual_update(payload: dict, now_iso: str) -> tuple[dict, list[str]]:
    """
    Merge the validated payload into floor_state[patient_id], stamp
    the matching *_set_at fields, and recompute NEWS2 against the
    current vitals + the new manual values. Returns the updated
    snapshot dict and a list of which logical fields were set.

    Raises KeyError if patient_id has no current state — the floor
    has never received a vitals update for them yet, so we have
    nothing to score against.
    """
    pid = payload["patient_id"]
    if pid not in floor_state:
        raise KeyError(pid)

    snap = floor_state[pid]
    fields_set: list[str] = []

    if "acvpu" in payload:
        snap["consciousness"] = payload["acvpu"]
        snap["acvpu_set_at"] = now_iso
        fields_set.append("acvpu")

    if "on_oxygen" in payload:
        snap["on_oxygen"] = payload["on_oxygen"]
        snap["o2_set_at"] = now_iso
        fields_set.append("on_oxygen")

    if "spo2_scale" in payload:
        snap["spo2_scale"] = payload["spo2_scale"]
        # Scale changes are an O2-related decision — same freshness
        # bucket as the on_oxygen toggle.
        snap["o2_set_at"] = now_iso
        if "on_oxygen" not in payload:
            fields_set.append("spo2_scale")

    if "bp_sys" in payload or "bp_dia" in payload:
        if "bp_sys" in payload:
            snap["bp_sys"] = payload["bp_sys"]
        if "bp_dia" in payload:
            snap["bp_dia"] = payload["bp_dia"]
        snap["nibp_set_at"] = now_iso
        fields_set.append("bp")

    if "temp_c" in payload:
        snap["temp_c"] = payload["temp_c"]
        snap["temp_set_at"] = now_iso
        fields_set.append("temp_c")

    # Recompute against the merged state. The agent tick handler
    # uses the same helper so the persisted score stays consistent
    # across both write paths.
    _recompute_full_news2(snap)
    snap["last_updated"] = now_iso
    # Audit trail — overwrites previous setter; kept in-memory only.
    snap["last_manual_set_by"] = payload["set_by"]

    return snap, fields_set


async def _handle_options(_request: web.Request) -> web.Response:
    return web.Response(headers=_CORS_HEADERS)


async def _handle_post_manual(request: web.Request) -> web.Response:
    try:
        body = await request.json()
    except Exception:
        return _bad_request("body must be valid JSON")

    err, payload = _validate_manual_payload(body)
    if err is not None:
        return _bad_request(err)

    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        snap, fields_set = _apply_manual_update(payload, now_iso)
    except KeyError:
        return web.json_response(
            {"error": f"patient {payload['patient_id']} has no current "
                      "state on this floor; wait for a vitals update first"},
            status=404, headers=_CORS_HEADERS,
        )

    persist_to_supabase(snap)

    floor_agent._logger.info(  # type: ignore[attr-defined]
        f"** manual update room {snap.get('room','?')} "
        f"({snap.get('full_name','?')}) by {payload['set_by']}: "
        f"{','.join(fields_set)} -> NEWS2={snap['news2_score']} "
        f"({snap['news2_risk']}) flag={snap['flag']}"
    )

    return web.json_response(
        {
            "patient_id":  snap["patient_id"],
            "set_at":      now_iso,
            "fields_set":  fields_set,
            "news2_score": snap["news2_score"],
            "news2_risk":  snap["news2_risk"],
            "preliminary_news2_score": snap.get("preliminary_news2_score", 0),
            "preliminary_news2_risk":  snap.get("preliminary_news2_risk", "none"),
            "flag":        snap["flag"],
        },
        headers=_CORS_HEADERS,
    )


async def _start_staff_http_server() -> None:
    """Boot the aiohttp app on STAFF_HTTP_PORT in the agent's loop."""
    app = web.Application()
    app.router.add_post("/staff/patient/manual", _handle_post_manual)
    app.router.add_options("/staff/patient/manual", _handle_options)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", STAFF_HTTP_PORT)
    await site.start()
    floor_agent._logger.info(  # type: ignore[attr-defined]
        f"staff HTTP endpoint listening on http://0.0.0.0:{STAFF_HTTP_PORT}"
        f"/staff/patient/manual (CORS open)"
    )


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

    # Phase 1.5 staff endpoint. Started as a background task so the
    # agent's main message loop is not blocked. If the bind fails
    # (port already in use), log and carry on — vitals ingest must
    # never be taken down by a dashboard concern.
    try:
        await _start_staff_http_server()
    except Exception as exc:
        ctx.logger.warning(f"staff HTTP endpoint failed to start: {exc}")


@floor_agent.on_message(model=VitalsUpdate, replies=VitalsAck)
async def handle_patient_update(
    ctx: Context, sender: str, msg: VitalsUpdate
) -> None:
    prev = floor_state.get(msg.patient_id, {})

    # Phase 2: once a patient hits 'completed' discharge status the
    # card on the dashboard greys out and freezes at the last
    # pre-discharge snapshot. The patient agent keeps polling for
    # demo simplicity, but we DROP the update on the floor here so
    # nothing is persisted, the in-memory state is unchanged, and
    # the freshness pills stop ticking. Still ack so the patient
    # agent doesn't error / retry.
    if prev.get("discharge_status") == "completed":
        await ctx.send(
            sender,
            VitalsAck(
                patient_id=msg.patient_id,
                received_at=datetime.now(timezone.utc).isoformat(),
                floor_status="patient discharged — vitals frozen",
            ),
        )
        return

    # Phase 1.5: manual fields are nurse-owned. Once the staff
    # endpoint has stamped them (signalled by the matching *_set_at
    # being non-null), the patient agent's defaults must NEVER
    # overwrite the nurse's value — otherwise an ACVPU=V tap reverts
    # to A on the next ~2 s tick.
    if prev.get("acvpu_set_at"):
        consciousness = prev.get("consciousness", msg.consciousness)
    else:
        consciousness = msg.consciousness

    if prev.get("o2_set_at"):
        on_oxygen   = prev.get("on_oxygen",   msg.on_oxygen)
        o2_flow_rate = prev.get("o2_flow_rate")
        spo2_scale  = prev.get("spo2_scale",  msg.spo2_scale)
    else:
        on_oxygen   = msg.on_oxygen
        o2_flow_rate = prev.get("o2_flow_rate")  # purely informational
        spo2_scale  = msg.spo2_scale

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
        "ai_note": msg.ai_note,
        "scenario": msg.scenario,
        # Manual / nurse-owned fields — sticky across ticks.
        "on_oxygen":     on_oxygen,
        "o2_flow_rate":  o2_flow_rate,
        "consciousness": consciousness,
        "spo2_scale":    spo2_scale,
        # Preserve freshness timestamps from the previous snapshot;
        # the agent never writes them. The writer's conditional
        # upsert keeps the existing DB value when these are absent,
        # but carrying them in floor_state keeps the in-memory view
        # consistent (e.g. for staff endpoint recomputes).
        "nibp_set_at":  prev.get("nibp_set_at"),
        "temp_set_at":  prev.get("temp_set_at"),
        "o2_set_at":    prev.get("o2_set_at"),
        "acvpu_set_at": prev.get("acvpu_set_at"),
        # Preliminary NEWS2 is sensor-only by definition — pass
        # through whatever the patient agent computed.
        "preliminary_news2_score": msg.preliminary_news2_score,
        "preliminary_news2_risk":  msg.preliminary_news2_risk,
        # Phase 2: discharge_status is owned by the discharge agent
        # via DischargeStatusUpdate. It must survive a vitals tick
        # the same way ACVPU does — hence the carry-forward.
        "discharge_status": prev.get("discharge_status"),
        # Full NEWS2 will be recomputed below using fresh vitals +
        # the (possibly nurse-overridden) manual fields. The agent's
        # msg.news2_score / msg.flag are ignored on purpose because
        # they were computed against the simulator's defaults, not
        # the actual nurse-confirmed state of the patient.
        "agent_address": sender,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }
    _recompute_full_news2(floor_state[msg.patient_id])

    snap = floor_state[msg.patient_id]
    ctx.logger.info(
        f"<- room {msg.room} ({msg.full_name}) flag={snap['flag']} "
        f"NEWS2={snap['news2_score']} ({snap['news2_risk']}) "
        f"[ACVPU={consciousness} O2={'Y' if on_oxygen else 'N'}] "
        f"from {sender[:18]}…"
    )

    persist_to_supabase(snap)

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


@floor_agent.on_message(model=DischargeStatusUpdate)
async def handle_discharge_status(
    ctx: Context, sender: str, msg: DischargeStatusUpdate
) -> None:
    """Phase 2: discharge agent telling us what stage of the
    workflow Maria (or whoever) is at. Sticky on the snapshot AND
    persisted so the dashboard PatientCard can render the badge.

    'cleared' is a sentinel meaning the workflow finished and we
    should drop the badge — translated to NULL on the snapshot."""

    snap = floor_state.get(msg.patient_id)
    if snap is None:
        # Patient never seen by the floor agent — still write through
        # to Supabase so the dashboard reflects it; we just have no
        # in-memory state to mutate.
        from .supabase_writer import update_patient_discharge_status  # noqa: PLC0415
        update_patient_discharge_status(
            msg.patient_id,
            None if msg.stage == "cleared" else msg.stage,
        )
        return

    snap["discharge_status"] = None if msg.stage == "cleared" else msg.stage
    snap["last_updated"] = datetime.now(timezone.utc).isoformat()
    persist_to_supabase(snap)

    ctx.logger.info(
        f"<- DischargeStatusUpdate room {snap.get('room','?')} "
        f"({snap.get('full_name','?')}): {msg.stage}"
    )


@floor_agent.on_interval(period=15.0)
async def print_snapshot(ctx: Context) -> None:
    ctx.logger.info("---- floor snapshot ----")
    for line in render_floor_snapshot().splitlines():
        ctx.logger.info(line)
    ctx.logger.info("------------------------")


if __name__ == "__main__":
    floor_agent.run()
