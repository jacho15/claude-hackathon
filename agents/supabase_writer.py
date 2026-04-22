"""
Supabase write layer for the floor aggregator agent.

The floor agent calls one function per inbound message:
    persist_update(state_dict)
That single call fans out to:
    1. UPSERT  patient_current_state   (one row per patient)
    2. INSERT  vitals_readings         (append-only history)
    3. INSERT  flags                   (only on flag transitions to
                                        watch / critical, OR severity
                                        escalations)
    4. INSERT  doctor_calls            (only when transitioning to
                                        critical, deduped per patient)

All writes are wrapped in try/except: a failed Supabase write logs
a warning but never crashes the agent loop. If credentials are
missing the writer becomes a no-op and prints a one-time notice.

The Supabase Python client (``supabase-py``) is synchronous. We
keep the calls synchronous here too — the message handler runs at
~10 Hz worst-case across all patients, well within the budget for
serial HTTP. If this ever needs to scale, wrap each call in
``asyncio.to_thread(...)`` from the caller.
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Map ACVPU + scenario + flag to a short doctor specialty hint so
# the auto-created doctor_calls entry isn't generic. Person 4 can
# override at acknowledge-time from the dashboard.
_SPECIALTY_HINT = {
    "bradycardia": "Cardiology",
    "sepsis":      "Internal Medicine",
    "hypoxia":     "Pulmonology",
}

# Severity 1..5 mapping driven primarily by NEWS2 risk band.
_SEVERITY_BY_RISK = {"none": 1, "low": 2, "medium": 4, "high": 5}


# --- client singleton -------------------------------------------------------

_client = None
_client_lock = threading.Lock()
_disabled_logged = False


def _missing_creds() -> Optional[str]:
    if not os.environ.get("SUPABASE_URL"):
        return "SUPABASE_URL"
    # Service-role key bypasses RLS (agents are trusted backend).
    if not (os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")):
        return "SUPABASE_SERVICE_KEY (or SUPABASE_ANON_KEY)"
    return None


def _get_client():
    """Return a cached supabase Client, or None if creds/lib missing."""
    global _client, _disabled_logged
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        missing = _missing_creds()
        if missing:
            if not _disabled_logged:
                logger.warning(
                    "Supabase writer disabled: %s not set. "
                    "Mock-only mode active.", missing
                )
                _disabled_logged = True
            return None
        try:
            from supabase import create_client  # type: ignore
        except ImportError:
            if not _disabled_logged:
                logger.warning(
                    "Supabase writer disabled: `supabase` package "
                    "not installed. `pip install supabase` to enable."
                )
                _disabled_logged = True
            return None
        url = os.environ["SUPABASE_URL"]
        key = (os.environ.get("SUPABASE_SERVICE_KEY")
               or os.environ["SUPABASE_ANON_KEY"])
        _client = create_client(url, key)
        logger.info("Supabase writer enabled (url=%s).", url)
        return _client


# --- per-patient transition state (in-memory) -------------------------------

_last_flag: dict[str, str] = {}   # patient_id -> previous flag
_last_doctor_call: dict[str, str] = {}  # patient_id -> last urgency
_state_lock = threading.Lock()


def _record_transition(patient_id: str, flag: str) -> Optional[str]:
    """Return previous flag if it changed, else None."""
    with _state_lock:
        prev = _last_flag.get(patient_id)
        _last_flag[patient_id] = flag
    return prev if prev != flag else None


def _should_open_doctor_call(patient_id: str, flag: str, prev: Optional[str]) -> bool:
    """
    A doctor call is opened when a patient newly enters `critical`
    OR escalates from watch -> critical. We do NOT spam the queue
    while the patient stays critical tick-after-tick.
    """
    if flag != "critical":
        return False
    if prev == "critical":
        return False
    return True


# --- session reset ----------------------------------------------------------

def clear_session_data() -> None:
    """Delete all doctor_calls and unacknowledged flags from previous sessions."""
    client = _get_client()
    if client is None:
        return
    try:
        client.table("doctor_calls").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        logger.info("Cleared doctor_calls for new session.")
    except Exception as exc:
        logger.warning("Failed to clear doctor_calls: %s", exc)
    try:
        client.table("flags").delete().eq("acknowledged", False).execute()
        logger.info("Cleared unacknowledged flags for new session.")
    except Exception as exc:
        logger.warning("Failed to clear flags: %s", exc)


# --- public write API -------------------------------------------------------

def _attending_doctor(patient_id: str) -> str:
    """
    Best-effort: look up the attending physician from the patients
    table. If anything goes wrong, fall back to the on-call name.
    Cached for the life of the process — patients don't switch
    attending mid-shift in this demo.
    """
    cache = _attending_doctor.cache  # type: ignore[attr-defined]
    if patient_id in cache:
        return cache[patient_id]
    client = _get_client()
    name = "Dr. On-Call"
    if client is not None:
        try:
            res = (client.table("patients")
                         .select("attending_doc")
                         .eq("id", patient_id)
                         .single()
                         .execute())
            if res.data and res.data.get("attending_doc"):
                name = res.data["attending_doc"]
        except Exception:
            pass
    cache[patient_id] = name
    return name


_attending_doctor.cache = {}  # type: ignore[attr-defined]


def persist_update(state: dict[str, Any]) -> None:
    """
    Single entrypoint called by the floor aggregator on every inbound
    VitalsUpdate. ``state`` is the snapshot dict the floor builds — see
    floor_aggregator.handle_patient_update for its shape.

    Silently no-ops when Supabase is not configured.
    """
    client = _get_client()
    if client is None:
        return

    patient_id: str = state["patient_id"]
    flag: str = state["flag"]
    prev_flag = _record_transition(patient_id, flag)

    now = datetime.now(timezone.utc).isoformat()

    # 1. patient_current_state -- always upsert
    state_row = {
        "patient_id":   patient_id,
        "hr":           state["hr"],
        "bp_sys":       state["bp_sys"],
        "bp_dia":       state["bp_dia"],
        "spo2":         state["spo2"],
        "temp_c":       state["temp_c"],
        "rr":           state["rr"],
        "flag":         flag,
        "ai_note":      state.get("ai_note", ""),
        "agent_address": state.get("agent_address"),
        "news2_score":  state.get("news2_score", 0),
        "news2_risk":   state.get("news2_risk", "none"),
        "on_oxygen":    bool(state.get("on_oxygen", False)),
        "consciousness": state.get("consciousness", "A"),
        "spo2_scale":   int(state.get("spo2_scale", 1)),
        # Phase 1.5: passive-only NEWS2. Defaults to 0/"none" so a
        # row missing these fields (older agents, partial state)
        # round-trips cleanly through the upsert.
        "preliminary_news2_score": state.get("preliminary_news2_score", 0),
        "preliminary_news2_risk":  state.get("preliminary_news2_risk", "none"),
        "scenario":     state.get("scenario"),
        "last_updated": now,
    }
    # Phase 1.5: only stamp *_set_at when the caller explicitly
    # provides them (i.e. via the staff endpoint). Omitting these
    # keys keeps the existing values intact in the upsert — Postgres
    # only updates columns named in the INSERT body.
    for key in ("nibp_set_at", "temp_set_at",
                "o2_set_at", "acvpu_set_at"):
        if state.get(key) is not None:
            state_row[key] = state[key]
    # Phase 2: discharge_status is conditionally upserted the same
    # way. Pass an explicit None to clear the badge; omit the key
    # entirely to leave the DB value intact.
    if "discharge_status" in state:
        state_row["discharge_status"] = state["discharge_status"]
    try:
        client.table("patient_current_state").upsert(state_row).execute()
    except Exception as exc:
        logger.warning("upsert patient_current_state failed for %s: %s",
                       patient_id, exc)

    # 2. vitals_readings -- always insert
    reading_row = {
        "patient_id":  patient_id,
        "hr":          state["hr"],
        "bp_sys":      state["bp_sys"],
        "bp_dia":      state["bp_dia"],
        "spo2":        state["spo2"],
        "temp_c":      state["temp_c"],
        "rr":          state["rr"],
        "flag":        flag,
        "news2_score": state.get("news2_score", 0),
        "news2_risk":  state.get("news2_risk", "none"),
        "recorded_at": now,
    }
    try:
        client.table("vitals_readings").insert(reading_row).execute()
    except Exception as exc:
        logger.warning("insert vitals_readings failed for %s: %s",
                       patient_id, exc)

    # 3. flags -- only on transitions into a worse state
    if prev_flag is not None and _is_escalation(prev_flag, flag):
        flag_row = {
            "patient_id":  patient_id,
            "flag_type":   flag,                          # 'watch' | 'critical'
            "severity":    _SEVERITY_BY_RISK.get(
                               state.get("news2_risk", "none"), 3),
            "message":     _flag_message(state, prev_flag),
            "ai_note":     state.get("ai_note", ""),
            "news2_score": state.get("news2_score", 0),
            "acknowledged": False,
            "resolved":     False,
        }
        try:
            client.table("flags").insert(flag_row).execute()
        except Exception as exc:
            logger.warning("insert flags failed for %s: %s",
                           patient_id, exc)

    # 4. doctor_calls -- only when newly critical
    if _should_open_doctor_call(patient_id, flag, prev_flag):
        doctor_row = {
            "patient_id": patient_id,
            "doctor_name": _attending_doctor(patient_id),
            "specialty":   _SPECIALTY_HINT.get(state.get("scenario") or ""),
            "urgency":     "urgent",
            "reason":      state.get("ai_note") or _flag_message(state, prev_flag),
            "status":      "pending",
        }
        try:
            client.table("doctor_calls").insert(doctor_row).execute()
            with _state_lock:
                _last_doctor_call[patient_id] = "urgent"
        except Exception as exc:
            logger.warning("insert doctor_calls failed for %s: %s",
                           patient_id, exc)


# --- helpers ---------------------------------------------------------------

_FLAG_RANK = {"stable": 0, "watch": 1, "critical": 2}


def _is_escalation(prev: str, current: str) -> bool:
    """True iff the patient moved to a strictly worse flag."""
    return _FLAG_RANK.get(current, 0) > _FLAG_RANK.get(prev, 0)


# ===========================================================================
# Phase 2: Bed / Discharge / Facilities writers.
#
# Each function follows the same conditional-upsert pattern as
# `persist_update`: only keys actually present in the input dict are
# included in the row body, so callers can update one field without
# clobbering others. All three are idempotent on `id` / unique key.
# ===========================================================================


def _audit_insert(table: str, row: dict[str, Any]) -> None:
    """Best-effort append-only insert into an audit table. Failures
    are warnings, never exceptions — the audit trail is nice-to-have,
    the live state row is the source of truth."""
    client = _get_client()
    if client is None:
        return
    try:
        client.table(table).insert(row).execute()
    except Exception as exc:
        logger.warning("audit insert into %s failed: %s", table, exc)


def persist_bed_update(state: dict[str, Any]) -> None:
    """
    Upsert a row in `beds`. ``state`` MUST include ``room_number``
    (the unique key the bed agent operates on). Optional keys —
    only those present are written, mirroring the manual-fields
    pattern in persist_update so a partial status flip doesn't
    erase ward/occupant information held elsewhere.

    On a status change, also append to `bed_history`.
    """
    client = _get_client()
    if client is None:
        return

    if "room_number" not in state:
        logger.warning("persist_bed_update missing room_number: %r", state)
        return

    row: dict[str, Any] = {"room_number": state["room_number"]}
    for key in ("ward", "status", "occupant_patient_id",
                "reserved_for", "cleaning_eta", "ready_at"):
        if key in state:
            row[key] = state[key]
    row["last_change"] = state.get("last_change") or datetime.now(timezone.utc).isoformat()

    try:
        # on_conflict drives the upsert via the UNIQUE constraint
        # on room_number; without this the client tries to upsert
        # by primary key (id) which we don't always have on hand.
        res = (client.table("beds")
                     .upsert(row, on_conflict="room_number")
                     .execute())
    except Exception as exc:
        logger.warning("upsert beds (room=%s) failed: %s",
                       state["room_number"], exc)
        return

    if "status" in state:
        bed_id = None
        try:
            if res.data:
                bed_id = res.data[0].get("id")
        except Exception:
            pass
        if bed_id is None:
            try:
                lookup = (client.table("beds")
                                .select("id")
                                .eq("room_number", state["room_number"])
                                .single()
                                .execute())
                bed_id = (lookup.data or {}).get("id")
            except Exception:
                bed_id = None
        if bed_id is not None:
            _audit_insert("bed_history", {
                "bed_id": bed_id,
                "status": state["status"],
                "actor":  state.get("actor", "bed_agent"),
            })
        _audit_insert("room_status_history", {
            "room_number": state["room_number"],
            "status":      state["status"],
            "actor":       state.get("actor", "bed_agent"),
        })


def persist_transfer_request(state: dict[str, Any]) -> None:
    """Upsert a transfer request keyed by `id` (request_id)."""
    client = _get_client()
    if client is None:
        return

    if "id" not in state:
        logger.warning("persist_transfer_request missing id: %r", state)
        return

    row: dict[str, Any] = {"id": state["id"]}
    for key in ("ward", "urgency", "reason", "status",
                "target_room", "released_by_patient_id",
                "eta", "created_at", "fulfilled_at"):
        if key in state:
            row[key] = state[key]
    try:
        client.table("transfer_requests").upsert(row).execute()
    except Exception as exc:
        logger.warning("upsert transfer_requests (id=%s) failed: %s",
                       state["id"], exc)


def persist_workflow_update(state: dict[str, Any]) -> None:
    """Upsert a discharge workflow keyed by `id`."""
    client = _get_client()
    if client is None:
        return

    if "id" not in state:
        logger.warning("persist_workflow_update missing id: %r", state)
        return

    row: dict[str, Any] = {"id": state["id"]}
    for key in ("patient_id", "requested_by", "language", "status",
                "triggered_by_request_id",
                "started_at", "completed_at"):
        if key in state:
            row[key] = state[key]
    try:
        client.table("discharge_workflows").upsert(row).execute()
    except Exception as exc:
        logger.warning("upsert discharge_workflows (id=%s) failed: %s",
                       state["id"], exc)


def persist_discharge_summary(workflow_id: str, language: str,
                              content: str) -> None:
    """Insert a discharge summary row — append-only, two per
    workflow (one EN, one in the requested language)."""
    client = _get_client()
    if client is None:
        return
    try:
        client.table("discharge_summaries").insert({
            "workflow_id": workflow_id,
            "language":    language,
            "content":     content,
        }).execute()
    except Exception as exc:
        logger.warning("insert discharge_summaries failed (wf=%s, lang=%s): %s",
                       workflow_id, language, exc)


def persist_transport_request(state: dict[str, Any]) -> None:
    """Upsert a transport row keyed by `id`."""
    client = _get_client()
    if client is None:
        return

    if "id" not in state:
        logger.warning("persist_transport_request missing id: %r", state)
        return

    row: dict[str, Any] = {"id": state["id"]}
    for key in ("workflow_id", "mode", "eta", "status"):
        if key in state:
            row[key] = state[key]
    try:
        client.table("transport_requests").upsert(row).execute()
    except Exception as exc:
        logger.warning("upsert transport_requests (id=%s) failed: %s",
                       state["id"], exc)


def persist_cleaning_update(state: dict[str, Any]) -> None:
    """Upsert a cleaning_jobs row keyed by `id`."""
    client = _get_client()
    if client is None:
        return

    if "id" not in state:
        logger.warning("persist_cleaning_update missing id: %r", state)
        return

    row: dict[str, Any] = {"id": state["id"]}
    for key in ("room_number", "status", "crew",
                "requested_at", "eta", "completed_at"):
        if key in state:
            row[key] = state[key]
    try:
        client.table("cleaning_jobs").upsert(row).execute()
    except Exception as exc:
        logger.warning("upsert cleaning_jobs (id=%s) failed: %s",
                       state["id"], exc)


def fetch_clinically_clear_patient(ward: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Return one bed (with patient info) currently flagged
    `clinically_clear`, optionally filtered by ward. Used by the
    Discharge Agent to pick a discharge target. Returns None if
    Supabase is unavailable or no candidate exists."""
    client = _get_client()
    if client is None:
        return None
    try:
        query = (client.table("beds")
                       .select("id, room_number, ward, occupant_patient_id, status")
                       .eq("status", "clinically_clear"))
        if ward:
            query = query.eq("ward", ward)
        res = query.limit(1).execute()
        if not res.data:
            return None
        bed = res.data[0]
        if bed.get("occupant_patient_id"):
            try:
                p = (client.table("patients")
                           .select("id, full_name, room_number, primary_dx")
                           .eq("id", bed["occupant_patient_id"])
                           .single()
                           .execute())
                if p.data:
                    bed["patient"] = p.data
            except Exception:
                pass
        return bed
    except Exception as exc:
        logger.warning("fetch_clinically_clear_patient failed: %s", exc)
        return None


