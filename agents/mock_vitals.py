"""
Realistic mock vitals generator for the demo.

Each patient has a `VitalsStream` with their own baseline (sampled
once at construction) and a small random walk on every `next()`
call. Scenarios (sepsis, bradycardia, hypoxia, recovery) can be
toggled at runtime — Person 4's demo script flips a scenario from
"baseline" -> "sepsis" to drive the dashboard from stable to
critical on cue.

The numbers here are not medically meaningful; they are tuned so
that `evaluate_flag()` produces a plausible mix of stable / watch
/ critical states during a 5-minute demo.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Optional


# Scenario presets. Each preset shifts the baseline + tightens the
# noise so the resulting vitals reliably trip the targeted flag.
SCENARIOS: dict[str, dict[str, tuple[float, float]]] = {
    # baseline = "patient is fine, drift around healthy means"
    "baseline": {
        "hr":      (78.0, 4.0),
        "bp_sys":  (118.0, 5.0),
        "bp_dia":  (74.0, 4.0),
        "spo2":    (98.0, 0.6),
        "temp_c":  (36.7, 0.2),
        "rr":      (16.0, 1.2),
    },
    # mild post-op watch state — only ONE vital sits in the watch
    # band so the EWS rule (>=2 watch breaches => critical) does not
    # fire by accident. Person 4 can tune up to trigger escalation
    # mid-demo by switching scenario to "sepsis".
    "watch": {
        "hr":      (88.0, 2.5),     # normal upper end
        "bp_sys":  (124.0, 3.0),    # normal
        "bp_dia":  (78.0, 2.5),     # normal
        "spo2":    (93.5, 0.4),     # WATCH band (92–94)
        "temp_c":  (37.0, 0.2),     # normal
        "rr":      (18.0, 1.0),     # normal upper
    },
    # Phase 1.5 demo beat — Maria Gonzalez, §19 step 8.
    # Tuned so the PRELIMINARY NEWS2 (passive params only, room-air,
    # ACVPU=A) lands at exactly 4 → low/watch with no single param
    # scoring 3:
    #   HR 95          → 1 (91–110)
    #   BP 124/78      → 0
    #   SpO2 93.5      → 2 (92–93 band, conservative <94)
    #   Temp 38.5 °C   → 1 (38.1–39.0)
    #   RR 18          → 0
    #   ───────────────────
    #   preliminary    = 4  (low / watch flag)
    # Flipping ACVPU = V then adds +3 → full NEWS2 = 7 → high /
    # critical, which is the demo punchline. Sigmas are kept tight
    # so the score doesn't drift past 4 and accidentally pre-trip
    # the critical flag during the walk-up.
    "demo_watch": {
        "hr":      (95.0, 1.5),
        "bp_sys":  (124.0, 2.5),
        "bp_dia":  (78.0, 2.0),
        "spo2":    (93.5, 0.3),
        "temp_c":  (38.5, 0.15),
        "rr":      (18.0, 0.8),
    },
    # septic shock onset — HR up, BP up early then crashes,
    # temp spiking, RR up
    "sepsis": {
        "hr":      (128.0, 4.0),
        "bp_sys":  (158.0, 6.0),
        "bp_dia":  (94.0, 4.0),
        "spo2":    (94.0, 0.8),
        "temp_c":  (38.9, 0.25),
        "rr":      (23.0, 1.3),
    },
    # symptomatic bradycardia + hypoxia
    "bradycardia": {
        "hr":      (44.0, 2.5),
        "bp_sys":  (104.0, 5.0),
        "bp_dia":  (66.0, 4.0),
        "spo2":    (90.5, 0.7),
        "temp_c":  (36.6, 0.2),
        "rr":      (15.0, 1.0),
    },
    # acute hypoxia (e.g. PE / pneumonia decompensation)
    "hypoxia": {
        "hr":      (118.0, 4.0),
        "bp_sys":  (132.0, 5.0),
        "bp_dia":  (84.0, 4.0),
        "spo2":    (89.0, 1.0),
        "temp_c":  (37.4, 0.25),
        "rr":      (26.0, 1.5),
    },
}


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass
class VitalsStream:
    """
    Per-patient stateful vitals generator.

    `current` holds the most recent reading; each call to `next()`
    nudges the values toward the active scenario's mean and adds a
    little gaussian noise on top. Scenarios are switched in-place
    via `set_scenario()`, so callers can drive a demo by mutating
    the active preset between polls.
    """

    patient_id: str
    room: str
    full_name: str
    scenario: str = "baseline"
    seed: Optional[int] = None
    current: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.seed is not None:
            self._rng = random.Random(self.seed)
        else:
            self._rng = random.Random()
        if self.scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {self.scenario}")
        # Initialize from the scenario mean so the very first reading
        # is already on-target rather than drifting in slowly.
        preset = SCENARIOS[self.scenario]
        self.current = {k: mean for k, (mean, _) in preset.items()}

    def set_scenario(self, scenario: str) -> None:
        if scenario not in SCENARIOS:
            raise ValueError(f"unknown scenario: {scenario}")
        self.scenario = scenario

    def next(self) -> dict[str, float]:
        """Advance the stream by one tick and return the new vitals."""
        preset = SCENARIOS[self.scenario]
        for key, (mean, sigma) in preset.items():
            # Gentle pull toward the scenario mean (Ornstein–Uhlenbeck-ish)
            # plus gaussian noise. The 0.35 / 0.65 weights produce a stream
            # that moves visibly between polls without flickering.
            drift = (mean - self.current[key]) * 0.35
            jitter = self._rng.gauss(0.0, sigma)
            self.current[key] = self.current[key] + drift + jitter

        # Apply hard physiological clamps so a stray gaussian tail
        # doesn't produce something silly like SpO2 = 110.
        self.current["hr"] = _clip(self.current["hr"], 25.0, 220.0)
        self.current["bp_sys"] = _clip(self.current["bp_sys"], 50.0, 240.0)
        self.current["bp_dia"] = _clip(self.current["bp_dia"], 30.0, 140.0)
        self.current["spo2"] = _clip(self.current["spo2"], 70.0, 100.0)
        self.current["temp_c"] = _clip(self.current["temp_c"], 33.0, 42.0)
        self.current["rr"] = _clip(self.current["rr"], 5.0, 45.0)

        # Round to one decimal so the dashboard doesn't render noise.
        return {k: round(v, 1) for k, v in self.current.items()}


# Demo roster — matches the seed data in supabase/seed.sql so the
# dashboard cards and the live agents agree on patient identity.
DEMO_ROSTER: list[dict[str, str]] = [
    {
        "patient_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "room": "301",
        "full_name": "Maria Gonzalez",
        # Pinned to baseline so Maria stays stable for the duration
        # of the demo. The earlier `demo_watch` preset (Phase 1.5
        # §19 step 8) put her at preliminary NEWS2 = 4 with an
        # ACVPU=V tap escalating her to critical — keep that recipe
        # in SCENARIOS for future demos, but don't drive her with it
        # by default. Env override `VITALWATCH_SCENARIO_301=...` is
        # still respected via roster_from_env().
        "scenario": "baseline",
    },
    {
        "patient_id": "aaaaaaaa-0000-0000-0000-000000000002",
        "room": "302",
        "full_name": "Lin Yao",
        "scenario": "watch",
    },
    {
        "patient_id": "aaaaaaaa-0000-0000-0000-000000000003",
        "room": "303",
        "full_name": "David Mehta",
        "scenario": "baseline",
    },
    {
        "patient_id": "aaaaaaaa-0000-0000-0000-000000000004",
        "room": "305",
        "full_name": "James Okafor",
        # Pre-loaded for the bradycardia demo beat.
        "scenario": "bradycardia",
    },
]


def roster_from_env() -> list[dict[str, str]]:
    """
    Allow overriding individual scenarios via env vars at launch:
        VITALWATCH_SCENARIO_301=sepsis
        VITALWATCH_SCENARIO_303=hypoxia
    """
    out = []
    for p in DEMO_ROSTER:
        override = os.environ.get(f"VITALWATCH_SCENARIO_{p['room']}")
        out.append({**p, "scenario": override or p["scenario"]})
    return out
