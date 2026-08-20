"""Full-text search query builder for public store agents.

This module is intentionally free of ORM imports so it can be unit-tested
without a database or Prisma client.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

SortKey = Literal["rating", "runs", "name", "updated_at"]

ALLOWED_ORDER_BY: dict[str, str] = {
    "rating": "rating DESC, rank DESC",
    "runs": "runs DESC, rank DESC",
    "name": "agent_name ASC, rank ASC",
    "updated_at": "updated_at DESC, rank DESC",
}

STORE_AGENT_FTS_SELECT = """
                SELECT
                    slug,
                    agent_name,
                    agent_image,
                    creator_username,
                    creator_avatar,
                    sub_heading,
                    description,
                    runs,
                    rating,
                    categories,
                    featured,
                    is_available,
                    updated_at,
                    ts_rank_cd(search, query) AS rank
                FROM "StoreAgent",
                    plainto_tsquery('english', $1) AS query
                WHERE {sql_where_clause}
                    AND search @@ query
                ORDER BY {order_by_clause}
                LIMIT {limit_param} OFFSET {offset_param}
            """

STORE_AGENT_FTS_COUNT = """
                SELECT COUNT(*) as count
                FROM "StoreAgent",
                    plainto_tsquery('english', $1) AS query
                WHERE {sql_where_clause}
                    AND search @@ query
            """


@dataclass(frozen=True)
class StoreAgentSearchQuery:
    sql: str
    count_sql: str
    params: list[Any]
    count_params: list[Any]


def order_clause_for(sorted_by: SortKey | str | None) -> str:
    if sorted_by and sorted_by in ALLOWED_ORDER_BY:
        return ALLOWED_ORDER_BY[sorted_by]
    return ALLOWED_ORDER_BY["updated_at"]


def build_store_agent_search_query(
    search_query: str,
    *,
    featured: bool = False,
    creators: list[str] | None = None,
    sorted_by: SortKey | str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> StoreAgentSearchQuery:
    """Build parameterized FTS SQL for the StoreAgent view.

    Parameter $1 is always the raw search term. Additional filters and
    pagination bind as $2+.
    """
    offset = (page - 1) * page_size
    where_parts: list[str] = ["is_available = true"]
    params: list[Any] = [search_query]
    param_index = 2

    if featured:
        where_parts.append("featured = true")

    if creators:
        where_parts.append(f"creator_username = ANY(${param_index})")
        params.append(creators)
        param_index += 1

    if category:
        where_parts.append(f"${param_index} = ANY(categories)")
        params.append(category)
        param_index += 1

    sql_where_clause = " AND ".join(where_parts)
    params.extend([page_size, offset])
    limit_param = f"${param_index}"
    offset_param = f"${param_index + 1}"

    sql = STORE_AGENT_FTS_SELECT.format(
        sql_where_clause=sql_where_clause,
        order_by_clause=order_clause_for(sorted_by),
        limit_param=limit_param,
        offset_param=offset_param,
    )
    count_sql = STORE_AGENT_FTS_COUNT.format(sql_where_clause=sql_where_clause)
    return StoreAgentSearchQuery(
        sql=sql,
        count_sql=count_sql,
        params=params,
        count_params=params[:-2],
    )