def fetch_bed_by_room(room_number: str) -> Optional[dict[str, Any]]:
    """One-shot bed lookup. Used by the Bed Agent on boot to seed
    its in-memory inventory and on demand to recheck an unknown room."""
    client = _get_client()
    if client is None:
        return None
    try:
        res = (client.table("beds")
                     .select("*")
                     .eq("room_number", room_number)
                     .single()
                     .execute())
        return res.data
    except Exception as exc:
        logger.warning("fetch_bed_by_room (%s) failed: %s", room_number, exc)
        return None


def fetch_all_beds() -> list[dict[str, Any]]:
    """Return every bed row. Used by the Bed Agent on boot."""
    client = _get_client()
    if client is None:
        return []
    try:
        res = client.table("beds").select("*").execute()
        return list(res.data or [])
    except Exception as exc:
        logger.warning("fetch_all_beds failed: %s", exc)
        return []


def update_patient_discharge_status(patient_id: str, stage: Optional[str]) -> None:
    """Single-field upsert for patient_current_state.discharge_status.
    Phase 2 sticky field — passes through the existing upsert path
    so Realtime fires once and the PatientCard re-renders."""
    client = _get_client()
    if client is None:
        return
    try:
        client.table("patient_current_state").upsert({
            "patient_id":       patient_id,
            "discharge_status": stage,
        }).execute()
    except Exception as exc:
        logger.warning("update_patient_discharge_status (%s) failed: %s",
                       patient_id, exc)


def _flag_message(state: dict[str, Any], prev: Optional[str]) -> str:
    score = state.get("news2_score", 0)
    risk = state.get("news2_risk", "?")
    flag = state.get("flag", "?")
    room = state.get("room", "?")
    name = state.get("full_name", "?")
    base = (
        f"Room {room} ({name}): {prev or '∅'} -> {flag} "
        f"(NEWS2={score}, {risk} risk)"
    )
    return base
