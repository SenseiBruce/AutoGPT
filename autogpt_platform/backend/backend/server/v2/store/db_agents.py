"""Store agent listing helpers (search and non-search paths)."""

from __future__ import annotations

import logging
import typing
from typing import Literal

import backend.server.v2.store.model
from backend.server.v2.store.search import build_store_agent_search_query

logger = logging.getLogger(__name__)


def store_agent_from_raw_row(agent: dict) -> backend.server.v2.store.model.StoreAgent:
    return backend.server.v2.store.model.StoreAgent(
        slug=agent["slug"],
        agent_name=agent["agent_name"],
        agent_image=agent["agent_image"][0] if agent["agent_image"] else "",
        creator=agent["creator_username"] or "Needs Profile",
        creator_avatar=agent["creator_avatar"] or "",
        sub_heading=agent["sub_heading"],
        description=agent["description"],
        runs=agent["runs"],
        rating=agent["rating"],
    )


def store_agent_from_prisma(agent) -> backend.server.v2.store.model.StoreAgent:
    return backend.server.v2.store.model.StoreAgent(
        slug=agent.slug,
        agent_name=agent.agent_name,
        agent_image=agent.agent_image[0] if agent.agent_image else "",
        creator=agent.creator_username or "Needs Profile",
        creator_avatar=agent.creator_avatar or "",
        sub_heading=agent.sub_heading,
        description=agent.description,
        runs=agent.runs,
        rating=agent.rating,
    )


async def fetch_store_agents_via_search(
    *,
    search_query: str,
    featured: bool = False,
    creators: list[str] | None = None,
    sorted_by: Literal["rating", "runs", "name", "updated_at"] | str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[backend.server.v2.store.model.StoreAgent], int, int]:
    import prisma

    fts = build_store_agent_search_query(
        search_query,
        featured=featured,
        creators=creators,
        sorted_by=sorted_by,
        category=category,
        page=page,
        page_size=page_size,
    )

    agents = await prisma.client.get_client().query_raw(
        typing.cast(typing.LiteralString, fts.sql), *fts.params
    )
    count_result = await prisma.client.get_client().query_raw(
        typing.cast(typing.LiteralString, fts.count_sql), *fts.count_params
    )

    total = count_result[0]["count"] if count_result else 0
    total_pages = (total + page_size - 1) // page_size

    store_agents: list[backend.server.v2.store.model.StoreAgent] = []
    for agent in agents:
        try:
            store_agents.append(store_agent_from_raw_row(agent))
        except Exception as e:
            logger.error(f"Error parsing Store agent from search results: {e}")
            continue
    return store_agents, total, total_pages


async def fetch_store_agents_via_prisma(
    *,
    featured: bool = False,
    creators: list[str] | None = None,
    sorted_by: Literal["rating", "runs", "name", "updated_at"] | str | None = None,
    category: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[backend.server.v2.store.model.StoreAgent], int, int]:
    import prisma.models
    import prisma.types

    where_clause: prisma.types.StoreAgentWhereInput = {"is_available": True}
    if featured:
        where_clause["featured"] = featured
    if creators:
        where_clause["creator_username"] = {"in": creators}
    if category:
        where_clause["categories"] = {"has": category}

    order_by = []
    if sorted_by == "rating":
        order_by.append({"rating": "desc"})
    elif sorted_by == "runs":
        order_by.append({"runs": "desc"})
    elif sorted_by == "name":
        order_by.append({"agent_name": "asc"})

    agents = await prisma.models.StoreAgent.prisma().find_many(
        where=where_clause,
        order=order_by,
        skip=(page - 1) * page_size,
        take=page_size,
    )

    total = await prisma.models.StoreAgent.prisma().count(where=where_clause)
    total_pages = (total + page_size - 1) // page_size

    store_agents: list[backend.server.v2.store.model.StoreAgent] = []
    for agent in agents:
        try:
            store_agents.append(store_agent_from_prisma(agent))
        except Exception as e:
            logger.error(
                f"Error parsing Store agent when getting store agents from db: {e}"
            )
            continue
    return store_agents, total, total_pages
