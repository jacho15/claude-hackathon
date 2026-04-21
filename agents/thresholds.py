"""
NEWS2 (National Early Warning Score 2) — UK Royal College of
Physicians, 2017. The de-facto standard EWS in the NHS and widely
adopted internationally.

Reference:
  Royal College of Physicians. National Early Warning Score (NEWS) 2:
  Standardising the assessment of acute-illness severity in the NHS.
  London: RCP, 2017. https://www.rcp.ac.uk/media/news2-report.pdf

NEWS2 assigns a 0–3 score to each of seven physiological parameters
and aggregates them. The aggregate score, plus a "single parameter
scoring 3" rule, drives the clinical response.

Aggregate score → clinical response (RCP Table 6):

  0          : routine 12-hourly observations
  1–4        : LOW   — min 4–6 hourly, ward nurse decides on care
  3 in any   : LOW–MEDIUM — urgent review by ward-based clinician
   single
   parameter
  5–6        : MEDIUM — urgent review by team with critical-care
                competency, consider transfer to higher dependency
  ≥ 7        : HIGH  — emergency assessment by critical-care team

We collapse those bands onto our 3-state UI flag as follows:

  stable    : aggregate 0
  watch     : aggregate 1–4 with no single parameter scoring 3
  critical  : aggregate ≥ 5  OR  any single parameter scoring 3

This matches the spirit of NEWS2's "anything that needs a human at
the bedside soon" threshold while keeping the dashboard's three
colour states intact.

Two simplifications worth flagging for clinical reviewers:

  * SpO2 Scale 1 only. NEWS2 defines a separate "Scale 2" for
    patients with hypercapnic respiratory failure (typically COPD
    with target SpO2 88–92%). We default everyone to Scale 1
    because we have no comorbidity model. A `scale` argument is
    threaded through so the patient agent can opt in per room.

  * Consciousness uses the ACVPU letters (A, C, V, P, U). "A" or
    blank means alert and scores 0; anything else scores 3. We
    default to "A" because the mock vitals stream has no
    consciousness signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping

Vitals = Mapping[str, float]
SpO2Scale = Literal[1, 2]
ACVPU = Literal["A", "C", "V", "P", "U"]
Risk = Literal["none", "low", "medium", "high"]


# --- per-parameter scoring ----------------------------------------------------
#
# NEWS2 is published for integer vitals (e.g. SpO2 93). Our mock
# generator emits one decimal (93.5). To avoid values falling
# between bands we use strict upper-bound comparisons (`<` rather
# than `<=`) on the breakpoints printed in the RCP table.
#
# Encoding rule:
#   "92–93 → 2" becomes  if spo2 < 94: return 2
#   "94–95 → 1" becomes  if spo2 < 96: return 1
# This treats 93.5 the same as 93, and 95.5 the same as 95, which
# is the clinically conservative interpretation.


def _score_rr(rr: float) -> int:
    if rr < 9:    return 3      # ≤ 8
    if rr < 12:   return 1      # 9–11
    if rr < 21:   return 0      # 12–20
    if rr < 25:   return 2      # 21–24
    return 3                    # ≥ 25


def _score_spo2_scale1(spo2: float) -> int:
    if spo2 < 92: return 3      # ≤ 91
    if spo2 < 94: return 2      # 92–93
    if spo2 < 96: return 1      # 94–95
    return 0                    # ≥ 96


def _score_spo2_scale2(spo2: float, on_oxygen: bool) -> int:
    """
    Scale 2 (target 88–92% for hypercapnic respiratory failure).

    On air: scores 0 across the full target range and above.
    On oxygen: high SpO2 also scores — over-oxygenation is
    dangerous in this group.
    """
    if spo2 < 84: return 3      # ≤ 83
    if spo2 < 86: return 2      # 84–85
    if spo2 < 88: return 1      # 86–87
    if spo2 < 93: return 0      # 88–92
    if not on_oxygen:
        return 0
    if spo2 < 95: return 1      # 93–94 on O2
    if spo2 < 97: return 2      # 95–96 on O2
    return 3                    # ≥ 97 on O2


def _score_oxygen(on_oxygen: bool) -> int:
    return 2 if on_oxygen else 0


def _score_sbp(sbp: float) -> int:
    if sbp < 91:  return 3      # ≤ 90
    if sbp < 101: return 2      # 91–100
    if sbp < 111: return 1      # 101–110
    if sbp < 220: return 0      # 111–219
    return 3                    # ≥ 220


def _score_pulse(hr: float) -> int:
    if hr < 41:   return 3      # ≤ 40
    if hr < 51:   return 1      # 41–50
    if hr < 91:   return 0      # 51–90
    if hr < 111:  return 1      # 91–110
    if hr < 131:  return 2      # 111–130
    return 3                    # ≥ 131


def _score_consciousness(level: ACVPU) -> int:
    # Alert (A) scores 0. New-onset confusion (C), responding to
    # Voice/Pain, or Unresponsive all score 3. NEWS2 does not
    # discriminate between V/P/U.
    return 0 if level == "A" else 3


def _score_temperature(temp_c: float) -> int:
    if temp_c < 35.1: return 3  # ≤ 35.0
    if temp_c < 36.1: return 1  # 35.1–36.0
    if temp_c < 38.1: return 0  # 36.1–38.0
    if temp_c < 39.1: return 1  # 38.1–39.0
    return 2                    # ≥ 39.1


# --- aggregate ---------------------------------------------------------------

@dataclass(frozen=True)
class News2Result:
    score: int                       # aggregate 0..20
    risk: Risk                       # none / low / medium / high
    flag: str                        # stable / watch / critical (UI)
    parts: dict[str, int]            # per-parameter scores
    has_single_three: bool           # any parameter == 3
    explanation: str                 # human-readable summary

    @property
    def needs_attention(self) -> bool:
        return self.flag != "stable"


def score_news2(
    v: Vitals,
    *,
    on_oxygen: bool = False,
    consciousness: ACVPU = "A",
    spo2_scale: SpO2Scale = 1,
) -> News2Result:
    parts: dict[str, int] = {
        "rr":            _score_rr(v["rr"]),
        "spo2":          (_score_spo2_scale2(v["spo2"], on_oxygen)
                          if spo2_scale == 2
                          else _score_spo2_scale1(v["spo2"])),
        "oxygen":        _score_oxygen(on_oxygen),
        "temp_c":        _score_temperature(v["temp_c"]),
        "bp_sys":        _score_sbp(v["bp_sys"]),
        "hr":            _score_pulse(v["hr"]),
        "consciousness": _score_consciousness(consciousness),
    }
    score = sum(parts.values())
    has_three = any(p == 3 for p in parts.values())

    if score == 0:
        risk: Risk = "none"
        flag = "stable"
    elif score >= 7:
        risk = "high"
        flag = "critical"
    elif score >= 5 or has_three:
        risk = "medium"
        flag = "critical"
    else:
        risk = "low"
        flag = "watch"

    if flag == "stable":
        explanation = "all parameters within normal range"
    else:
        contrib = sorted(
            ((k, s) for k, s in parts.items() if s > 0),
            key=lambda kv: -kv[1],
        )
        contrib_str = ", ".join(f"{k}={s}" for k, s in contrib) or "none"
        explanation = (
            f"NEWS2={score} ({risk}); driven by {contrib_str}"
            + ("; single param=3" if has_three and score < 7 else "")
        )

    return News2Result(
        score=score,
        risk=risk,
        flag=flag,
        parts=parts,
        has_single_three=has_three,
        explanation=explanation,
    )


# --- Phase 1.5: passive-only NEWS2 -------------------------------------------
# `score_news2_partial` is the exact same NEWS2 calculation but
# fixed to "what we can know from sensors alone" — room-air,
# ACVPU=A. Both unmeasurable inputs score 0, so this is the
# best-case reading of the 5 passively-sensed parameters
# (HR, SpO2, RR, BP, temp).
#
# The patient agent emits this alongside the full score every
# tick. The dashboard surfaces it as "preliminary NEWS2" whenever
# the matching manual fields (o2_set_at / acvpu_set_at) are
# missing or stale — so the floor is never blind, and it's
# visually obvious which reading is sensor-grounded vs which is
# nurse-confirmed.
#
# `spo2_scale` is kept as a kwarg because it's a per-room patient
# property (hypercapnic respiratory failure), not a real-time
# nurse decision; safe to thread through.


def score_news2_partial(
    v: Vitals,
    *,
    spo2_scale: SpO2Scale = 1,
) -> News2Result:
    """
    Phase 1.5 preliminary NEWS2 — passive parameters only.

    Identical to ``score_news2`` with ``on_oxygen=False`` and
    ``consciousness="A"`` forced. Returns the same ``News2Result``
    so callers can use both interchangeably.
    """
    return score_news2(
        v,
        on_oxygen=False,
        consciousness="A",
        spo2_scale=spo2_scale,
    )


# --- backward-compatible facade ---------------------------------------------
# The rest of the codebase (patient_agent, floor_aggregator, the dashboard's
# colour scheme) was written against `evaluate_flag()` / `explain_flag()`.
# Keep those symbols stable and have them call NEWS2 under the hood so
# nothing else needs to change.


def evaluate_flag(
    v: Vitals,
    *,
    on_oxygen: bool = False,
    consciousness: ACVPU = "A",
    spo2_scale: SpO2Scale = 1,
) -> str:
    """Return one of "critical", "watch", "stable" for the given vitals."""
    return score_news2(
        v,
        on_oxygen=on_oxygen,
        consciousness=consciousness,
        spo2_scale=spo2_scale,
    ).flag


def explain_flag(
    v: Vitals,
    *,
    on_oxygen: bool = False,
    consciousness: ACVPU = "A",
    spo2_scale: SpO2Scale = 1,
) -> str:
    """Human-readable summary of the NEWS2 score — used in agent logs."""
    return score_news2(
        v,
        on_oxygen=on_oxygen,
        consciousness=consciousness,
        spo2_scale=spo2_scale,
    ).explanation
