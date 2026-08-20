from backend.server.v2.store.search import (
    ALLOWED_ORDER_BY,
    build_store_agent_search_query,
    order_clause_for,
)


def test_order_clause_defaults_to_updated_at():
    assert order_clause_for(None) == ALLOWED_ORDER_BY["updated_at"]
    assert order_clause_for("not-a-column") == ALLOWED_ORDER_BY["updated_at"]


def test_order_clause_whitelist():
    assert order_clause_for("rating") == "rating DESC, rank DESC"
    assert order_clause_for("name") == "agent_name ASC, rank ASC"


def test_search_query_binds_search_term_as_first_param():
    query = build_store_agent_search_query("calendar agent")
    assert query.params[0] == "calendar agent"
    assert "$1" in query.sql
    assert "plainto_tsquery" in query.sql
    assert "search @@ query" in query.sql
    assert "is_available = true" in query.sql


def test_search_query_pagination_params():
    query = build_store_agent_search_query("bots", page=3, page_size=10)
    assert query.params[-2:] == [10, 20]
    assert query.count_params == ["bots"]
    assert "LIMIT $2 OFFSET $3" in query.sql


def test_search_query_optional_filters_are_parameterized():
    query = build_store_agent_search_query(
        "writer",
        featured=True,
        creators=["alice", "bob"],
        category="marketing",
        sorted_by="runs",
        page=1,
        page_size=5,
    )
    assert "featured = true" in query.sql
    assert "creator_username = ANY($2)" in query.sql
    assert "$3 = ANY(categories)" in query.sql
    assert "runs DESC, rank DESC" in query.sql
    assert query.params == ["writer", ["alice", "bob"], "marketing", 5, 0]
    assert query.count_params == ["writer", ["alice", "bob"], "marketing"]
    assert "$" not in "".join(str(p) for p in query.params)
