"""Graph database operations."""

import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal, Optional, cast

from prisma.enums import SubmissionStatus
from prisma.models import (
    AgentGraph,
    AgentNode,
    AgentNodeLink,
    LibraryAgent,
    StoreListingVersion,
)
from prisma.types import (
    AgentGraphCreateInput,
    AgentGraphWhereInput,
    AgentNodeCreateInput,
    AgentNodeLinkCreateInput,
)

from backend.blocks.agent import AgentExecutorBlock
from backend.blocks.io import AgentInputBlock, AgentOutputBlock
from backend.blocks.llm import LlmModel
from backend.data.db import prisma as db
from backend.data.includes import MAX_GRAPH_VERSIONS_FETCH
from backend.data.model import (
    CredentialsField,
    CredentialsFieldInfo,
    CredentialsMetaInput,
    is_credentials_field_name,
)
from backend.integrations.providers import ProviderName
from backend.util import type as type_utils
from backend.util.exceptions import GraphNotAccessibleError, GraphNotInLibraryError
from backend.util.json import SafeJson
from backend.util.models import Pagination

from .block import (
    Block,
    BlockInput,
    BlockSchema,
    BlockType,
    EmptySchema,
    get_block,
    get_blocks,
)
from .db import query_raw_with_schema, transaction
from .graph_models import (
    BaseGraph,
    Graph,
    GraphMeta,
    GraphModel,
    GraphTriggerInfo,
    GraphsPaginated,
    Link,
    Node,
    NodeModel,
)
from .includes import AGENT_GRAPH_INCLUDE, AGENT_NODE_INCLUDE

if TYPE_CHECKING:
    from .execution import NodesInputMasks
    from .integrations import Webhook

logger = logging.getLogger(__name__)

async def get_node(node_id: str) -> NodeModel:
    """⚠️ No `user_id` check: DO NOT USE without check in user-facing endpoints."""
    node = await AgentNode.prisma().find_unique_or_raise(
        where={"id": node_id},
        include=AGENT_NODE_INCLUDE,
    )
    return NodeModel.from_db(node)


async def set_node_webhook(node_id: str, webhook_id: str | None) -> NodeModel:
    """⚠️ No `user_id` check: DO NOT USE without check in user-facing endpoints."""
    node = await AgentNode.prisma().update(
        where={"id": node_id},
        data=(
            {"Webhook": {"connect": {"id": webhook_id}}}
            if webhook_id
            else {"Webhook": {"disconnect": True}}
        ),
        include=AGENT_NODE_INCLUDE,
    )
    if not node:
        raise ValueError(f"Node #{node_id} not found")
    return NodeModel.from_db(node)


async def list_graphs_paginated(
    user_id: str,
    page: int = 1,
    page_size: int = 25,
    filter_by: Literal["active"] | None = "active",
) -> GraphsPaginated:
    """
    Retrieves paginated graph metadata objects.

    Args:
        user_id: The ID of the user that owns the graphs.
        page: Page number (1-based).
        page_size: Number of graphs per page.
        filter_by: An optional filter to either select graphs.

    Returns:
        GraphsPaginated: Paginated list of graph metadata.
    """
    where_clause: AgentGraphWhereInput = {"userId": user_id}

    if filter_by == "active":
        where_clause["isActive"] = True

    # Get total count
    total_count = await AgentGraph.prisma().count(where=where_clause)
    total_pages = (total_count + page_size - 1) // page_size

    # Get paginated results
    offset = (page - 1) * page_size
    graphs = await AgentGraph.prisma().find_many(
        where=where_clause,
        distinct=["id"],
        order={"version": "desc"},
        include=AGENT_GRAPH_INCLUDE,
        skip=offset,
        take=page_size,
    )

    graph_models: list[GraphMeta] = []
    for graph in graphs:
        try:
            graph_meta = GraphModel.from_db(graph).meta()
            # Trigger serialization to validate that the graph is well formed
            graph_meta.model_dump()
            graph_models.append(graph_meta)
        except Exception as e:
            logger.error(f"Error processing graph {graph.id}: {e}")
            continue

    return GraphsPaginated(
        graphs=graph_models,
        pagination=Pagination(
            total_items=total_count,
            total_pages=total_pages,
            current_page=page,
            page_size=page_size,
        ),
    )


