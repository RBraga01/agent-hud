import json
from dataclasses import asdict

import pytest
from test_decision_contract import ROOT, as_task

from stub_server.decision_contract import CanonicalGateway
from stub_server.policy import Policy

DATA = json.loads((ROOT / "core/conformance/vectors/gateway.json").read_text())


@pytest.mark.parametrize("case", DATA["cases"], ids=lambda case: case["name"])
def test_gateway_vector(case):
    task = asdict(as_task(DATA["initial"]))
    task["actions"] = {
        "primary": task.pop("primary"),
        "secondary": task.pop("secondary"),
    }
    gateway = CanonicalGateway(Policy(lambda: [task]))
    results = [gateway.receive(d) for d in case["decisions"]]
    assert [r["status"] for r in results] == case["expected"]
    if "original_status" in case:
        assert results[-1]["original_status"] == case["original_status"]
    if "reason" in case:
        assert results[-1]["reason"] == case["reason"]
