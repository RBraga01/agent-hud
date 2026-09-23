import time

from conftest import PROJECT_ROOT, enter_confirmation, result_message, wait_for_sent
from halo_emulator import HaloEmulator

ERROR_SCREENSHOT = (
    PROJECT_ROOT / "artifacts" / "screenshots" / "progress" / "h1-error.png"
)


def test_error_is_distinct_and_retry_requires_new_confirmation(
    hud_emulator: HaloEmulator,
) -> None:
    enter_confirmation(hud_emulator, "request_primary.json")
    hud_emulator.inject_button_double()
    first_send = wait_for_sent(hud_emulator, 1)
    assert len(first_send) == 1

    hud_emulator.inject_bluetooth_data(result_message("req-001", 1, "error"))
    time.sleep(0.1)
    ERROR_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    hud_emulator.get_framebuffer().save(ERROR_SCREENSHOT)

    hud_emulator.inject_button_double()
    time.sleep(0.05)
    assert hud_emulator.get_bluetooth_sent() == first_send

    hud_emulator.inject_button_double()
    assert len(wait_for_sent(hud_emulator, 2)) == 2
    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "SEND"
