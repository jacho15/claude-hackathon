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


class VitalsAck(Model):
    """Acknowledgement returned by the floor agent for each update."""

    patient_id: str
    received_at: str
    floor_status: str  # short summary of current floor state
