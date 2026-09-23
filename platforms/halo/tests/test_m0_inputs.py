import json
import time

from conftest import PROJECT_ROOT
from host.contract import CanonicalSession

TASK = {
    "task_id": "example-task",
    "revision": 3,
    "actions": [
        {"action_id": "approve", "label": "Approve"},
        {"action_id": "inspect", "label": "Inspect"},
    ],
}
OUTPUT = PROJECT_ROOT / "artifacts/screenshots/m0"


def capture(emulator, name):
    time.sleep(0.08)
    assert emulator.get_error() is None
    OUTPUT.mkdir(parents=True, exist_ok=True)
    emulator.get_framebuffer().save(OUTPUT / f"{name}.png")


def test_canonical_physical_inputs_retry_ack_and_screenshots(hud_emulator_b):
    emulator = hud_emulator_b
    host = CanonicalSession()
    emulator.inject_bluetooth_data(
        host.request(
            TASK,
            title="Review example change?",
            short_context="Example checks passed. Review the decision.",
        )
    )
    capture(emulator, "attention")
    emulator.inject_button_single()
    capture(emulator, "request")
    emulator.inject_button_single()
    emulator.inject_imu_tap("single")
    capture(emulator, "menu")
    emulator.inject_button_double()
    capture(emulator, "confirmation")
    assert emulator.get_bluetooth_sent() == []
    emulator.inject_button_double()
    capture(emulator, "sending")
    first = emulator.get_bluetooth_sent()
    assert len(first) == 1 and first[0][0] == 0x22
    decision = json.loads(first[0][1:])
    assert decision == {
        "decision_id": host.session_id + ":1",
        "task_id": TASK["task_id"],
        "revision": 3,
        "action_id": "inspect",
    }
    emulator.inject_bluetooth_data(host.result(decision, "ERROR"))
    capture(emulator, "delivery-unknown")
    emulator.inject_button_double()
    capture(emulator, "retry-confirmation")
    assert emulator.get_bluetooth_sent() == first
    emulator.inject_button_double()
    time.sleep(0.08)
    assert emulator.get_bluetooth_sent() == first + first
    emulator.inject_bluetooth_data(
        host.result(decision, "DUPLICATE", original_status="ACCEPTED")
    )
    capture(emulator, "accepted")
    emulator.inject_button_double()
    time.sleep(0.05)
    assert emulator.get_bluetooth_sent() == first + first


def test_session_ids_are_fresh_and_not_task_ids():
    first, second = CanonicalSession(), CanonicalSession()
    assert first.session_id != second.session_id
    assert len(first.session_id) == 32


def test_canonical_stale_blocks_send(hud_emulator_b):
    emulator, host = hud_emulator_b, CanonicalSession()

    def inject(task):
        emulator.inject_bluetooth_data(
            host.request(task, title="Example review", short_context="Example only")
        )
        time.sleep(0.05)

    inject(TASK)
    emulator.inject_button_single()
    emulator.inject_button_single()
    emulator.inject_button_double()
    inject(dict(TASK, revision=4))
    capture(emulator, "stale")
    assert emulator.get_bluetooth_sent() == []
