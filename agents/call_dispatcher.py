"""
Doctor-call dispatcher.

Places a real phone call via Twilio Programmable Voice whenever the
dashboard asks the floor to escalate a patient. Reuses the existing
Supabase writer so the `doctor_calls` table is the single audit
trail — this module only *places* the call and updates status.

Graceful-degrade behaviour (mirrors `claude_notes.py` /
`supabase_writer.py`):
  - No Twilio creds         -> return `{placed: False, reason: "twilio disabled"}`
  - Twilio package missing  -> same
  - Twilio API error        -> logged, return `{placed: False, reason: "<error>"}`
The caller (scripts.call_server) can still update `doctor_calls.status`
to `notified` in the no-call case so the dashboard UX is identical.

On-call phone routing:
  - Phase 1 demo: every call goes to `ON_CALL_PHONE` regardless of
    attending_doc. Trivial to extend later — look up the doctor in
    `staff` and map to a phone column when we add one.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

_client = None
_client_attempted = False


def _get_client():
    """Return a cached Twilio REST client, or None if disabled."""
    global _client, _client_attempted
    if _client is not None or _client_attempted:
        return _client
    _client_attempted = True

    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        logger.warning(
            "Twilio dispatcher disabled: TWILIO_ACCOUNT_SID / "
            "TWILIO_AUTH_TOKEN not set. Calls will be logged only."
        )
        return None
    try:
        from twilio.rest import Client  # type: ignore
    except ImportError:
        logger.warning(
            "Twilio dispatcher disabled: `twilio` package not installed. "
            "Run `pip install twilio` to enable real calls."
        )
        return None

    _client = Client(sid, token)
    logger.info("Twilio dispatcher enabled (from=%s).",
                os.environ.get("TWILIO_FROM_NUMBER", "<unset>"))
    return _client


def _spell_number(value) -> str:
    """Make SpO2/HR sound natural in TTS (e.g. '93' -> 'ninety three')."""
    # Twilio's Polly voices handle plain digits fine, so we keep this
    # simple — just strip decimals for cleaner speech.
    try:
        return str(int(round(float(value))))
    except Exception:
        return str(value)


def _shorten(text: str, limit: int = 180) -> str:
    """Trim free-text reasons so the TTS stays under ~10 seconds."""
    if not text:
        return ""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(",.;:") + "."


def _strip_doctor_prefix(name: str) -> str:
    """'Dr. Reyes' -> 'Reyes' for the spoken 'Doctor Reyes' template."""
    n = (name or "").strip()
    for prefix in ("Dr. ", "Dr ", "Doctor "):
        if n.lower().startswith(prefix.lower()):
            return n[len(prefix):].strip()
    return n


def _build_twiml(
    *,
    patient_name: str,
    room: str,
    doctor_name: str,
    reason: str,
    news2_score: Optional[int],
    hr: Optional[float],
    spo2: Optional[float],
    urgency: str = "urgent",
    custom_message: Optional[str] = None,
) -> str:
    """
    Build a TwiML script that reads like a real hospital page:

        "Doctor Reyes, you are needed in Room 305.
         Patient James Okafor — bradycardia with low oxygen.
         NEWS2 five. Heart rate forty-four. Oxygen ninety percent.
         Repeating: Room 305, bradycardia with low oxygen.
         Please acknowledge on the nurse-station dashboard. Thank you."

    `custom_message` — if provided (from the dashboard) — replaces the
    auto-generated short description. Keep it under ~180 chars.
    """
    urgency_word = {
        "urgent":    "urgently",
        "routine":   "",
        "follow_up": "for a follow-up",
    }.get(urgency, "urgently")

    last_name = _strip_doctor_prefix(doctor_name) or "on-call"
    short_desc = _shorten(custom_message or reason or "critical patient", 180)
    hr_txt    = _spell_number(hr)   if hr   is not None else "unknown"
    spo2_txt  = _spell_number(spo2) if spo2 is not None else "unknown"
    news2_txt = str(news2_score)    if news2_score is not None else "unknown"

    # Line 1 — WHERE and WHO. The doctor hears this in the first 3 seconds.
    line_where = (
        f"Doctor {last_name}, this is Nucleus. "
        f"You are needed {urgency_word} in Room {room}. "
    ).replace("  ", " ").strip()

    # Line 2 — WHAT (the nurse-supplied or AI-generated description).
    line_what = f"Patient {patient_name}. {short_desc}"
    if not line_what.rstrip().endswith((".", "!", "?")):
        line_what += "."

    # Line 3 — the numbers, spoken deliberately.
    line_numbers = (
        f"Current N E W S 2 score, {news2_txt}. "
        f"Heart rate, {hr_txt} beats per minute. "
        f"Oxygen saturation, {spo2_txt} percent."
    )

    # Short, repeatable summary so the doctor catches the essentials
    # even if they missed the first pass.
    line_repeat = (
        f"Repeating. Room {room}. {short_desc} "
        f"N E W S 2 {news2_txt}. Heart rate {hr_txt}. "
        f"Oxygen {spo2_txt} percent. "
        f"Please acknowledge on the nurse-station dashboard. Thank you."
    )

    import html
    parts = [html.escape(s) for s in (line_where, line_what, line_numbers, line_repeat)]

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Response>'
        f'<Say voice="Polly.Joanna">{parts[0]}</Say>'
        '<Pause length="1"/>'
        f'<Say voice="Polly.Joanna">{parts[1]}</Say>'
        '<Pause length="1"/>'
        f'<Say voice="Polly.Joanna">{parts[2]}</Say>'
        '<Pause length="2"/>'
        f'<Say voice="Polly.Joanna">{parts[3]}</Say>'
        '</Response>'
    )


def place_doctor_call(
    *,
    patient_name: str,
    room: str,
    doctor_name: str,
    reason: str,
    news2_score: Optional[int] = None,
    hr: Optional[float] = None,
    spo2: Optional[float] = None,
    urgency: str = "urgent",
    to_number: Optional[str] = None,
    custom_message: Optional[str] = None,
) -> dict[str, Any]:
    """
    Place a real phone call. Returns a dict describing what happened:

        { "placed": True,  "sid": "CAxxxx", "to": "+1...", "twiml": "<...>" }
        { "placed": False, "reason": "twilio disabled" | "<error>" }

    Never raises — every failure mode is returned as data so the caller
    can keep the DB write and the dashboard UX intact.
    """
    to = to_number or os.environ.get("ON_CALL_PHONE")
    if not to:
        return {"placed": False, "reason": "ON_CALL_PHONE not set"}

    client = _get_client()
    twiml = _build_twiml(
        patient_name=patient_name,
        room=room,
        doctor_name=doctor_name,
        reason=reason,
        news2_score=news2_score,
        hr=hr,
        spo2=spo2,
        urgency=urgency,
        custom_message=custom_message,
    )

    if client is None:
        logger.info(
            "[STUB CALL] to=%s  patient=%s room=%s doctor=%s reason=%r",
            to, patient_name, room, doctor_name, reason,
        )
        return {"placed": False, "reason": "twilio disabled", "twiml": twiml, "to": to}

    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    if not from_number:
        return {"placed": False, "reason": "TWILIO_FROM_NUMBER not set"}

    try:
        call = client.calls.create(
            to=to,
            from_=from_number,
            twiml=twiml,
        )
        logger.info("Twilio call queued: sid=%s to=%s from=%s",
                    call.sid, to, from_number)
        return {
            "placed": True,
            "sid": call.sid,
            "to": to,
            "from": from_number,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Twilio call failed: %s", exc)
        return {"placed": False, "reason": str(exc), "twiml": twiml, "to": to}
