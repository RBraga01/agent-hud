import time

from conftest import PROJECT_ROOT, request_message, wait_for_sent
from halo_emulator import HaloEmulator

PROFILE_B_SCREENSHOT = (
    PROJECT_ROOT / "artifacts" / "screenshots" / "progress" / "h1-profile-b.png"
)


def test_button_events_are_distinct(event_probe: HaloEmulator) -> None:
    event_probe.inject_button_single()
    event_probe.inject_button_double()
    event_probe.inject_button_long()

    assert wait_for_sent(event_probe, 3) == [
        b"button:single",
        b"button:double",
        b"button:long",
    ]


def test_tap_events_are_distinct(event_probe: HaloEmulator) -> None:
    event_probe.inject_imu_tap("single")
    event_probe.inject_imu_tap("double")
    event_probe.inject_imu_tap("triple")

    assert wait_for_sent(event_probe, 3) == [
        b"tap:single",
        b"tap:double",
        b"tap:triple",
    ]


def enter_profile_b_confirmation(emulator: HaloEmulator) -> None:
    emulator.inject_bluetooth_data(request_message("request_two_actions.json"))
    emulator.inject_button_single()
    emulator.inject_button_single()
    emulator.inject_imu_tap("single")
    emulator.inject_button_double()
    time.sleep(0.15)


def test_profile_b_separates_navigation_selection_and_confirmation(
    hud_emulator_b: HaloEmulator,
) -> None:
    enter_profile_b_confirmation(hud_emulator_b)

    assert hud_emulator_b.get_bluetooth_sent() == []
    PROFILE_B_SCREENSHOT.parent.mkdir(parents=True, exist_ok=True)
    hud_emulator_b.get_framebuffer().save(PROFILE_B_SCREENSHOT)
    hud_emulator_b.stop()
    assert hud_emulator_b.execute_lua("return agent_hud.state.name") == "CONFIRMATION"
    assert (
        hud_emulator_b.execute_lua("return agent_hud.state.selected_action.id")
        == "inspect_diff"
    )


def test_profile_b_confirmation_sends_once(hud_emulator_b: HaloEmulator) -> None:
    enter_profile_b_confirmation(hud_emulator_b)
    hud_emulator_b.inject_button_double()
    expected = (
        b'\x20{"type":"decision","request_id":"req-002",'
        b'"version":3,"action_id":"inspect_diff"}'
    )
    assert wait_for_sent(hud_emulator_b, 1) == [expected]
    hud_emulator_b.inject_button_double()
    time.sleep(0.05)
    assert hud_emulator_b.get_bluetooth_sent() == [expected]


def test_profile_b_back_and_stale_send_nothing(hud_emulator_b: HaloEmulator) -> None:
    hud_emulator_b.inject_bluetooth_data(request_message("request_primary.json"))
    hud_emulator_b.inject_button_single()
    hud_emulator_b.inject_button_single()
    hud_emulator_b.inject_button_double()
    time.sleep(0.15)
    hud_emulator_b.inject_button_long()
    time.sleep(0.05)
    assert hud_emulator_b.get_bluetooth_sent() == []

    hud_emulator_b.inject_button_double()
    hud_emulator_b.inject_bluetooth_data(request_message("request_stale.json"))
    time.sleep(0.1)
    assert hud_emulator_b.get_bluetooth_sent() == []
    hud_emulator_b.stop()
    assert hud_emulator_b.execute_lua("return agent_hud.state.name") == "STALE"
