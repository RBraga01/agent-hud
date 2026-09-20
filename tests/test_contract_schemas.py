import json

import pytest
from jsonschema import Draft202012Validator
from test_decision_contract import ROOT, VECTORS


def validator(name):
    schema = json.loads(
        (ROOT / f"core/contracts/schemas/{name}.schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_all_normative_examples_match_schemas():
    task, decision, result = [validator(n) for n in ("task", "decision", "result")]
    for case in VECTORS["cases"]:
        task.validate(case["initial"])
        for emitted in case["expected_transmissions"]:
            decision.validate(emitted)
        for event in case["events"]:
            if event["type"] == "result":
                result.validate(event["result"])
            if event["type"] == "update":
                task.validate(event["task"])


@pytest.mark.parametrize(
    "change",
    [
        {"revision": True},
        {"revision": -1},
        {"revision": 2**53},
        {"decision_id": ""},
        {"task_id": "space invalid"},
        {"extra": "field"},
    ],
)
def test_decision_schema_rejects_invalid_identity(change):
    decision = dict(VECTORS["cases"][3]["expected_decisions"][0], **change)
    assert not validator("decision").is_valid(decision)


def test_duplicate_requires_an_original_outcome():
    result = {"decision_id": "d", "task_id": "t", "revision": 0, "status": "DUPLICATE"}
    assert not validator("result").is_valid(result)
    assert validator("result").is_valid(dict(result, original_status="STALE"))
    assert not validator("result").is_valid(dict(result, original_status="ERROR"))
