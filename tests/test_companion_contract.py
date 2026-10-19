"""Machine-checkable safety cases for the reviewed companion HTTP draft."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from stub_server.companion_contract import validate_snapshot_semantics

SPEC = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "docs/api/companion-v1.openapi.yaml")
    .read_text(encoding="utf-8")
)


def validator(name):
    root = {"$ref": f"#/components/schemas/{name}", "components": SPEC["components"]}
    Draft202012Validator.check_schema(root)
    return Draft202012Validator(root, format_checker=FormatChecker())


def snapshot_example(name="verified_empty"):
    return deepcopy(
        SPEC["paths"]["/v1/companion/snapshots/current"]["get"]["responses"]
        ["200"]["content"]["application/json"]["examples"][name]["value"]
    )


def test_published_examples_validate():
    for name in ("verified_empty", "failed_source"):
        validator("Snapshot").validate(snapshot_example(name))


def test_every_component_is_valid_json_schema_2020_12():
    for schema in SPEC["components"]["schemas"].values():
        Draft202012Validator.check_schema(schema)


@pytest.mark.parametrize(
    "change",
    [
        {"source_health": []},
        {"source_health": [{"name": "simulated", "state": "failed",
                            "last_success_at": None, "fresh_until": None}]},
        {"source_health": [{"name": "simulated", "state": "healthy",
                            "last_success_at": None, "fresh_until": None}]},
        {"tasks": [{}]},
    ],
)
def test_complete_snapshot_rejects_missing_health_or_empty_task(change):
    snapshot = snapshot_example()
    snapshot.update(change)
    assert not validator("Snapshot").is_valid(snapshot)


@pytest.mark.parametrize(
    "change",
    [
        {"device_id": "bad id"},
        {"health": "healthy", "evidence": "none"},
        {"health": "healthy", "evidence": "verified_link",
         "last_verified_link_at": None},
        {"health": "unavailable", "evidence": "none"},
        {"health": "unavailable", "evidence": "verified_link",
         "last_verified_link_at": "2026-10-19T09:58:00Z",
         "absence_started_at": "2026-10-19T09:59:00Z",
         "failed_observations": 1},
        {"health": "healthy", "evidence": "verified_link",
         "last_verified_link_at": "2026-10-19T09:59:50Z",
         "presence_valid_until": "2026-10-19T10:00:10Z",
         "absence_started_at": "2026-10-19T09:59:00Z",
         "failed_observations": 2},
    ],
)
def test_device_health_requires_independent_evidence(change):
    device = {
        "device_id": "glasses-1",
        "health": "unknown",
        "evidence": "none",
        "last_authenticated_at": None,
        "last_verified_link_at": None,
        "presence_valid_until": None,
        "absence_started_at": None,
        "failed_observations": 0,
    }
    device.update(change)
    assert not validator("SelectedDevice").is_valid(device)


def test_unknown_device_with_only_token_activity_is_valid():
    validator("SelectedDevice").validate({
        "device_id": "glasses-1",
        "health": "unknown",
        "evidence": "none",
        "last_authenticated_at": "2026-10-19T10:00:00Z",
        "last_verified_link_at": None,
        "presence_valid_until": None,
        "absence_started_at": None,
        "failed_observations": 0,
    })


def test_normalized_informational_task_has_no_actions():
    task = {
        "task_id": "codex-1", "revision": 3, "source": "Codex",
        "title": "Parser work", "summary": "Waiting", "detail": "Needs review",
        "needs_you": True, "actions": [],
    }
    validator("CompanionTask").validate(task)
    assert not validator("CompanionTask").is_valid(dict(task, task_id="bad id"))


@pytest.mark.parametrize(
    "payload",
    [
        {"request_id": "d:1", "revision": 3, "type": "action"},
        {"request_id": "d:1", "revision": 3, "type": "message"},
        {"request_id": "bad id", "revision": 3, "type": "action",
         "action_id": "approve"},
        {"request_id": "d:1", "revision": 3, "type": "action",
         "action_id": "bad id"},
    ],
)
def test_feedback_rejects_missing_type_fields_and_invalid_ids(payload):
    assert not validator("Feedback").is_valid(payload)


def test_feedback_keeps_legacy_action_and_message_shapes():
    for payload in (
        {"request_id": "d:1", "revision": 3, "type": "action",
         "action_id": "approve"},
        {"request_id": "d:2", "revision": 3, "type": "message",
         "text": "Please check"},
    ):
        validator("Feedback").validate(payload)


def test_error_distinguishes_stale_and_id_conflict_without_requiring_new_field():
    errors = validator("Error")
    errors.validate({"status": "stale", "error": "task changed", "revision": 4})
    errors.validate({"code": "id_conflict", "error": "content changed"})
    errors.validate({"error": "legacy error without discriminator"})
    assert not errors.is_valid({"status": "stale", "code": "id_conflict",
                                "error": "contradiction"})


def test_409_has_a_formal_stale_or_id_conflict_shape():
    conflicts = validator("ConflictError")
    conflicts.validate({"status": "stale", "revision": 5,
                        "error": "this task has changed"})
    conflicts.validate({"code": "id_conflict",
                        "error": "request_id content changed"})
    assert not conflicts.is_valid({"error": "ambiguous conflict"})
    assert not conflicts.is_valid({"status": "stale", "code": "id_conflict",
                                   "revision": 5, "error": "contradiction"})
    responses = SPEC["paths"]["/tasks/{task_id}/feedback"]["post"]["responses"]
    assert responses["409"]["$ref"] == "#/components/responses/Conflict"


def test_contract_declares_no_store_and_disables_submission():
    snapshot = validator("Snapshot")
    changed = snapshot_example()
    changed["decision_submission_enabled"] = True
    assert not snapshot.is_valid(changed)
    get = SPEC["paths"]["/v1/companion/snapshots/current"]["get"]
    assert get["security"] == [{"sessionCookie": []}]
    assert get["responses"]["200"]["headers"]["Cache-Control"]


def test_complete_source_must_be_current_at_observation_time():
    snapshot = snapshot_example()
    validate_snapshot_semantics(snapshot)
    snapshot["source_health"][0]["fresh_until"] = "2026-10-19T09:59:59Z"
    with pytest.raises(ValueError, match="source freshness"):
        validate_snapshot_semantics(snapshot)


def test_complete_source_cannot_report_success_from_the_future():
    snapshot = snapshot_example()
    snapshot["source_health"][0]["last_success_at"] = "2026-10-19T10:01:00Z"
    with pytest.raises(ValueError, match="source freshness"):
        validate_snapshot_semantics(snapshot)


def test_healthy_device_needs_fresh_real_evidence_at_observation_time():
    snapshot = snapshot_example()
    snapshot["selected_device"] = {
        "device_id": "glasses-1",
        "health": "healthy",
        "evidence": "verified_link",
        "last_authenticated_at": "2026-10-19T09:59:00Z",
        "last_verified_link_at": "2026-10-19T09:59:50Z",
        "presence_valid_until": "2026-10-19T10:00:10Z",
        "absence_started_at": None,
        "failed_observations": 0,
    }
    validate_snapshot_semantics(snapshot)
    snapshot["selected_device"]["presence_valid_until"] = "2026-10-19T09:59:59Z"
    with pytest.raises(ValueError, match="device freshness"):
        validate_snapshot_semantics(snapshot)
    snapshot["selected_device"]["presence_valid_until"] = "2026-10-19T10:00:10Z"
    snapshot["selected_device"]["evidence"] = "none"
    with pytest.raises(ValueError, match="independent evidence"):
        validate_snapshot_semantics(snapshot)


def test_unavailable_device_requires_sustained_independent_failures():
    snapshot = snapshot_example()
    snapshot["selected_device"] = {
        "device_id": "glasses-1",
        "health": "unavailable",
        "evidence": "verified_link",
        "last_authenticated_at": "2026-10-19T10:00:00Z",
        "last_verified_link_at": "2026-10-19T09:58:00Z",
        "presence_valid_until": "2026-10-19T09:58:10Z",
        "absence_started_at": "2026-10-19T09:59:30Z",
        "failed_observations": 2,
    }
    with pytest.raises(ValueError, match="absence threshold"):
        validate_snapshot_semantics(snapshot)
    snapshot["selected_device"]["absence_started_at"] = "2026-10-19T09:59:00Z"
    validate_snapshot_semantics(snapshot)
    snapshot["selected_device"]["presence_valid_until"] = "2026-10-19T10:00:10Z"
    with pytest.raises(ValueError, match="absence threshold"):
        validate_snapshot_semantics(snapshot)


def test_duplicate_task_or_action_identity_invalidates_complete_observation():
    snapshot = snapshot_example()
    task = {
        "task_id": "sim-1", "revision": 3, "source": "Simulated",
        "title": "Decision", "summary": "Waiting", "detail": "Review first",
        "needs_you": True,
        "actions": [{"action_id": "approve", "label": "Approve"},
                    {"action_id": "approve", "label": "Again"}],
    }
    snapshot["tasks"] = [task]
    with pytest.raises(ValueError, match="duplicate action"):
        validate_snapshot_semantics(snapshot)
    task["actions"].pop()
    snapshot["tasks"].append(deepcopy(task))
    with pytest.raises(ValueError, match="duplicate task"):
        validate_snapshot_semantics(snapshot)
