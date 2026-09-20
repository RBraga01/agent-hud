"""Identical normative vectors, executed inside the real Lua application VM."""

import hashlib
import json
import time

import pytest
from conftest import APP_DIR, PROBE_DIR, PROJECT_ROOT
from halo_emulator import HaloEmulator

CONTRACT_DIR = PROJECT_ROOT.parents[1] / "core"


def vectors():
    return json.loads(
        (CONTRACT_DIR / "conformance/vectors/decision-lifecycle.json").read_text()
    )


def test_halo_uses_the_repository_contract_instead_of_a_private_copy():
    assert (CONTRACT_DIR / "contracts/protocol.md").is_file()
    assert (CONTRACT_DIR / "conformance/vectors/decision-lifecycle.json").is_file()
    assert not (PROJECT_ROOT / "core").exists()


@pytest.fixture(scope="module")
def conformance_report():
    rows = []
    yield rows
    if len(rows) != len(vectors()["cases"]):
        return
    source = CONTRACT_DIR / "conformance/vectors/decision-lifecycle.json"
    report = {
        "contract_version": vectors()["contract_version"],
        "vector_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "runtime": "Halo Lua 5.4 in halo-emulator 2.0.1",
        "cases": rows,
    }
    output = PROJECT_ROOT / "artifacts/m0-conformance-halo.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def run_vector(emulator, case, session):
    def inject(code, payload):
        emulator.inject_bluetooth_data(bytes([code]) + json.dumps(payload).encode())
        time.sleep(0.03)

    presentation = {
        "title": "Example decision",
        "short_context": "Review the offered action.",
    }
    inject(
        0x12,
        {"session_id": session, "task": case["initial"], "presentation": presentation},
    )
    emulator.inject_button_single()
    emulator.inject_button_single()
    time.sleep(0.03)
    inject(0x7E, {"type": "observe"})
    bootstrap = [
        json.loads(m[1:]) for m in emulator.get_bluetooth_sent() if m[0] == 0x7F
    ]
    assert bootstrap and bootstrap[-1]["state"] == "ACTION_MENU", "Task did not load"
    emulator.clear_bluetooth_sent()
    for event in case["events"]:
        if event["type"] == "update":
            inject(
                0x12,
                {
                    "session_id": session,
                    "task": event["task"],
                    "presentation": presentation,
                },
            )
        elif event["type"] == "result":
            inject(0x13, event["result"])
        else:
            inject(0x7E, event)
    inject(0x7E, {"type": "observe"})
    deadline = time.monotonic() + 2
    while not any(m[0] == 0x7F for m in emulator.get_bluetooth_sent()):
        assert time.monotonic() < deadline, "Lua observer did not respond"
        time.sleep(0.01)
    messages = emulator.get_bluetooth_sent()
    assert emulator.get_error() is None
    transmissions = [json.loads(m[1:]) for m in messages if m[0] == 0x22]
    observed = [json.loads(m[1:]) for m in messages if m[0] == 0x7F][-1]
    status = observed["result"]
    if status:
        assert (
            observed["state"]
            == {
                "ACCEPTED": "ACK",
                "STALE": "STALE",
                "INVALID_ACTION": "REJECTED",
                "ERROR": "ERROR",
            }[status]
        )
    assert transmissions == case["expected_transmissions"]
    assert (
        list({d["decision_id"]: d for d in transmissions}.values())
        == case["expected_decisions"]
    )
    assert status == case["expected_result"]
    return {"name": case["name"], "transmissions": transmissions, "result": status}


@pytest.mark.parametrize("case", vectors()["cases"], ids=lambda case: case["name"])
def test_m0_vector(case, tmp_path, conformance_report):
    with HaloEmulator(sandbox_dir=tmp_path / "sandbox", print_handler=None) as emulator:
        emulator.load_directory(APP_DIR)
        emulator.load_directory(PROBE_DIR)
        emulator.start("m0_conformance.lua")
        time.sleep(0.05)
        conformance_report.append(run_vector(emulator, case, vectors()["id_session"]))