async def get_graph_metadata(graph_id: str, version: int | None = None) -> Graph | None:
    where_clause: AgentGraphWhereInput = {
        "id": graph_id,
    }

    if version is not None:
        where_clause["version"] = version

    graph = await AgentGraph.prisma().find_first(
        where=where_clause,
        order={"version": "desc"},
    )

    if not graph:
        return None

    return Graph(
        id=graph.id,
        name=graph.name or "",
        description=graph.description or "",
        version=graph.version,
        is_active=graph.isActive,
    )


async def get_graph(
    graph_id: str,
    version: int | None = None,
    *,
    user_id: str | None = None,
    for_export: bool = False,
    include_subgraphs: bool = False,
    skip_access_check: bool = False,
) -> GraphModel | None:
    """
    Retrieves a graph from the DB.
    Defaults to the version with `is_active` if `version` is not passed.

    Returns `None` if the record is not found.
    """
    where_clause: AgentGraphWhereInput = {
        "id": graph_id,
    }

    if version is not None:
        where_clause["version"] = version

    graph = await AgentGraph.prisma().find_first(
        where=where_clause,
        include=AGENT_GRAPH_INCLUDE,
        order={"version": "desc"},
    )
    if graph is None:
        return None

    if not skip_access_check and graph.userId != user_id:
        # For access, the graph must be owned by the user or listed in the store
        if not await is_graph_published_in_marketplace(graph_id, graph.version):
            return None

    if include_subgraphs or for_export:
        sub_graphs = await get_sub_graphs(graph)
        return GraphModel.from_db(
            graph=graph,
            sub_graphs=sub_graphs,
            for_export=for_export,
        )

    return GraphModel.from_db(graph, for_export)


async def get_graph_as_admin(
    graph_id: str,
    version: int | None = None,
    user_id: str | None = None,
    for_export: bool = False,
) -> GraphModel | None:
    """
    Intentionally parallels the get_graph but should only be used for admin tasks, because can return any graph that's been submitted
    Retrieves a graph from the DB.
    Defaults to the version with `is_active` if `version` is not passed.

    Returns `None` if the record is not found.
    """
    logger.warning(f"Getting {graph_id=} {version=} as ADMIN {user_id=} {for_export=}")
    where_clause: AgentGraphWhereInput = {
        "id": graph_id,
    }

    if version is not None:
        where_clause["version"] = version

    graph = await AgentGraph.prisma().find_first(
        where=where_clause,
        include=AGENT_GRAPH_INCLUDE,
        order={"version": "desc"},
    )

    # For access, the graph must be owned by the user or listed in the store
    if graph is None or (
        graph.userId != user_id
        and not await is_graph_published_in_marketplace(
            graph_id, version or graph.version
        )
    ):
        return None

    if for_export:
        sub_graphs = await get_sub_graphs(graph)
        return GraphModel.from_db(
            graph=graph,
            sub_graphs=sub_graphs,
            for_export=for_export,
        )

    return GraphModel.from_db(graph, for_export)


async def get_sub_graphs(graph: AgentGraph) -> list[AgentGraph]:
    """
    Iteratively fetches all sub-graphs of a given graph, and flattens them into a list.
    This call involves a DB fetch in batch, breadth-first, per-level of graph depth.
    On each DB fetch we will only fetch the sub-graphs that are not already in the list.
    """
    sub_graphs = {graph.id: graph}
    search_graphs = [graph]
    agent_block_id = AgentExecutorBlock().id

    while search_graphs:
        sub_graph_ids = [
            (graph_id, graph_version)
            for graph in search_graphs
            for node in graph.Nodes or []
            if (
                node.AgentBlock
                and node.AgentBlock.id == agent_block_id
                and (graph_id := cast(str, dict(node.constantInput).get("graph_id")))
                and (
                    graph_version := cast(
                        int, dict(node.constantInput).get("graph_version")
                    )
                )
            )
        ]
        if not sub_graph_ids:
            break

        graphs = await AgentGraph.prisma().find_many(
            where={
                "OR": [
                    {
                        "id": graph_id,
                        "version": graph_version,
                        "userId": graph.userId,  # Ensure the sub-graph is owned by the same user
                    }
                    for graph_id, graph_version in sub_graph_ids
                ]
            },
            include=AGENT_GRAPH_INCLUDE,
        )

        search_graphs = [graph for graph in graphs if graph.id not in sub_graphs]
        sub_graphs.update({graph.id: graph for graph in search_graphs})

    return [g for g in sub_graphs.values() if g.id != graph.id]


