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
        "scenario":     state.get("scenario"),
        "last_updated": now,
    }
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
