import time

from conftest import PROJECT_ROOT, request_message, result_message, wait_for_sent
from halo_emulator import HaloEmulator

OUTPUT_DIR = PROJECT_ROOT / "artifacts" / "screenshots" / "simulation-2026-09-20"


def capture(emulator: HaloEmulator, name: str) -> None:
    time.sleep(0.08)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    emulator.get_framebuffer().save(OUTPUT_DIR / name)


def test_profile_b_menu_has_a_distinct_input_hint(
    hud_emulator: HaloEmulator, hud_emulator_b: HaloEmulator
) -> None:
    hud_emulator.inject_bluetooth_data(request_message("request_primary.json"))
    hud_emulator.inject_button_double()
    hud_emulator.inject_button_double()

    hud_emulator_b.inject_bluetooth_data(request_message("request_primary.json"))
    hud_emulator_b.inject_button_single()
    hud_emulator_b.inject_button_single()
    time.sleep(0.1)

    assert (
        hud_emulator.get_framebuffer().tobytes()
        != hud_emulator_b.get_framebuffer().tobytes()
    )


def test_profile_b_real_input_session(hud_emulator_b: HaloEmulator) -> None:
    capture(hud_emulator_b, "00-quiet-boot.png")

    hud_emulator_b.inject_bluetooth_data(request_message("request_two_actions.json"))
    capture(hud_emulator_b, "01-ble-request-attention.png")

    hud_emulator_b.inject_button_single()
    capture(hud_emulator_b, "02-single-click-request.png")

    hud_emulator_b.inject_button_single()
    capture(hud_emulator_b, "03-single-click-menu-primary.png")

    hud_emulator_b.inject_imu_tap("single")
    capture(hud_emulator_b, "04-imu-tap-menu-secondary.png")
    assert hud_emulator_b.get_bluetooth_sent() == []

    hud_emulator_b.inject_button_double()
    capture(hud_emulator_b, "05-double-click-confirmation.png")
    assert hud_emulator_b.get_bluetooth_sent() == []

    hud_emulator_b.inject_button_double()
    capture(hud_emulator_b, "06-double-click-sending.png")
    expected = (
        b'\x20{"type":"decision","request_id":"req-002",'
        b'"version":3,"action_id":"inspect_diff"}'
    )
    assert wait_for_sent(hud_emulator_b, 1) == [expected]

    hud_emulator_b.inject_bluetooth_data(result_message("req-002", 3, "ack"))
    capture(hud_emulator_b, "07-ble-ack.png")

    hud_emulator_b.inject_button_long()
    capture(hud_emulator_b, "08-long-press-quiet.png")


def test_profile_b_cancel_and_stale_sessions(hud_emulator_b: HaloEmulator) -> None:
    hud_emulator_b.inject_bluetooth_data(request_message("request_primary.json"))
    hud_emulator_b.inject_button_single()
    hud_emulator_b.inject_button_single()
    hud_emulator_b.inject_imu_tap("single")
    capture(hud_emulator_b, "09-imu-tap-cancel-focused.png")

    hud_emulator_b.inject_button_double()
    capture(hud_emulator_b, "10-double-click-cancelled-quiet.png")
    assert hud_emulator_b.get_bluetooth_sent() == []

    hud_emulator_b.inject_bluetooth_data(request_message("request_primary.json"))
    hud_emulator_b.inject_button_single()
    hud_emulator_b.inject_button_single()
    hud_emulator_b.inject_button_double()
    hud_emulator_b.inject_bluetooth_data(request_message("request_stale.json"))
    capture(hud_emulator_b, "11-version-update-stale.png")
    assert hud_emulator_b.get_bluetooth_sent() == []