async def get_connected_output_nodes(node_id: str) -> list[tuple[Link, Node]]:
    links = await AgentNodeLink.prisma().find_many(
        where={"agentNodeSourceId": node_id},
        include={"AgentNodeSink": {"include": AGENT_NODE_INCLUDE}},
    )
    return [
        (Link.from_db(link), NodeModel.from_db(link.AgentNodeSink))
        for link in links
        if link.AgentNodeSink
    ]


async def set_graph_active_version(graph_id: str, version: int, user_id: str) -> None:
    # Activate the requested version if it exists and is owned by the user.
    updated_count = await AgentGraph.prisma().update_many(
        data={"isActive": True},
        where={
            "id": graph_id,
            "version": version,
            "userId": user_id,
        },
    )
    if updated_count == 0:
        raise Exception(f"Graph #{graph_id} v{version} not found or not owned by user")

    # Deactivate all other versions.
    await AgentGraph.prisma().update_many(
        data={"isActive": False},
        where={
            "id": graph_id,
            "version": {"not": version},
            "userId": user_id,
            "isActive": True,
        },
    )


async def get_graph_all_versions(
    graph_id: str, user_id: str, limit: int = MAX_GRAPH_VERSIONS_FETCH
) -> list[GraphModel]:
    graph_versions = await AgentGraph.prisma().find_many(
        where={"id": graph_id, "userId": user_id},
        order={"version": "desc"},
        include=AGENT_GRAPH_INCLUDE,
        take=limit,
    )

    if not graph_versions:
        return []

    return [GraphModel.from_db(graph) for graph in graph_versions]


async def delete_graph(graph_id: str, user_id: str) -> int:
    entries_count = await AgentGraph.prisma().delete_many(
        where={"id": graph_id, "userId": user_id}
    )
    if entries_count:
        logger.info(f"Deleted {entries_count} graph entries for Graph #{graph_id}")
    return entries_count


async def validate_graph_execution_permissions(
    user_id: str, graph_id: str, graph_version: int, is_sub_graph: bool = False
) -> None:
    """
    Validate that a user has permission to execute a specific graph.

    This function performs comprehensive authorization checks and raises specific
    exceptions for different types of failures to enable appropriate error handling.

    ## Logic
    A user can execute a graph if any of these is true:
    1. They own the graph and some version of it is still listed in their library
    2. The graph is published in the marketplace and listed in their library
    3. The graph is published in the marketplace and is being executed as a sub-agent

    Args:
        graph_id: The ID of the graph to check
        user_id: The ID of the user
        graph_version: The version of the graph to check
        is_sub_graph: Whether this is being executed as a sub-graph.
            If `True`, the graph isn't required to be in the user's Library.

    Raises:
        GraphNotAccessibleError: If the graph is not accessible to the user.
        GraphNotInLibraryError: If the graph is not in the user's library (deleted/archived).
        NotAuthorizedError: If the user lacks execution permissions for other reasons
    """
    graph, library_agent = await asyncio.gather(
        AgentGraph.prisma().find_unique(
            where={"graphVersionId": {"id": graph_id, "version": graph_version}}
        ),
        LibraryAgent.prisma().find_first(
            where={
                "userId": user_id,
                "agentGraphId": graph_id,
                "isDeleted": False,
                "isArchived": False,
            }
        ),
    )

    # Step 1: Check if user owns this graph
    user_owns_graph = graph and graph.userId == user_id

    # Step 2: Check if agent is in the library *and not deleted*
    user_has_in_library = library_agent is not None

    # Step 3: Apply permission logic
    if not (
        user_owns_graph
        or await is_graph_published_in_marketplace(graph_id, graph_version)
    ):
        raise GraphNotAccessibleError(
            f"You do not have access to graph #{graph_id} v{graph_version}: "
            "it is not owned by you and not available in the Marketplace"
        )
    elif not (user_has_in_library or is_sub_graph):
        raise GraphNotInLibraryError(f"Graph #{graph_id} is not in your library")

    # Step 6: Check execution-specific permissions (raises generic NotAuthorizedError)
    # Additional authorization checks beyond the above:
    # 1. Check if user has execution credits (future)
    # 2. Check if graph is suspended/disabled (future)
    # 3. Check rate limiting rules (future)
    # 4. Check organization-level permissions (future)

    # For now, the above check logic is sufficient for execution permission.
    # Future enhancements can add more granular permission checks here.
    # When adding new checks, raise NotAuthorizedError for non-library issues.


