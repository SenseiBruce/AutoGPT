"""Root-level suite so a fresh clone can run `pytest tests` without Poetry."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = (
    Path(__file__).resolve().parents[1] / "autogpt_platform" / "backend"
)
sys.path.insert(0, str(BACKEND_ROOT))

from backend.server.v2.store.search import (  # noqa: E402
    build_store_agent_search_query,
)


def test_fts_query_uses_parameterized_placeholders():
    query = build_store_agent_search_query(
        "demo", featured=True, creators=["ada"], category="ops"
    )
    assert query.params[0] == "demo"
    assert "creator_username = ANY($2)" in query.sql
    assert "$3 = ANY(categories)" in query.sql
    assert "featured = true" in query.sql
    assert query.params[-2] == 20


def test_fts_query_rejects_unknown_sort_keys_in_sql():
    query = build_store_agent_search_query("x", sorted_by="drop table")
    assert "updated_at DESC, rank DESC" in query.sql
    assert "drop table" not in query.sql
