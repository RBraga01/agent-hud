"""Only proven feeder reads may certify an empty companion snapshot."""

import pytest
import requests

from agent_hud.config import Settings
from feeders import FileFeederError, collect_with_evidence
from tests.test_companion_contract import validator
from tests.test_companion_endpoint import PATH, _serve


def _settings(*feeders):
    return Settings(
        gateway_url="http://127.0.0.1:8765/tasks",
        poll_seconds=3,
        feeders=feeders,
    )


def test_simulated_feeder_reports_individual_evidence():
    report = collect_with_evidence(_settings("simulated"))
    assert report.verified_sources == ("simulated",)
    assert report.tasks


def test_file_feeder_needs_present_well_formed_list(tmp_path):
    path = tmp_path / "tasks.json"
    with pytest.raises(FileFeederError):
        collect_with_evidence(_settings("file"), file_path=path)

    path.write_text('{"tasks": []}', encoding="utf-8")
    report = collect_with_evidence(_settings("file"), file_path=path)
    assert report.tasks == []
    assert report.verified_sources == ("file",)

    path.write_text('{"tasks": [{}, "broken"]}', encoding="utf-8")
    with pytest.raises(FileFeederError):
        collect_with_evidence(_settings("file"), file_path=path)


def test_two_supported_sources_are_verified_individually_over_http(tmp_path):
    path = tmp_path / "tasks.json"
    path.write_text('{"tasks": []}', encoding="utf-8")
    settings = _settings("simulated", "file")
    base, cookie, refresher, _, stop = _serve(
        report=lambda: collect_with_evidence(settings, file_path=path),
        sources=("simulated", "file"),
    )
    try:
        assert refresher.sweep_once()
        healthy = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        validator("Snapshot").validate(healthy)
        assert healthy["complete"] is True
        assert [s["state"] for s in healthy["source_health"]] == [
            "healthy", "healthy"
        ]

        path.write_text('{"tasks": [{}]}', encoding="utf-8")
        assert refresher.sweep_once()
        broken = requests.get(base + PATH, cookies=cookie, timeout=5).json()
        validator("Snapshot").validate(broken)
        assert broken["complete"] is False
        assert all(s["state"] == "failed" for s in broken["source_health"])
    finally:
        stop()
