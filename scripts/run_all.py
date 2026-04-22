"""
Bring up the full VitalWatch agent mesh in one Python process.

Usage:
    python -m scripts.run_all

Spawns:
    - 1 Floor Aggregator on :8100  (staff HTTP on :8101)
    - 4 Patient Agents on :8001..:8004 (rooms 301, 302, 303, 305)
    - 1 Bed Agent           (HTTP on :8102)
    - 1 Discharge Agent     (HTTP on :8103)
    - 1 Facilities Agent
    All under a single Bureau on :8200.

uAgents has a ``Bureau`` helper that runs many agents on one event
loop — perfect for a hackathon demo where we don't want to juggle
five terminals. The patient agents discover the floor agent via the
in-process ``floor_agent.address`` rather than env vars; the Phase 2
agents discover each other through ``set_targets()`` on each
module so everyone has every address before ``bureau.run()``.
"""

from __future__ import annotations

import os

from uagents import Bureau

from agents.bed_agent import bed_agent, set_targets as set_bed_targets
from agents.discharge_agent import (
    discharge_agent,
    set_targets as set_discharge_targets,
)
from agents.facilities_agent import (
    facilities_agent,
    set_targets as set_facilities_targets,
)
from agents.floor_aggregator import floor_agent
from agents.mock_vitals import roster_from_env
from agents.patient_agent import build_patient_agent


def main() -> None:
    bureau_port = int(os.environ.get("BUREAU_PORT", "8200"))
    bureau = Bureau(
        port=bureau_port,
        endpoint=[f"http://127.0.0.1:{bureau_port}/submit"],
    )

    bureau.add(floor_agent)
    bureau.add(bed_agent)
    bureau.add(discharge_agent)
    bureau.add(facilities_agent)

    floor_address      = floor_agent.address
    bed_address        = bed_agent.address
    discharge_address  = discharge_agent.address
    facilities_address = facilities_agent.address

    # Wire the Phase 2 cross-agent address graph BEFORE bureau.run()
    # so handlers never see empty target strings.
    set_bed_targets(
        discharge=discharge_address,
        facilities=facilities_address,
    )
    set_discharge_targets(
        bed=bed_address,
        facilities=facilities_address,
        floor=floor_address,
    )
    set_facilities_targets(bed=bed_address)

    print("=" * 72)
    print(f"Floor aggregator address  : {floor_address}")
    print(f"Bed agent address         : {bed_address}")
    print(f"Discharge agent address   : {discharge_address}")
    print(f"Facilities agent address  : {facilities_address}")
    print("HTTP endpoints:")
    print(f"  staff manual            : http://127.0.0.1:{os.environ.get('STAFF_HTTP_PORT', '8101')}/staff/patient/manual")
    print(f"  bed reservation         : http://127.0.0.1:{os.environ.get('BED_HTTP_PORT', '8102')}/bed/reserve")
    print(f"  discharge start         : http://127.0.0.1:{os.environ.get('DISCHARGE_HTTP_PORT', '8103')}/discharge/start")
    print("=" * 72)

    base_port = int(os.environ.get("PATIENT_BASE_PORT", "8001"))
    for i, spec in enumerate(roster_from_env()):
        agent = build_patient_agent(
            patient_id=spec["patient_id"],
            room=spec["room"],
            full_name=spec["full_name"],
            scenario=spec["scenario"],
            port=base_port + i,
            floor_address=floor_address,
        )
        bureau.add(agent)
        print(
            f"  + patient agent room {spec['room']:>3} "
            f"({spec['full_name']:<18} | {spec['scenario']}) on "
            f"port {base_port + i}, address {agent.address}"
        )

    print("=" * 72)
    print("Starting bureau. Ctrl+C to stop.")
    bureau.run()


if __name__ == "__main__":
    main()
