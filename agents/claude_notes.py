"""
Claude clinical-note generator.

Single public function: ``call_claude_for_note(vitals, flag, ...)``.
The patient agent looks for this module via lazy import — the moment
``ANTHROPIC_API_KEY`` is set in the environment and ``anthropic``
is installed, every patient cycle starts producing real Claude notes
in place of the deterministic stub.

Design notes
------------
* **Cheap by default.** Claude is called at most once per
  ``(patient_id, flag)`` transition, plus a refresh every
  ``CLAUDE_REFRESH_SECONDS`` (default 60s) for non-stable patients.
  Stable patients get one note and we reuse it. This caps spend
  during a 5-minute demo at ~30–40 calls instead of one per tick
  per patient.
* **Bounded tokens.** ``max_tokens=120`` and the prompt asks for
  ≤40 words. Sonnet typically returns ~30 words.
* **Safe failure.** Any error (rate-limit, bad key, network)
  returns a deterministic stub so the agent loop never crashes.
* **No PHI.** The prompt deliberately omits the patient's name.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Mapping, Optional

DEFAULT_MODEL = os.environ.get(
    "ANTHROPIC_MODEL", "claude-sonnet-4-20250514"
)
REFRESH_SECONDS = float(os.environ.get("CLAUDE_REFRESH_SECONDS", "60"))


# --- prompt -----------------------------------------------------------------

_PROMPT_TEMPLATE = """\
You are a clinical decision-support AI assisting a hospital nurse.
Analyse these vital signs and the NEWS2 score for an adult inpatient
and write a single concise clinical note (max 40 words, no preamble,
no markdown). If status is "watch" or "critical", end with one
explicit suggested action. Use clinical shorthand. Do NOT mention
the patient by name.

Vitals:
- HR: {hr} bpm
- BP: {bp_sys}/{bp_dia} mmHg
- SpO2: {spo2}% ({o2_status})
- Temperature: {temp_c} C
- Respiratory rate: {rr} breaths/min
- Consciousness (ACVPU): {consciousness}

NEWS2 aggregate score: {news2_score} ({news2_risk} risk)
Current flag: {flag}
"""


def _stub(vitals: Mapping[str, float], flag: str) -> str:
    """Deterministic fallback used when Claude is unavailable."""
    if flag == "critical":
        return (
            f"CRITICAL: HR {float(vitals['hr']):.0f}, "
            f"SpO2 {float(vitals['spo2']):.0f}%, "
            f"T {float(vitals['temp_c']):.1f}C. Escalate to attending."
        )
    if flag == "watch":
        return (
            f"Watch: borderline vitals (HR {float(vitals['hr']):.0f}, "
            f"SpO2 {float(vitals['spo2']):.0f}%). Recheck in 10 min."
        )
    return "Stable. Continue routine monitoring."


# --- cache ------------------------------------------------------------------

@dataclass
class _CacheEntry:
    flag: str
    note: str
    issued_at: float


_cache: dict[str, _CacheEntry] = {}
_cache_lock = threading.Lock()


def _cached_note(
    patient_id: Optional[str],
    flag: str,
) -> Optional[str]:
    if patient_id is None:
        return None
    with _cache_lock:
        entry = _cache.get(patient_id)
    if entry is None:
        return None
    if entry.flag != flag:
        # Flag transition: force a fresh note so the dashboard text
        # tracks the new clinical picture.
        return None
    if flag != "stable" and (time.time() - entry.issued_at) > REFRESH_SECONDS:
        return None
    return entry.note


def _store_note(patient_id: Optional[str], flag: str, note: str) -> None:
    if patient_id is None:
        return
    with _cache_lock:
        _cache[patient_id] = _CacheEntry(
            flag=flag, note=note, issued_at=time.time()
        )


# --- public API -------------------------------------------------------------

_client_singleton = None
_client_lock = threading.Lock()


def _get_client():
    """Lazy-import + singleton the Anthropic client."""
    global _client_singleton
    if _client_singleton is not None:
        return _client_singleton
    with _client_lock:
        if _client_singleton is not None:
            return _client_singleton
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic  # type: ignore
        except ImportError:
            return None
        _client_singleton = anthropic.Anthropic()
        return _client_singleton


def call_claude_for_note(
    vitals: Mapping[str, float],
    flag: str,
    *,
    patient_id: Optional[str] = None,
    news2_score: int = 0,
    news2_risk: str = "none",
    on_oxygen: bool = False,
    consciousness: str = "A",
    model: str = DEFAULT_MODEL,
) -> str:
    """
    Return a 1–2 sentence clinical note. Falls back to a stub on
    any failure path so the agent loop is never blocked by Claude.
    """
    cached = _cached_note(patient_id, flag)
    if cached is not None:
        return cached

    client = _get_client()
    if client is None:
        note = _stub(vitals, flag)
        _store_note(patient_id, flag, note)
        return note

    prompt = _PROMPT_TEMPLATE.format(
        hr=round(float(vitals["hr"]), 1),
        bp_sys=round(float(vitals["bp_sys"]), 1),
        bp_dia=round(float(vitals["bp_dia"]), 1),
        spo2=round(float(vitals["spo2"]), 1),
        temp_c=round(float(vitals["temp_c"]), 1),
        rr=round(float(vitals["rr"]), 1),
        consciousness=consciousness,
        o2_status="on supplemental O2" if on_oxygen else "room air",
        news2_score=news2_score,
        news2_risk=news2_risk,
        flag=flag,
    )

    try:
        message = client.messages.create(
            model=model,
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        # Defensive parsing — Anthropic returns a list of content
        # blocks; we want the first text block, joined.
        chunks: list[str] = []
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                chunks.append(text)
        note = " ".join(c.strip() for c in chunks).strip() or _stub(vitals, flag)
    except Exception:
        # Rate limit, bad key, network blip — log via stub.
        note = _stub(vitals, flag)

    _store_note(patient_id, flag, note)
    return note
