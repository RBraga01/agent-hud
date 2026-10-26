from __future__ import annotations

import ctypes
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _compiler() -> str:
    for candidate in (os.environ.get("CC"), "cc", "clang", "gcc"):
        if candidate and shutil.which(candidate):
            return candidate
    pytest.skip("a native C compiler is required for MemoMind adapter tests")


def test_display_and_input_adapters_preserve_state_boundaries(tmp_path: Path):
    output = tmp_path / ("adapter-test.dll" if os.name == "nt" else "adapter-test")
    command = [
        _compiler(),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(ROOT / "glasses" / "src"),
        str(ROOT / "tests" / "glasses" / "adapter_test.c"),
        str(ROOT / "glasses" / "src" / "agent_hud_state.c"),
        str(ROOT / "glasses" / "src" / "agent_hud_theme.c"),
        str(ROOT / "glasses" / "src" / "agent_hud_view.c"),
        str(ROOT / "glasses" / "src" / "input_mapping.c"),
        "-o",
        str(output),
    ]
    if os.name == "nt" and Path(command[0]).name.lower().startswith("clang"):
        command[1:1] = ["-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry"]
    subprocess.run(command, check=True, cwd=ROOT, capture_output=True, text=True)
    if os.name == "nt":
        run_test = ctypes.CDLL(str(output)).run_adapter_test
        run_test.restype = ctypes.c_int
        assert run_test() == 0
    else:
        subprocess.run([str(output)], check=True, cwd=ROOT)


def test_both_physical_input_journeys_and_restart_are_safe(tmp_path: Path):
    output = tmp_path / ("journey-test.dll" if os.name == "nt" else "journey-test")
    command = [
        _compiler(),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(ROOT / "glasses" / "src"),
        str(ROOT / "tests" / "glasses" / "journey_test.c"),
        str(ROOT / "glasses" / "src" / "agent_hud_state.c"),
        str(ROOT / "glasses" / "src" / "input_mapping.c"),
        "-o",
        str(output),
    ]
    if os.name == "nt" and Path(command[0]).name.lower().startswith("clang"):
        command[1:1] = ["-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry"]
    subprocess.run(command, check=True, cwd=ROOT, capture_output=True, text=True)
    if os.name == "nt":
        run_test = ctypes.CDLL(str(output)).run_journey_test
        run_test.restype = ctypes.c_int
        assert run_test() == 0
    else:
        subprocess.run([str(output)], check=True, cwd=ROOT)


def test_native_renderer_uses_distinct_composed_hud_states(tmp_path: Path):
    output = tmp_path / ("renderer-test.dll" if os.name == "nt" else "renderer-test")
    command = [
        _compiler(),
        "-std=c11",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(ROOT / "glasses" / "src"),
        "-I",
        str(ROOT / "vendor" / "plugin-open-platform" / "GlassSDK" / "include"),
        str(ROOT / "tests" / "glasses" / "renderer_test.c"),
        str(ROOT / "glasses" / "src" / "agent_hud_renderer.c"),
        str(ROOT / "glasses" / "src" / "agent_hud_theme.c"),
        "-o",
        str(output),
    ]
    if os.name == "nt" and Path(command[0]).name.lower().startswith("clang"):
        command[1:1] = ["-shared", "-nostdlib", "-fuse-ld=lld", "-Wl,/noentry"]
    subprocess.run(command, check=True, cwd=ROOT, capture_output=True, text=True)
    if os.name == "nt":
        run_test = ctypes.CDLL(str(output)).run_renderer_test
        run_test.restype = ctypes.c_int
        assert run_test() == 0
    else:
        subprocess.run([str(output)], check=True, cwd=ROOT)
