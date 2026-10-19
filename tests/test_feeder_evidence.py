"""Only proven feeder reads may certify an empty companion snapshot."""

import pytest

from agent_hud.config import Settings
from feeders import FileFeederError, collect_with_evidence


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
