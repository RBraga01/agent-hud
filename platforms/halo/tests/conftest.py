import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from halo_emulator import HaloEmulator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

APP_DIR = PROJECT_ROOT / "app"
PROBE_DIR = PROJECT_ROOT / "tests" / "lua"
FIXTURE_DIR = PROJECT_ROOT / "tests" / "fixtures"


@pytest.fixture
def hud_emulator(tmp_path: Path) -> Iterator[HaloEmulator]:
    yield from _running_hud(tmp_path, "main.lua")


@pytest.fixture
def hud_emulator_b(tmp_path: Path) -> Iterator[HaloEmulator]:
    yield from _running_hud(tmp_path, "main_profile_b.lua")


def _running_hud(tmp_path: Path, script: str) -> Iterator[HaloEmulator]:
    emulator = HaloEmulator(sandbox_dir=tmp_path / "sandbox", print_handler=None)
    emulator.load_directory(APP_DIR)
    emulator.start(script)
    time.sleep(0.05)
    yield emulator
    if emulator.is_running():
        emulator.stop()


@pytest.fixture
def event_probe(tmp_path: Path) -> Iterator[HaloEmulator]:
    assert (PROBE_DIR / "h0_event_probe.lua").is_file(), "H0 event probe is missing"
    emulator = HaloEmulator(sandbox_dir=tmp_path / "sandbox", print_handler=None)
    emulator.load_directory(PROBE_DIR)
    emulator.start("h0_event_probe.lua")
    time.sleep(0.05)
    yield emulator
    if emulator.is_running():
        emulator.stop()


def wait_for_sent(emulator: HaloEmulator, count: int) -> list[bytes]:
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline:
        sent = emulator.get_bluetooth_sent()
        if len(sent) >= count:
            return sent
        time.sleep(0.01)
    return emulator.get_bluetooth_sent()


def request_message(name: str) -> bytes:
    return bytes([0x10]) + (FIXTURE_DIR / name).read_bytes()


def result_message(request_id: str, version: int, status: str) -> bytes:
    payload = (
        f'{{"type":"result","request_id":"{request_id}",'
        f'"version":{version},"status":"{status}"}}'
    )
    return bytes([0x11]) + payload.encode()


def enter_confirmation(
    emulator: HaloEmulator, fixture_name: str, navigation_steps: int = 0
) -> None:
    emulator.inject_bluetooth_data(request_message(fixture_name))
    emulator.inject_button_double()
    emulator.inject_button_double()
    for _ in range(navigation_steps):
        emulator.inject_button_single()
    emulator.inject_button_double()
    time.sleep(0.15)
