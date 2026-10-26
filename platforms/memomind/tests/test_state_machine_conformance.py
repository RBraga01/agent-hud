from __future__ import annotations

import ctypes
import itertools
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

PLATFORM_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PLATFORM_ROOT.parents[1]
VECTORS = (
    REPOSITORY_ROOT
    / "core"
    / "conformance"
    / "vectors"
    / "decision-lifecycle.json"
)


def _compiler() -> str:
    for candidate in (os.environ.get("CC"), "cc", "clang", "gcc"):
        if candidate and shutil.which(candidate):
            return candidate
    pytest.skip("a native C compiler is required for MemoMind conformance")


def _library(tmp_path: Path) -> ctypes.CDLL:
    library_name = "state-fixture.dll" if os.name == "nt" else "libstate-fixture.so"
    output = tmp_path / library_name
    command = [
        _compiler(),
        "-shared",
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(PLATFORM_ROOT / "glasses" / "src"),
        str(PLATFORM_ROOT / "tests" / "glasses" / "state_fixture_bridge.c"),
        str(PLATFORM_ROOT / "glasses" / "src" / "agent_hud_state.c"),
        "-o",
        str(output),
    ]
    if os.name == "nt" and Path(command[0]).name.lower().startswith("clang"):
        command[2:2] = ["-nostdlib", "-fuse-ld=lld", "-Wl,/noentry"]
    else:
        command[2:2] = ["-fPIC"]
    subprocess.run(
        command, check=True, cwd=PLATFORM_ROOT, capture_output=True, text=True
    )
    library = ctypes.CDLL(str(output))
    string = ctypes.c_char_p
    library.ah_fixture_reset.argtypes = [
        string,
        string,
        ctypes.c_uint64,
        string,
        string,
        string,
        string,
    ]
    library.ah_fixture_apply.argtypes = [
        ctypes.c_int,
        string,
        string,
        ctypes.c_uint64,
        ctypes.c_int,
        ctypes.c_int,
    ]
    library.ah_fixture_transmission_count.restype = ctypes.c_uint32
    for name in ("decision_id", "task_id", "action_id"):
        getattr(library, f"ah_fixture_{name}").argtypes = [ctypes.c_uint32]
        getattr(library, f"ah_fixture_{name}").restype = string
    library.ah_fixture_revision.argtypes = [ctypes.c_uint32]
    library.ah_fixture_revision.restype = ctypes.c_uint64
    library.ah_fixture_result.restype = ctypes.c_int
    return library


def _bytes(value: str | None) -> bytes | None:
    return value.encode() if value is not None else None


def _reset(library: ctypes.CDLL, case: dict) -> None:
    initial = case["initial"]
    actions = initial["actions"]
    padded = actions + [{"action_id": None, "label": None}] * (2 - len(actions))
    library.ah_fixture_reset(
        b"m0-session",
        _bytes(initial["task_id"]),
        initial["revision"],
        _bytes(padded[0]["action_id"]),
        _bytes(padded[0]["label"]),
        _bytes(padded[1]["action_id"]),
        _bytes(padded[1]["label"]),
    )


EVENT = {
    "focus": 1,
    "select": 2,
    "confirm": 3,
    "cancel": 4,
    "update": 5,
    "result": 6,
    "retry": 7,
}
RESULT = {"ACCEPTED": 1, "STALE": 2, "INVALID_ACTION": 3, "ERROR": 4, "DUPLICATE": 5}


def _apply(library: ctypes.CDLL, event: dict) -> None:
    payload = event.get("task") or event.get("result") or {}
    identifier = event.get("action_id") or payload.get("decision_id")
    task_id = payload.get("task_id")
    revision = payload.get("revision", 0)
    status = RESULT.get(payload.get("status"), 0)
    original = RESULT.get(payload.get("original_status"), 0)
    library.ah_fixture_apply(
        EVENT[event["type"]],
        _bytes(identifier),
        _bytes(task_id),
        revision,
        status,
        original,
    )


def _decision(library: ctypes.CDLL, index: int) -> dict:
    return {
        "decision_id": library.ah_fixture_decision_id(index).decode(),
        "task_id": library.ah_fixture_task_id(index).decode(),
        "revision": library.ah_fixture_revision(index),
        "action_id": library.ah_fixture_action_id(index).decode(),
    }


def test_memomind_core_runs_the_shared_decision_lifecycle_vectors(tmp_path: Path):
    suite = json.loads(VECTORS.read_text())
    library = _library(tmp_path)

    for case in suite["cases"]:
        _reset(library, case)
        for event in case["events"]:
            _apply(library, event)

        count = library.ah_fixture_transmission_count()
        transmissions = [_decision(library, index) for index in range(count)]
        decisions = list({item["decision_id"]: item for item in transmissions}.values())
        expected_result = case["expected_result"]
        observed_result = library.ah_fixture_result()

        assert transmissions == case["expected_transmissions"], case["name"]
        assert decisions == case["expected_decisions"], case["name"]
        assert observed_result == RESULT.get(expected_result, 0), case["name"]


def test_no_event_sequence_without_confirmation_can_transmit(tmp_path: Path):
    library = _library(tmp_path)
    case = json.loads(VECTORS.read_text())["cases"][0]
    candidates = (
        {"type": "focus", "action_id": "approve"},
        {"type": "select", "action_id": "approve"},
        {"type": "cancel"},
        {
            "type": "update",
            "task": {"task_id": "task-1", "revision": 4},
        },
        {"type": "retry"},
    )

    for sequence in itertools.product(candidates, repeat=4):
        _reset(library, case)
        for event in sequence:
            _apply(library, event)
        assert library.ah_fixture_transmission_count() == 0, sequence


def test_restart_drops_confirmation_without_transmitting(tmp_path: Path):
    library = _library(tmp_path)
    case = json.loads(VECTORS.read_text())["cases"][0]
    _reset(library, case)
    _apply(library, {"type": "select", "action_id": "approve"})
    assert library.ah_fixture_transmission_count() == 0

    _reset(library, case)
    assert library.ah_fixture_transmission_count() == 0
    assert library.ah_fixture_result() == 0
