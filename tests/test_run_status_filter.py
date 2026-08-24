"""Root-level suite so `pytest tests` covers run-status filtering without Poetry."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = (
    Path(__file__).resolve().parents[1] / "autogpt_platform" / "backend"
)
sys.path.insert(0, str(BACKEND_ROOT))

from backend.util.run_status_filter import (  # noqa: E402
    filter_runs_by_status,
    parse_status_values,
    resolve_run_status_filter,
    resolve_status_group,
)


def test_parse_status_values_keeps_known_and_ignores_junk():
    assert parse_status_values(["failed", " QUEUED ", "drop table"]) == [
        "FAILED",
        "QUEUED",
    ]
    assert parse_status_values([]) is None
    assert parse_status_values(None) is None
    assert parse_status_values(["nope"]) is None


def test_resolve_status_group_presets():
    assert resolve_status_group("failed") == [
        "FAILED",
        "TERMINATED",
        "INCOMPLETE",
    ]
    assert resolve_status_group("RUNNING") == ["RUNNING", "QUEUED"]
    assert resolve_status_group("completed") == ["COMPLETED"]
    assert resolve_status_group("all") is None
    assert resolve_status_group("unknown") is None


def test_resolve_run_status_filter_prefers_group_over_explicit_list():
    assert resolve_run_status_filter(
        status_group="failed", statuses=["COMPLETED"]
    ) == ["FAILED", "TERMINATED", "INCOMPLETE"]
    assert resolve_run_status_filter(statuses=["completed"]) == ["COMPLETED"]


def test_filter_runs_by_status_keeps_matching_rows():
    runs = [
        {"id": "1", "status": "COMPLETED"},
        {"id": "2", "status": "FAILED"},
        {"id": "3", "status": "TERMINATED"},
        {"id": "4", "status": "RUNNING"},
        {"id": "5", "status": "QUEUED"},
    ]
    failed = filter_runs_by_status(runs, "failed")
    assert [row["id"] for row in failed] == ["2", "3"]

    running = filter_runs_by_status(runs, "running")
    assert [row["id"] for row in running] == ["4", "5"]

    assert len(filter_runs_by_status(runs, "all")) == 5
    assert filter_runs_by_status(runs, "completed") == [runs[0]]
