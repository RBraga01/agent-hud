import time

from conftest import PROJECT_ROOT, request_message
from halo_emulator import HaloEmulator

ATTENTION_SCREENSHOT = (
    PROJECT_ROOT / "artifacts" / "screenshots" / "progress" / "h1-attention.png"
)
MENU_SCREENSHOT = (
    PROJECT_ROOT / "artifacts" / "screenshots" / "progress" / "h1-action-menu.png"
)


def test_request_arrival_tracks_identity_and_shows_attention(
    hud_emulator: HaloEmulator,
) -> None:
    hud_emulator.inject_bluetooth_data(request_message("request_primary.json"))
    time.sleep(0.1)

    framebuffer = hud_emulator.get_framebuffer()
    assert any(sum(pixel[:3]) > 30 for pixel in framebuffer.getdata())
    assert hud_emulator.get_bluetooth_sent() == []
    ATTENTION_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    framebuffer.save(ATTENTION_SCREENSHOT)

    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "ATTENTION"
    assert (
        hud_emulator.execute_lua("return agent_hud.state.request.request_id")
        == "req-001"
    )
    assert hud_emulator.execute_lua("return agent_hud.state.request.version") == 1
    assert hud_emulator.execute_lua("return #agent_hud.state.request.actions") == 1


def test_invalid_request_stays_quiet_and_sends_nothing(
    hud_emulator: HaloEmulator,
) -> None:
    hud_emulator.inject_bluetooth_data(bytes([0x10]) + b'{"type":"request"}')
    time.sleep(0.1)

    assert hud_emulator.get_bluetooth_sent() == []
    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "QUIET"


def test_navigation_reaches_menu_and_never_sends(hud_emulator: HaloEmulator) -> None:
    hud_emulator.inject_bluetooth_data(request_message("request_two_actions.json"))
    hud_emulator.inject_button_double()
    hud_emulator.inject_button_double()
    hud_emulator.inject_button_single()
    time.sleep(0.15)

    assert hud_emulator.get_bluetooth_sent() == []
    MENU_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    hud_emulator.get_framebuffer().save(MENU_SCREENSHOT)
    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "ACTION_MENU"
    assert hud_emulator.execute_lua("return agent_hud.state.focus") == 2


def test_cancel_menu_entry_returns_to_quiet_without_sending(
    hud_emulator: HaloEmulator,
) -> None:
    hud_emulator.inject_bluetooth_data(request_message("request_two_actions.json"))
    hud_emulator.inject_button_double()
    hud_emulator.inject_button_double()
    for _ in range(3):
        hud_emulator.inject_button_single()
    hud_emulator.inject_button_double()
    time.sleep(0.15)

    assert hud_emulator.get_bluetooth_sent() == []
    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "QUIET"


def test_back_from_confirmation_never_sends(hud_emulator: HaloEmulator) -> None:
    hud_emulator.inject_bluetooth_data(request_message("request_primary.json"))
    hud_emulator.inject_button_double()
    hud_emulator.inject_button_double()
    hud_emulator.inject_button_double()
    hud_emulator.inject_button_long()
    time.sleep(0.15)

    assert hud_emulator.get_bluetooth_sent() == []
    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "ACTION_MENU"
