"""
Shared uAgents message models.

These Pydantic models define the wire format that flows from each
Patient Agent to the Floor Aggregator Agent. They MUST stay in sync
between sender and receiver — uAgents identifies message types by
their schema digest, so any field rename invalidates routing.
"""

from __future__ import annotations

from typing import Optional

from uagents import Model


class VitalsUpdate(Model):
    patient_id: str
    room: str
    full_name: str

    hr: float       # Heart rate (bpm)
    bp_sys: float   # Systolic BP (mmHg)
    bp_dia: float   # Diastolic BP (mmHg)
    spo2: float     # Oxygen saturation (%)
    temp_c: float   # Temperature (°C)
    rr: float       # Respiratory rate (breaths/min)

    flag: str       # "critical" | "watch" | "stable"
    ai_note: str    # Claude-generated clinical note (may be empty in mock mode)
    scenario: Optional[str] = None  # e.g. "sepsis", "bradycardia", "baseline"

    # --- NEWS2 (UK NHS Royal College of Physicians) -------------------------
    # The score and risk band are computed by the patient agent so the floor
    # aggregator and dashboard never have to re-derive them. Inputs that are
    # not measurable from the bedside monitor (oxygen, consciousness) ride
    # along so the audit trail is complete.
    news2_score: int = 0                  # 0..20 aggregate
    news2_risk: str = "none"              # "none" | "low" | "medium" | "high"
    on_oxygen: bool = False               # patient on supplemental O2?
    consciousness: str = "A"              # ACVPU letter; "A" = alert
    spo2_scale: int = 1                   # 1 = standard, 2 = hypercapnic

    # --- Phase 1.5: preliminary NEWS2 (passive sensors only) ----------------
    # Same calculation as news2_score but with on_oxygen=False and
    # consciousness="A" forced. Surfaces what the floor can know
    # from sensors alone, before any nurse-supplied manual data
    # has been entered or has gone stale. Defaults to 0 / "none"
    # so older agents stay wire-compatible.
    preliminary_news2_score: int = 0
    preliminary_news2_risk: str = "none"  # "none" | "low" | "medium" | "high"


class VitalsAck(Model):
    """Acknowledgement returned by the floor agent for each update."""

    patient_id: str
    received_at: str
    floor_status: str  # short summary of current floor state


# ---------------------------------------------------------------------------
# Phase 2: Bed / Discharge / Facilities wire format
#
# Every Model gets a `request_id` or `workflow_id` so the dashboard can
# reconcile which row in transfer_requests / discharge_workflows the
# inter-agent message belongs to. uAgents matches handlers by schema
# digest, so once these are deployed do NOT rename or retype fields.
# ---------------------------------------------------------------------------


class BedReservationRequest(Model):
    """Dashboard -> Bed Agent (HTTP wraps it). Asks the bed agent
    to find / free a bed in the requested ward at the requested
    urgency, returning either an immediate match or a request_id
    the dashboard can poll on."""

    request_id: str
    ward: str
    urgency: str = "urgent"      # "routine" | "urgent" | "emergent"
    reason: Optional[str] = None
    requested_by: str = "dashboard"


class BedNeedRequest(Model):
    """Bed Agent -> Discharge Agent. Means: I have no free bed in
    `ward`; please find me a clinically_clear patient I can discharge
    so the room can flip to cleaning -> ready -> reserved."""

    request_id: str
    ward: str
    urgency: str


class BedReleased(Model):
    """Discharge Agent -> Bed Agent. Means: this patient has formally
    left the room — flip the bed to `clinically_clear` (then on to
    cleaning once Facilities is dispatched)."""

    room_number: str
    by_patient_id: str
    request_id: str
    released_at: str


class RoomNeedsCleaning(Model):
    """Discharge Agent -> Facilities Agent. The corresponding row in
    cleaning_jobs is created by Facilities on receipt."""

    room_number: str
    request_id: str
    requested_at: str


class RoomReady(Model):
    """Facilities Agent -> Bed Agent. Cleaning crew finished; bed
    is physically ready to accept the next patient."""

    room_number: str
    request_id: str
    ready_at: str


class DischargeRequest(Model):
    """Dashboard -> Discharge Agent (HTTP wraps it) OR Bed Agent ->
    Discharge Agent when a clinically_clear bed has been earmarked for
    an inbound transfer. The optional ``triggered_by_request_id``
    threads the original transfer_request id all the way through to
    the eventual BedReleased so the bed agent can match the cleaned
    room back to its waiting reservation precisely."""

    patient_id: str
    requested_by: str
    language: str = "es"
    triggered_by_request_id: Optional[str] = None


class DischargeStatusUpdate(Model):
    """Discharge Agent -> Floor Aggregator. Surfaces the workflow
    stage on the patient_current_state row so each PatientCard can
    show 'Discharge initiated' / 'Summary drafted' / etc."""

    patient_id: str
    workflow_id: str
    stage: str                    # 'initiated' | 'summary_drafted' | ...
    updated_at: str
