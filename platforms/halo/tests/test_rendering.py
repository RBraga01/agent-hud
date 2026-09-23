import time

from conftest import PROJECT_ROOT, request_message
from halo_emulator import HaloEmulator

FINAL_DIR = PROJECT_ROOT / "artifacts" / "screenshots" / "final"


def save_frame(emulator: HaloEmulator, name: str) -> bytes:
    image = emulator.get_framebuffer()
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    image.save(FINAL_DIR / name)
    return image.tobytes()


def test_major_states_render_distinct_framebuffers(hud_emulator: HaloEmulator) -> None:
    hud_emulator.inject_bluetooth_data(request_message("request_primary.json"))
    time.sleep(0.1)
    frames = [save_frame(hud_emulator, "pending.png")]

    hud_emulator.inject_button_double()
    hud_emulator.inject_button_double()
    time.sleep(0.1)
    frames.append(save_frame(hud_emulator, "action-menu.png"))

    hud_emulator.inject_button_double()
    time.sleep(0.1)
    frames.append(save_frame(hud_emulator, "confirmation.png"))

    hud_emulator.inject_bluetooth_data(request_message("request_stale.json"))
    time.sleep(0.1)
    frames.append(save_frame(hud_emulator, "stale.png"))

    assert len(set(frames)) == 4
    assert hud_emulator.get_bluetooth_sent() == []