async def is_graph_published_in_marketplace(graph_id: str, graph_version: int) -> bool:
    """
    Check if a graph is published in the marketplace.

    Params:
        graph_id: The ID of the graph to check
        graph_version: The version of the graph to check

    Returns:
        True if the graph is published and approved in the marketplace, False otherwise
    """
    marketplace_listing = await StoreListingVersion.prisma().find_first(
        where={
            "agentGraphId": graph_id,
            "agentGraphVersion": graph_version,
            "submissionStatus": SubmissionStatus.APPROVED,
            "isDeleted": False,
        }
    )
    return marketplace_listing is not None


async def create_graph(graph: Graph, user_id: str) -> GraphModel:
    async with transaction() as tx:
        await __create_graph(tx, graph, user_id)

    if created_graph := await get_graph(graph.id, graph.version, user_id=user_id):
        return created_graph

    raise ValueError(f"Created graph {graph.id} v{graph.version} is not in DB")


async def fork_graph(graph_id: str, graph_version: int, user_id: str) -> GraphModel:
    """
    Forks a graph by copying it and all its nodes and links to a new graph.
    """
    graph = await get_graph(graph_id, graph_version, user_id=user_id, for_export=True)
    if not graph:
        raise ValueError(f"Graph {graph_id} v{graph_version} not found")

    # Set forked from ID and version as itself as it's about ot be copied
    graph.forked_from_id = graph.id
    graph.forked_from_version = graph.version
    graph.name = f"{graph.name} (copy)"
    graph.reassign_ids(user_id=user_id, reassign_graph_id=True)
    graph.validate_graph(for_run=False)

    async with transaction() as tx:
        await __create_graph(tx, graph, user_id)

    return graph


async def __create_graph(tx, graph: Graph, user_id: str):
    graphs = [graph] + graph.sub_graphs

    await AgentGraph.prisma(tx).create_many(
        data=[
            AgentGraphCreateInput(
                id=graph.id,
                version=graph.version,
                name=graph.name,
                description=graph.description,
                recommendedScheduleCron=graph.recommended_schedule_cron,
                isActive=graph.is_active,
                userId=user_id,
                forkedFromId=graph.forked_from_id,
                forkedFromVersion=graph.forked_from_version,
            )
            for graph in graphs
        ]
    )

    await AgentNode.prisma(tx).create_many(
        data=[
            AgentNodeCreateInput(
                id=node.id,
                agentGraphId=graph.id,
                agentGraphVersion=graph.version,
                agentBlockId=node.block_id,
                constantInput=SafeJson(node.input_default),
                metadata=SafeJson(node.metadata),
            )
            for graph in graphs
            for node in graph.nodes
        ]
    )

    await AgentNodeLink.prisma(tx).create_many(
        data=[
            AgentNodeLinkCreateInput(
                id=str(uuid.uuid4()),
                sourceName=link.source_name,
                sinkName=link.sink_name,
                agentNodeSourceId=link.source_id,
                agentNodeSinkId=link.sink_id,
                isStatic=link.is_static,
            )
            for graph in graphs
            for link in graph.links
        ]
    )


# ------------------------ UTILITIES ------------------------ #


def make_graph_model(creatable_graph: Graph, user_id: str) -> GraphModel:
    """
    Convert a Graph to a GraphModel, setting graph_id and graph_version on all nodes.

    Args:
        creatable_graph (Graph): The creatable graph to convert.
        user_id (str): The ID of the user creating the graph.

    Returns:
        GraphModel: The converted Graph object.
    """
    # Create a new Graph object, inheriting properties from CreatableGraph
    return GraphModel(
        **creatable_graph.model_dump(exclude={"nodes"}),
        user_id=user_id,
        created_at=datetime.now(tz=timezone.utc),
        nodes=[
            NodeModel(
                **creatable_node.model_dump(),
                graph_id=creatable_graph.id,
                graph_version=creatable_graph.version,
            )
            for creatable_node in creatable_graph.nodes
        ],
    )


