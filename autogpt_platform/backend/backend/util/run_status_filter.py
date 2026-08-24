"""Pure helpers for filtering agent-run lists by status (no Prisma)."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence

KNOWN_STATUSES = frozenset(
    {"QUEUED", "RUNNING", "COMPLETED", "TERMINATED", "FAILED", "INCOMPLETE"}
)

STATUS_GROUPS: dict[str, tuple[str, ...]] = {
    "failed": ("FAILED", "TERMINATED", "INCOMPLETE"),
    "running": ("RUNNING", "QUEUED"),
    "completed": ("COMPLETED",),
}


def parse_status_values(raw: Sequence[str] | None) -> list[str] | None:
    """Return known execution statuses from a query list, or None if unrestricted."""
    if not raw:
        return None
    parsed = [item.strip().upper() for item in raw if item and item.strip()]
    known = [item for item in parsed if item in KNOWN_STATUSES]
    return known or None


def resolve_status_group(group: str | None) -> list[str] | None:
    """Map a preset group name to concrete statuses."""
    if not group:
        return None
    key = group.strip().lower()
    if key in {"", "all"}:
        return None
    statuses = STATUS_GROUPS.get(key)
    return list(statuses) if statuses else None


def resolve_run_status_filter(
    *,
    status_group: str | None = None,
    statuses: Sequence[str] | None = None,
) -> list[str] | None:
    """Prefer a named group, otherwise an explicit status list."""
    grouped = resolve_status_group(status_group)
    if grouped is not None:
        return grouped
    return parse_status_values(statuses)


def filter_runs_by_status(
    runs: Iterable[Mapping[str, object]],
    status_group: str | None = None,
) -> list[Mapping[str, object]]:
    """Keep runs whose ``status`` is in the named group. ``all`` returns a new list."""
    allowed = resolve_status_group(status_group)
    if allowed is None:
        return list(runs)
    allowed_set = set(allowed)
    return [run for run in runs if str(run.get("status", "")).upper() in allowed_set]
