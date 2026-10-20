from __future__ import annotations

import ctypes
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _compiler() -> str:
    candidates = [os.environ.get("CC"), "cc", "clang", "gcc"]
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return candidate
    pytest.skip("a native C compiler is required for the MemoMind codec test")


def test_c_codec_matches_the_canonical_v2_vectors(tmp_path: Path):
    vectors = json.loads((ROOT / "protocol" / "vectors.json").read_text())
    request = bytes.fromhex(vectors["request"]["hex"])
    decision = bytes.fromhex(vectors["decision"]["hex"])
    result = bytes.fromhex(vectors["result"]["hex"])
    generated = tmp_path / "expected_protocol_vector.h"
    generated.write_text(
        "#define EXPECTED_REQUEST_BYTES {"
        + ",".join(f"0x{value:02x}U" for value in request)
        + "}\n#define EXPECTED_REQUEST_LENGTH "
        + str(len(request))
        + "U\n#define EXPECTED_DECISION_BYTES {"
        + ",".join(f"0x{value:02x}U" for value in decision)
        + "}\n#define EXPECTED_DECISION_LENGTH "
        + str(len(decision))
        + "U\n#define EXPECTED_RESULT_BYTES {"
        + ",".join(f"0x{value:02x}U" for value in result)
        + "}\n#define EXPECTED_RESULT_LENGTH "
        + str(len(result))
        + "U\n"
    )
    executable = tmp_path / (
        "protocol-test.dll" if os.name == "nt" else "protocol-test"
    )
    command = [
        _compiler(),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(ROOT / "glasses" / "src"),
        "-I",
        str(tmp_path),
        str(ROOT / "tests" / "glasses" / "protocol_test.c"),
        str(ROOT / "glasses" / "src" / "protocol.c"),
        str(ROOT / "glasses" / "src" / "round_trip.c"),
        str(ROOT / "glasses" / "src" / "freestanding_memory.c"),
        "-o",
        str(executable),
    ]
    if os.name == "nt" and Path(command[0]).name.lower().startswith("clang"):
        command[1:1] = [
            "-shared",
            "-nostdlib",
            "-fuse-ld=lld",
            "-Wl,/noentry",
        ]
    subprocess.run(command, check=True, cwd=ROOT, capture_output=True, text=True)
    if os.name == "nt":
        run_test = ctypes.CDLL(str(executable)).run_test
        run_test.restype = ctypes.c_int
        assert run_test() == 0
    else:
        subprocess.run([str(executable)], check=True, cwd=ROOT)


def test_c_state_machine_preserves_agent_hud_safety_contract(tmp_path: Path):
    executable = tmp_path / (
        "state-test.dll" if os.name == "nt" else "state-test"
    )
    command = [
        _compiler(),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(ROOT / "glasses" / "src"),
        str(ROOT / "tests" / "glasses" / "state_test.c"),
        str(ROOT / "glasses" / "src" / "agent_hud_state.c"),
        "-o",
        str(executable),
    ]
    if os.name == "nt" and Path(command[0]).name.lower().startswith("clang"):
        command[1:1] = [
            "-shared",
            "-nostdlib",
            "-fuse-ld=lld",
            "-Wl,/noentry",
        ]
    subprocess.run(command, check=True, cwd=ROOT, capture_output=True, text=True)
    if os.name == "nt":
        run_test = ctypes.CDLL(str(executable)).run_state_test
        run_test.restype = ctypes.c_int
        assert run_test() == 0
    else:
        subprocess.run([str(executable)], check=True, cwd=ROOT)