async def fix_llm_provider_credentials():
    """Fix node credentials with provider `llm`"""
    from backend.integrations.credentials_store import IntegrationCredentialsStore

    from .user import get_user_integrations

    store = IntegrationCredentialsStore()

    broken_nodes = []
    try:
        broken_nodes = await query_raw_with_schema(
            """
            SELECT    graph."userId"       user_id,
                  node.id              node_id,
                  node."constantInput" node_preset_input
            FROM      {schema_prefix}"AgentNode"  node
            LEFT JOIN {schema_prefix}"AgentGraph" graph
            ON        node."agentGraphId" = graph.id
            WHERE     node."constantInput"::jsonb->'credentials'->>'provider' = 'llm'
            ORDER BY  graph."userId";
            """
        )
        logger.info(f"Fixing LLM credential inputs on {len(broken_nodes)} nodes")
    except Exception as e:
        logger.error(f"Error fixing LLM credential inputs: {e}")

    user_id: str = ""
    user_integrations = None
    for node in broken_nodes:
        if node["user_id"] != user_id:
            # Save queries by only fetching once per user
            user_id = node["user_id"]
            user_integrations = await get_user_integrations(user_id)
        elif not user_integrations:
            raise RuntimeError(f"Impossible state while processing node {node}")

        node_id: str = node["node_id"]
        node_preset_input: dict = node["node_preset_input"]
        credentials_meta: dict = node_preset_input["credentials"]

        credentials = next(
            (
                c
                for c in user_integrations.credentials
                if c.id == credentials_meta["id"]
            ),
            None,
        )
        if not credentials:
            continue
        if credentials.type != "api_key":
            logger.warning(
                f"User {user_id} credentials {credentials.id} with provider 'llm' "
                f"has invalid type '{credentials.type}'"
            )
            continue

        api_key = credentials.api_key.get_secret_value()
        if api_key.startswith("sk-ant-api03-"):
            credentials.provider = credentials_meta["provider"] = "anthropic"
        elif api_key.startswith("sk-"):
            credentials.provider = credentials_meta["provider"] = "openai"
        elif api_key.startswith("gsk_"):
            credentials.provider = credentials_meta["provider"] = "groq"
        else:
            logger.warning(
                f"Could not identify provider from key prefix {api_key[:13]}*****"
            )
            continue

        await store.update_creds(user_id, credentials)
        await AgentNode.prisma().update(
            where={"id": node_id},
            data={"constantInput": SafeJson(node_preset_input)},
        )


async def migrate_llm_models(migrate_to: LlmModel):
    """
    Update all LLM models in all AI blocks that don't exist in the enum.
    Note: Only updates top level LlmModel SchemaFields of blocks (won't update nested fields).
    """
    logger.info("Migrating LLM models")
    # Scan all blocks and search for LlmModel fields
    llm_model_fields: dict[str, str] = {}  # {block_id: field_name}

    # Search for all LlmModel fields
    for block_type in get_blocks().values():
        block = block_type()
        from pydantic.fields import FieldInfo

        fields: dict[str, FieldInfo] = block.input_schema.model_fields

        # Collect top-level LlmModel fields
        for field_name, field in fields.items():
            if field.annotation == LlmModel:
                llm_model_fields[block.id] = field_name

    # Convert enum values to a list of strings for the SQL query
    enum_values = [v.value for v in LlmModel]
    escaped_enum_values = repr(tuple(enum_values))  # hack but works

    # Update each block
    for id, path in llm_model_fields.items():
        query = f"""
            UPDATE platform."AgentNode"
            SET "constantInput" = jsonb_set("constantInput", $1, to_jsonb($2), true)
            WHERE "agentBlockId" = $3
            AND "constantInput" ? ($4)::text
            AND "constantInput"->>($4)::text NOT IN {escaped_enum_values}
            """

        await db.execute_raw(
            query,  # type: ignore - is supposed to be LiteralString
            [path],
            migrate_to.value,
            id,
            path,
        )
