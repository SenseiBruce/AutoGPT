"""Execution database query and mutation helpers."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import (
    Any,
    Literal,
    Mapping,
    Optional,
    cast,
    overload,
)

from prisma import Json
from prisma.enums import AgentExecutionStatus
from prisma.models import (
    AgentGraphExecution,
    AgentNodeExecution,
    AgentNodeExecutionInputOutput,
    AgentNodeExecutionKeyValueData,
)
from prisma.types import (
    AgentGraphExecutionUpdateManyMutationInput,
    AgentGraphExecutionWhereInput,
    AgentNodeExecutionCreateInput,
    AgentNodeExecutionInputOutputCreateInput,
    AgentNodeExecutionKeyValueDataCreateInput,
    AgentNodeExecutionUpdateInput,
    AgentNodeExecutionWhereInput,
)
from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError
from pydantic.fields import Field

from backend.util import type as type_utils
from backend.util.exceptions import DatabaseError
from backend.util.json import SafeJson
from backend.util.models import Pagination
from backend.util.retry import func_retry
from backend.util.settings import Config
from backend.util.truncate import truncate

from .block import (
    BlockInput,
    BlockType,
    CompletedBlockOutput,
    get_block,
    get_io_block_ids,
    get_webhook_block_ids,
)
from .db import BaseDbModel, query_raw_with_schema
from .execution_models import (
    BlockErrorStats,
    ExecutionStatus,
    GraphExecution,
    GraphExecutionMeta,
    GraphExecutionWithNodes,
    NodesInputMasks,
    NodeExecutionResult,
)
from .includes import (
    EXECUTION_RESULT_INCLUDE,
    EXECUTION_RESULT_ORDER,
    GRAPH_EXECUTION_INCLUDE_WITH_NODES,
    graph_execution_include,
)
from .model import CredentialsMetaInput, GraphExecutionStats, NodeExecutionStats

logger = logging.getLogger(__name__)
config = Config()

async def get_graph_executions(
    graph_exec_id: Optional[str] = None,
    graph_id: Optional[str] = None,
    user_id: Optional[str] = None,
    statuses: Optional[list[ExecutionStatus]] = None,
    created_time_gte: Optional[datetime] = None,
    created_time_lte: Optional[datetime] = None,
    limit: Optional[int] = None,
) -> list[GraphExecutionMeta]:
    """⚠️ **Optional `user_id` check**: MUST USE check in user-facing endpoints."""
    where_filter: AgentGraphExecutionWhereInput = {
        "isDeleted": False,
    }
    if graph_exec_id:
        where_filter["id"] = graph_exec_id
    if user_id:
        where_filter["userId"] = user_id
    if graph_id:
        where_filter["agentGraphId"] = graph_id
    if created_time_gte or created_time_lte:
        where_filter["createdAt"] = {
            "gte": created_time_gte or datetime.min.replace(tzinfo=timezone.utc),
            "lte": created_time_lte or datetime.max.replace(tzinfo=timezone.utc),
        }
    if statuses:
        where_filter["OR"] = [{"executionStatus": status} for status in statuses]

    executions = await AgentGraphExecution.prisma().find_many(
        where=where_filter,
        order={"createdAt": "desc"},
        take=limit,
    )
    return [GraphExecutionMeta.from_db(execution) for execution in executions]


async def get_graph_executions_count(
    user_id: Optional[str] = None,
    graph_id: Optional[str] = None,
    statuses: Optional[list[ExecutionStatus]] = None,
    created_time_gte: Optional[datetime] = None,
    created_time_lte: Optional[datetime] = None,
) -> int:
    """
    Get count of graph executions with optional filters.

    Args:
        user_id: Optional user ID to filter by
        graph_id: Optional graph ID to filter by
        statuses: Optional list of execution statuses to filter by
        created_time_gte: Optional minimum creation time
        created_time_lte: Optional maximum creation time

    Returns:
        Count of matching graph executions
    """
    where_filter: AgentGraphExecutionWhereInput = {
        "isDeleted": False,
    }

    if user_id:
        where_filter["userId"] = user_id

    if graph_id:
        where_filter["agentGraphId"] = graph_id

    if created_time_gte or created_time_lte:
        where_filter["createdAt"] = {
            "gte": created_time_gte or datetime.min.replace(tzinfo=timezone.utc),
            "lte": created_time_lte or datetime.max.replace(tzinfo=timezone.utc),
        }
    if statuses:
        where_filter["OR"] = [{"executionStatus": status} for status in statuses]

    count = await AgentGraphExecution.prisma().count(where=where_filter)
    return count


class GraphExecutionsPaginated(BaseModel):
    """Response schema for paginated graph executions."""

    executions: list[GraphExecutionMeta]
    pagination: Pagination


async def get_graph_executions_paginated(
    user_id: str,
    graph_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
    statuses: Optional[list[ExecutionStatus]] = None,
    created_time_gte: Optional[datetime] = None,
    created_time_lte: Optional[datetime] = None,
) -> GraphExecutionsPaginated:
    """Get paginated graph executions for a specific graph."""
    where_filter: AgentGraphExecutionWhereInput = {
        "isDeleted": False,
        "userId": user_id,
    }

    if graph_id:
        where_filter["agentGraphId"] = graph_id
    if created_time_gte or created_time_lte:
        where_filter["createdAt"] = {
            "gte": created_time_gte or datetime.min.replace(tzinfo=timezone.utc),
            "lte": created_time_lte or datetime.max.replace(tzinfo=timezone.utc),
        }
    if statuses:
        where_filter["OR"] = [{"executionStatus": status} for status in statuses]

    total_count = await AgentGraphExecution.prisma().count(where=where_filter)
    total_pages = (total_count + page_size - 1) // page_size

    offset = (page - 1) * page_size
    executions = await AgentGraphExecution.prisma().find_many(
        where=where_filter,
        order={"createdAt": "desc"},
        take=page_size,
        skip=offset,
    )

    return GraphExecutionsPaginated(
        executions=[GraphExecutionMeta.from_db(execution) for execution in executions],
        pagination=Pagination(
            total_items=total_count,
            total_pages=total_pages,
            current_page=page,
            page_size=page_size,
        ),
    )


async def get_graph_execution_meta(
    user_id: str, execution_id: str
) -> GraphExecutionMeta | None:
    execution = await AgentGraphExecution.prisma().find_first(
        where={"id": execution_id, "isDeleted": False, "userId": user_id}
    )
    return GraphExecutionMeta.from_db(execution) if execution else None


@overload
async def get_graph_execution(
    user_id: str,
    execution_id: str,
    include_node_executions: Literal[True],
) -> GraphExecutionWithNodes | None: ...


@overload
async def get_graph_execution(
    user_id: str,
    execution_id: str,
    include_node_executions: Literal[False] = False,
) -> GraphExecution | None: ...


@overload
async def get_graph_execution(
    user_id: str,
    execution_id: str,
    include_node_executions: bool = False,
) -> GraphExecution | GraphExecutionWithNodes | None: ...


async def get_graph_execution(
    user_id: str,
    execution_id: str,
    include_node_executions: bool = False,
) -> GraphExecution | GraphExecutionWithNodes | None:
    execution = await AgentGraphExecution.prisma().find_first(
        where={"id": execution_id, "isDeleted": False, "userId": user_id},
        include=(
            GRAPH_EXECUTION_INCLUDE_WITH_NODES
            if include_node_executions
            else graph_execution_include(
                [*get_io_block_ids(), *get_webhook_block_ids()]
            )
        ),
    )
    if not execution:
        return None

    return (
        GraphExecutionWithNodes.from_db(execution)
        if include_node_executions
        else GraphExecution.from_db(execution)
    )


async def get_child_graph_executions(
    parent_exec_id: str,
) -> list[GraphExecutionMeta]:
    """
    Get all child executions of a parent execution.

    Args:
        parent_exec_id: Parent graph execution ID

    Returns:
        List of child graph executions
    """
    children = await AgentGraphExecution.prisma().find_many(
        where={"parentGraphExecutionId": parent_exec_id, "isDeleted": False}
    )

    return [GraphExecutionMeta.from_db(child) for child in children]


async def create_graph_execution(
    graph_id: str,
    graph_version: int,
    starting_nodes_input: list[tuple[str, BlockInput]],  # list[(node_id, BlockInput)]
    inputs: Mapping[str, JsonValue],
    user_id: str,
    preset_id: Optional[str] = None,
    credential_inputs: Optional[Mapping[str, CredentialsMetaInput]] = None,
    nodes_input_masks: Optional[NodesInputMasks] = None,
    parent_graph_exec_id: Optional[str] = None,
) -> GraphExecutionWithNodes:
    """
    Create a new AgentGraphExecution record.
    Returns:
        The id of the AgentGraphExecution and the list of ExecutionResult for each node.
    """
    result = await AgentGraphExecution.prisma().create(
        data={
            "agentGraphId": graph_id,
            "agentGraphVersion": graph_version,
            "executionStatus": ExecutionStatus.INCOMPLETE,
            "inputs": SafeJson(inputs),
            "credentialInputs": (
                SafeJson(credential_inputs) if credential_inputs else Json({})
            ),
            "nodesInputMasks": (
                SafeJson(nodes_input_masks) if nodes_input_masks else Json({})
            ),
            "NodeExecutions": {
                "create": [
                    AgentNodeExecutionCreateInput(
                        agentNodeId=node_id,
                        executionStatus=ExecutionStatus.QUEUED,
                        queuedTime=datetime.now(tz=timezone.utc),
                        Input={
                            "create": [
                                {"name": name, "data": SafeJson(data)}
                                for name, data in node_input.items()
                            ]
                        },
                    )
                    for node_id, node_input in starting_nodes_input
                ]
            },
            "userId": user_id,
            "agentPresetId": preset_id,
            "parentGraphExecutionId": parent_graph_exec_id,
        },
        include=GRAPH_EXECUTION_INCLUDE_WITH_NODES,
    )

    return GraphExecutionWithNodes.from_db(result)


async def upsert_execution_input(
    node_id: str,
    graph_exec_id: str,
    input_name: str,
    input_data: JsonValue,
    node_exec_id: str | None = None,
) -> tuple[str, BlockInput]:
    """
    Insert AgentNodeExecutionInputOutput record for as one of AgentNodeExecution.Input.
    If there is no AgentNodeExecution that has no `input_name` as input, create new one.

    Args:
        node_id: The id of the AgentNode.
        graph_exec_id: The id of the AgentGraphExecution.
        input_name: The name of the input data.
        input_data: The input data to be inserted.
        node_exec_id: [Optional] The id of the AgentNodeExecution that has no `input_name` as input. If not provided, it will find the eligible incomplete AgentNodeExecution or create a new one.

    Returns:
        str: The id of the created or existing AgentNodeExecution.
        dict[str, Any]: Node input data; key is the input name, value is the input data.
    """
    existing_exec_query_filter: AgentNodeExecutionWhereInput = {
        "agentGraphExecutionId": graph_exec_id,
        "agentNodeId": node_id,
        "executionStatus": ExecutionStatus.INCOMPLETE,
        "Input": {
            "none": {
                "name": input_name,
                "time": {"gte": datetime.now(tz=timezone.utc) - timedelta(days=1)},
            }
        },
    }
    if node_exec_id:
        existing_exec_query_filter["id"] = node_exec_id

    existing_execution = await AgentNodeExecution.prisma().find_first(
        where=existing_exec_query_filter,
        order={"addedTime": "asc"},
        include={"Input": True},
    )
    json_input_data = SafeJson(input_data)

    if existing_execution:
        await AgentNodeExecutionInputOutput.prisma().create(
            data=AgentNodeExecutionInputOutputCreateInput(
                name=input_name,
                data=json_input_data,
                referencedByInputExecId=existing_execution.id,
            )
        )
        return existing_execution.id, {
            **{
                input_data.name: type_utils.convert(input_data.data, JsonValue)
                for input_data in existing_execution.Input or []
            },
            input_name: input_data,
        }

    elif not node_exec_id:
        result = await AgentNodeExecution.prisma().create(
            data=AgentNodeExecutionCreateInput(
                agentNodeId=node_id,
                agentGraphExecutionId=graph_exec_id,
                executionStatus=ExecutionStatus.INCOMPLETE,
                Input={"create": {"name": input_name, "data": json_input_data}},
            )
        )
        return result.id, {input_name: input_data}

    else:
        raise ValueError(
            f"NodeExecution {node_exec_id} not found or already has input {input_name}."
        )


async def upsert_execution_output(
    node_exec_id: str,
    output_name: str,
    output_data: Any | None,
) -> None:
    """
    Insert AgentNodeExecutionInputOutput record for as one of AgentNodeExecution.Output.
    """
    data: AgentNodeExecutionInputOutputCreateInput = {
        "name": output_name,
        "referencedByOutputExecId": node_exec_id,
    }
    if output_data is not None:
        data["data"] = SafeJson(output_data)
    await AgentNodeExecutionInputOutput.prisma().create(data=data)


async def update_graph_execution_start_time(
    graph_exec_id: str,
) -> GraphExecution | None:
    res = await AgentGraphExecution.prisma().update(
        where={"id": graph_exec_id},
        data={
            "executionStatus": ExecutionStatus.RUNNING,
            "startedAt": datetime.now(tz=timezone.utc),
        },
        include=graph_execution_include(
            [*get_io_block_ids(), *get_webhook_block_ids()]
        ),
    )
    return GraphExecution.from_db(res) if res else None


async def update_graph_execution_stats(
    graph_exec_id: str,
    status: ExecutionStatus | None = None,
    stats: GraphExecutionStats | None = None,
) -> GraphExecution | None:
    if not status and not stats:
        raise ValueError(
            f"Must provide either status or stats to update for execution {graph_exec_id}"
        )

    update_data: AgentGraphExecutionUpdateManyMutationInput = {}

    if stats:
        stats_dict = stats.model_dump()
        if isinstance(stats_dict.get("error"), Exception):
            stats_dict["error"] = str(stats_dict["error"])
        update_data["stats"] = SafeJson(stats_dict)

    if status:
        update_data["executionStatus"] = status

    where_clause: AgentGraphExecutionWhereInput = {"id": graph_exec_id}

    if status:
        if allowed_from := VALID_STATUS_TRANSITIONS.get(status, []):
            # Add OR clause to check if current status is one of the allowed source statuses
            where_clause["AND"] = [
                {"id": graph_exec_id},
                {"OR": [{"executionStatus": s} for s in allowed_from]},
            ]
        else:
            raise ValueError(
                f"Status {status} cannot be set via update for execution {graph_exec_id}. "
                f"This status can only be set at creation or is not a valid target status."
            )

    await AgentGraphExecution.prisma().update_many(
        where=where_clause,
        data=update_data,
    )

    graph_exec = await AgentGraphExecution.prisma().find_unique_or_raise(
        where={"id": graph_exec_id},
        include=graph_execution_include(
            [*get_io_block_ids(), *get_webhook_block_ids()]
        ),
    )

    return GraphExecution.from_db(graph_exec)


async def update_node_execution_status_batch(
    node_exec_ids: list[str],
    status: ExecutionStatus,
    stats: dict[str, Any] | None = None,
):
    await AgentNodeExecution.prisma().update_many(
        where={"id": {"in": node_exec_ids}},
        data=_get_update_status_data(status, None, stats),
    )


async def update_node_execution_status(
    node_exec_id: str,
    status: ExecutionStatus,
    execution_data: BlockInput | None = None,
    stats: dict[str, Any] | None = None,
) -> NodeExecutionResult:
    if status == ExecutionStatus.QUEUED and execution_data is None:
        raise ValueError("Execution data must be provided when queuing an execution.")

    res = await AgentNodeExecution.prisma().update(
        where={"id": node_exec_id},
        data=_get_update_status_data(status, execution_data, stats),
        include=EXECUTION_RESULT_INCLUDE,
    )
    if not res:
        raise ValueError(f"Execution {node_exec_id} not found.")

    return NodeExecutionResult.from_db(res)


def _get_update_status_data(
    status: ExecutionStatus,
    execution_data: BlockInput | None = None,
    stats: dict[str, Any] | None = None,
) -> AgentNodeExecutionUpdateInput:
    now = datetime.now(tz=timezone.utc)
    update_data: AgentNodeExecutionUpdateInput = {"executionStatus": status}

    if status == ExecutionStatus.QUEUED:
        update_data["queuedTime"] = now
    elif status == ExecutionStatus.RUNNING:
        update_data["startedTime"] = now
    elif status in (ExecutionStatus.FAILED, ExecutionStatus.COMPLETED):
        update_data["endedTime"] = now

    if execution_data:
        update_data["executionData"] = SafeJson(execution_data)
    if stats:
        update_data["stats"] = SafeJson(stats)

    return update_data


async def delete_graph_execution(
    graph_exec_id: str, user_id: str, soft_delete: bool = True
) -> None:
    if soft_delete:
        deleted_count = await AgentGraphExecution.prisma().update_many(
            where={"id": graph_exec_id, "userId": user_id}, data={"isDeleted": True}
        )
    else:
        deleted_count = await AgentGraphExecution.prisma().delete_many(
            where={"id": graph_exec_id, "userId": user_id}
        )
    if deleted_count < 1:
        raise DatabaseError(
            f"Could not delete graph execution #{graph_exec_id}: not found"
        )


async def get_node_execution(node_exec_id: str) -> NodeExecutionResult | None:
    """⚠️ No `user_id` check: DO NOT USE without check in user-facing endpoints."""
    execution = await AgentNodeExecution.prisma().find_first(
        where={"id": node_exec_id},
        include=EXECUTION_RESULT_INCLUDE,
    )
    if not execution:
        return None
    return NodeExecutionResult.from_db(execution)


async def get_node_executions(
    graph_exec_id: str | None = None,
    node_id: str | None = None,
    block_ids: list[str] | None = None,
    statuses: list[ExecutionStatus] | None = None,
    limit: int | None = None,
    created_time_gte: datetime | None = None,
    created_time_lte: datetime | None = None,
    include_exec_data: bool = True,
) -> list[NodeExecutionResult]:
    """⚠️ No `user_id` check: DO NOT USE without check in user-facing endpoints."""
    where_clause: AgentNodeExecutionWhereInput = {}
    if graph_exec_id:
        where_clause["agentGraphExecutionId"] = graph_exec_id
    if node_id:
        where_clause["agentNodeId"] = node_id
    if block_ids:
        where_clause["Node"] = {"is": {"agentBlockId": {"in": block_ids}}}
    if statuses:
        where_clause["OR"] = [{"executionStatus": status} for status in statuses]

    if created_time_gte or created_time_lte:
        where_clause["addedTime"] = {
            "gte": created_time_gte or datetime.min.replace(tzinfo=timezone.utc),
            "lte": created_time_lte or datetime.max.replace(tzinfo=timezone.utc),
        }

    executions = await AgentNodeExecution.prisma().find_many(
        where=where_clause,
        include=(
            EXECUTION_RESULT_INCLUDE
            if include_exec_data
            else {"Node": True, "GraphExecution": True}
        ),
        order=EXECUTION_RESULT_ORDER,
        take=limit,
    )
    res = [NodeExecutionResult.from_db(execution) for execution in executions]
    return res


async def get_latest_node_execution(
    node_id: str, graph_eid: str
) -> NodeExecutionResult | None:
    """⚠️ No `user_id` check: DO NOT USE without check in user-facing endpoints."""
    execution = await AgentNodeExecution.prisma().find_first(
        where={
            "agentGraphExecutionId": graph_eid,
            "agentNodeId": node_id,
            "OR": [
                {"executionStatus": ExecutionStatus.QUEUED},
                {"executionStatus": ExecutionStatus.RUNNING},
                {"executionStatus": ExecutionStatus.COMPLETED},
                {"executionStatus": ExecutionStatus.TERMINATED},
                {"executionStatus": ExecutionStatus.FAILED},
            ],
        },
        include=EXECUTION_RESULT_INCLUDE,
        order=EXECUTION_RESULT_ORDER,
    )
    if not execution:
        return None
    return NodeExecutionResult.from_db(execution)


# ----------------- Execution Infrastructure ----------------- #


