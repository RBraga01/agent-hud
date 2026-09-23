import time

from conftest import PROJECT_ROOT, enter_confirmation, result_message, wait_for_sent
from halo_emulator import HaloEmulator

CONFIRM_SCREENSHOT = (
    PROJECT_ROOT / "artifacts" / "screenshots" / "progress" / "h1-confirmation.png"
)
ACK_SCREENSHOT = PROJECT_ROOT / "artifacts" / "screenshots" / "progress" / "h1-ack.png"


def test_selecting_action_enters_confirmation_without_sending(
    hud_emulator: HaloEmulator,
) -> None:
    enter_confirmation(hud_emulator, "request_two_actions.json", navigation_steps=1)

    assert hud_emulator.get_bluetooth_sent() == []
    CONFIRM_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    hud_emulator.get_framebuffer().save(CONFIRM_SCREENSHOT)
    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "CONFIRMATION"
    assert (
        hud_emulator.execute_lua("return agent_hud.state.selected_action.id")
        == "inspect_diff"
    )


def test_confirmation_sends_once_and_matching_ack_is_rendered(
    hud_emulator: HaloEmulator,
) -> None:
    enter_confirmation(hud_emulator, "request_two_actions.json", navigation_steps=1)
    hud_emulator.inject_button_double()

    expected = (
        b'\x20{"type":"decision","request_id":"req-002",'
        b'"version":3,"action_id":"inspect_diff"}'
    )
    assert wait_for_sent(hud_emulator, 1) == [expected]
    hud_emulator.inject_button_double()
    time.sleep(0.05)
    assert hud_emulator.get_bluetooth_sent() == [expected]

    hud_emulator.inject_bluetooth_data(result_message("req-002", 3, "ack"))
    time.sleep(0.1)
    ACK_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    hud_emulator.get_framebuffer().save(ACK_SCREENSHOT)
    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "ACK"


def test_ack_can_close_to_quiet(hud_emulator: HaloEmulator) -> None:
    enter_confirmation(hud_emulator, "request_primary.json")
    hud_emulator.inject_button_double()
    assert len(wait_for_sent(hud_emulator, 1)) == 1
    hud_emulator.inject_bluetooth_data(result_message("req-001", 1, "ack"))
    time.sleep(0.1)
    hud_emulator.inject_button_long()
    time.sleep(0.05)

    hud_emulator.stop()
    assert hud_emulator.execute_lua("return agent_hud.state.name") == "QUIET"
