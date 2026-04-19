"""
Bring up the full VitalWatch agent mesh in one Python process.

Usage:
    python -m scripts.run_all

Spawns:
    - 1 Floor Aggregator on :8100
    - 4 Patient Agents on :8001..:8004 (rooms 301, 302, 303, 305)

uAgents has a `Bureau` helper that runs many agents on one event
loop — perfect for a hackathon demo where we don't want to juggle
five terminals. The patient agents discover the floor agent via the
in-process `floor_agent.address` rather than env vars, so this works
out of the box with no `.env` setup.
"""

from __future__ import annotations

import os

from uagents import Bureau

from agents.floor_aggregator import floor_agent
from agents.mock_vitals import roster_from_env
from agents.patient_agent import build_patient_agent


def main() -> None:
    # Bureau owns a single uvicorn server for all in-process agents.
    # Pin it to 8200 so we don't collide with the dashboard's Vite
    # dev server (5173) or anything sitting on the default 8000.
    bureau_port = int(os.environ.get("BUREAU_PORT", "8200"))
    bureau = Bureau(
        port=bureau_port,
        endpoint=[f"http://127.0.0.1:{bureau_port}/submit"],
    )
    bureau.add(floor_agent)

    floor_address = floor_agent.address
    print("=" * 72)
    print(f"Floor aggregator address: {floor_address}")
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
