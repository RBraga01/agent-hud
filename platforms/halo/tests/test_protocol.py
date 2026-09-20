from conftest import wait_for_sent
from halo_emulator import HaloEmulator


def test_ble_receive_can_trigger_a_captured_send(event_probe: HaloEmulator) -> None:
    event_probe.inject_bluetooth_data(b"agent-request")

    assert wait_for_sent(event_probe, 1) == [b"ble:agent-request"]


def test_orientation_is_deterministic_in_emulator(event_probe: HaloEmulator) -> None:
    event_probe.set_imu_direction(pitch=15.0, roll=-5.0, heading=99.0)
    event_probe.inject_bluetooth_data(b"read-direction")

    assert wait_for_sent(event_probe, 1) == [b"direction:15.0,-5.0,0.0"]
