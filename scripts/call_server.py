"""
Call-server — tiny FastAPI app the dashboard hits to place a real
phone call through Twilio.

Why a separate process instead of embedding the endpoint in the
Floor Aggregator agent: uAgents owns its own HTTP surface on the
Bureau and we don't want to mix dashboard-facing REST with inter-
agent submit routes. Running this on :8300 keeps things clean and
CORS simple.

Endpoints
---------
    GET  /health          -> {status, twilio_enabled, supabase_enabled}
    POST /call-doctor     -> places a Twilio call + upserts doctor_calls row

The POST accepts:
    {
      "patient_id": "<uuid>",
      "doctor_name": "Dr. Reyes",    # optional; defaults to attending_doc
      "specialty":   "Cardiology",   # optional
      "reason":      "Critical ...", # optional; defaults to latest ai_note
      "urgency":     "urgent"        # optional; urgent|routine|follow_up
    }

Run
---
    python -m scripts.call_server
    # → listening on http://127.0.0.1:8300
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

# Make sure the project root is importable when this script is launched
# directly (e.g. `python scripts/call_server.py`) — otherwise the later
# `from agents.call_dispatcher import ...` blows up with ModuleNotFoundError.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
)
logger = logging.getLogger("call_server")

app = FastAPI(title="Nucleus Call Server", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class CallRequest(BaseModel):
    patient_id: str
    doctor_name: Optional[str] = None
    specialty: Optional[str] = None
    reason: Optional[str] = None
    urgency: str = "urgent"
    # Optional free-text line the nurse types in the dashboard; it
    # replaces the auto-generated short description in the TwiML body.
    custom_message: Optional[str] = None


def _get_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY") or os.environ.get("SUPABASE_ANON_KEY")
    if not url or not key:
        return None
    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        return None
    return create_client(url, key)


def _load_patient_context(sb, patient_id: str) -> dict[str, Any]:
    """Pull the patient profile + latest live state for the TwiML body."""
    p_resp = (
        sb.table("patients")
        .select("id, full_name, room_number, attending_doc, primary_dx")
        .eq("id", patient_id)
        .limit(1)
        .execute()
    )
    if not p_resp.data:
        raise HTTPException(404, f"patient {patient_id} not found")
    patient = p_resp.data[0]

    s_resp = (
        sb.table("patient_current_state")
        .select("hr, spo2, news2_score, news2_risk, flag, ai_note")
        .eq("patient_id", patient_id)
        .limit(1)
        .execute()
    )
    state = s_resp.data[0] if s_resp.data else {}

    return {"patient": patient, "state": state}


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "twilio_enabled": bool(os.environ.get("TWILIO_ACCOUNT_SID")
                               and os.environ.get("TWILIO_AUTH_TOKEN")
                               and os.environ.get("TWILIO_FROM_NUMBER")),
        "supabase_enabled": bool(os.environ.get("SUPABASE_URL")
                                 and (os.environ.get("SUPABASE_SERVICE_KEY")
                                      or os.environ.get("SUPABASE_ANON_KEY"))),
        "on_call_phone_set": bool(os.environ.get("ON_CALL_PHONE")),
    }


@app.post("/call-doctor")
def call_doctor(req: CallRequest) -> dict[str, Any]:
    from agents.call_dispatcher import place_doctor_call

    sb = _get_supabase()
    if sb is None:
        raise HTTPException(503, "supabase not configured on server")

    ctx = _load_patient_context(sb, req.patient_id)
    patient = ctx["patient"]
    state = ctx["state"]

    doctor_name = req.doctor_name or patient.get("attending_doc") or "the on-call doctor"
    specialty = req.specialty or "attending"
    reason = (
        req.reason
        or state.get("ai_note")
        or f"{state.get('flag', 'critical')} patient, NEWS2 {state.get('news2_score')}"
    )

    # 1. Insert the call row FIRST so the dashboard queue updates even
    #    if Twilio is down. Status starts as 'pending'.
    call_row = {
        "patient_id": req.patient_id,
        "doctor_name": doctor_name,
        "specialty": specialty,
        "reason": reason[:500],  # guard the column width
        "urgency": req.urgency,
        "status": "pending",
    }
    ins = sb.table("doctor_calls").insert(call_row).execute()
    call_id = ins.data[0]["id"] if ins.data else None

    # 2. Place the actual call.
    result = place_doctor_call(
        patient_name=patient["full_name"],
        room=patient["room_number"],
        doctor_name=doctor_name,
        reason=reason,
        news2_score=state.get("news2_score"),
        hr=state.get("hr"),
        spo2=state.get("spo2"),
        urgency=req.urgency,
        custom_message=req.custom_message,
    )

    # 3. If the call was actually dialled, flip the row to 'notified'.
    if result.get("placed") and call_id:
        sb.table("doctor_calls").update({
            "status": "notified",
            "scheduled_at": "now()",
        }).eq("id", call_id).execute()

    return {
        "call_id": call_id,
        "doctor_name": doctor_name,
        "patient_name": patient["full_name"],
        "room": patient["room_number"],
        **result,
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("CALL_SERVER_PORT", "8300"))
    # Pass the app object directly (not an import string) — this script
    # lives outside a Python package so "scripts.call_server:app" can't
    # be re-imported by uvicorn's config.load().
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="info",
    )
