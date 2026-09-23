import time

from conftest import PROJECT_ROOT, enter_confirmation, request_message
from halo_emulator import HaloEmulator

STALE_SCREENSHOT = (
    PROJECT_ROOT / "artifacts" / "screenshots" / "progress" / "h1-stale.png"
)


def test_higher_version_blocks_send_and_enters_stale(
    hud_emulator: HaloEmulator,
) -> None:
    enter_confirmation(hud_emulator, "request_primary.json")
    hud_emulator.inject_bluetooth_data(request_message("request_stale.json"))
    time.sleep(0.15)

    assert hud_emulator.get_bluetooth_sent() == []
    STALE_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    hud_emulator.get_framebuffer().save(STALE_SCREENSHOT)
    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "STALE"
    assert hud_emulator.execute_lua("return agent_hud.state.latest_version") == 2


def test_stale_reload_uses_new_version_without_sending(
    hud_emulator: HaloEmulator,
) -> None:
    enter_confirmation(hud_emulator, "request_primary.json")
    hud_emulator.inject_bluetooth_data(request_message("request_stale.json"))
    time.sleep(0.1)
    hud_emulator.inject_button_double()
    time.sleep(0.1)

    assert hud_emulator.get_bluetooth_sent() == []
    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "ATTENTION"
    assert hud_emulator.execute_lua("return agent_hud.state.request.version") == 2
