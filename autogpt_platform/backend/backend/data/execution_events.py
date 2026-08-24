"""Execution event bus and share helpers."""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from enum import Enum
from multiprocessing import Manager
from queue import Empty
from typing import (
    Annotated,
    Any,
    AsyncGenerator,
    Generator,
    Generic,
    Literal,
    Optional,
    TypeVar,
    cast,
)

from prisma import Json
from prisma.enums import AgentExecutionStatus
from prisma.models import AgentNodeExecutionKeyValueData
from prisma.types import AgentNodeExecutionKeyValueDataCreateInput
from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError
from pydantic.fields import Field

from backend.util import type as type_utils
from backend.util.exceptions import DatabaseError
from backend.util.json import SafeJson
from backend.util.retry import func_retry
from backend.util.settings import Config
from backend.util.truncate import truncate

from .block import BlockInput, BlockType, CompletedBlockOutput, get_block
from .db import BaseDbModel, query_raw_with_schema
from .event_bus import AsyncRedisEventBus, RedisEventBus
from .execution_models import (
    BlockErrorStats,
    ExecutionStatus,
    GraphExecution,
    GraphExecutionMeta,
    GraphExecutionWithNodes,
    NodesInputMasks,
    NodeExecutionResult,
)
from .includes import EXECUTION_RESULT_INCLUDE, graph_execution_include
from .model import GraphExecutionStats, NodeExecutionStats

T = TypeVar("T")

logger = logging.getLogger(__name__)
config = Config()

class UserContext(BaseModel):
    """Generic user context for graph execution containing user-specific settings."""

    timezone: str


class GraphExecutionEntry(BaseModel):
    user_id: str
    graph_exec_id: str
    graph_id: str
    graph_version: int
    nodes_input_masks: Optional[NodesInputMasks] = None
    user_context: UserContext
    parent_graph_exec_id: Optional[str] = None


class NodeExecutionEntry(BaseModel):
    user_id: str
    graph_exec_id: str
    graph_id: str
    node_exec_id: str
    node_id: str
    block_id: str
    inputs: BlockInput
    user_context: UserContext


class ExecutionQueue(Generic[T]):
    """
    Queue for managing the execution of agents.
    This will be shared between different processes
    """

    def __init__(self):
        self.queue = Manager().Queue()

    def add(self, execution: T) -> T:
        self.queue.put(execution)
        return execution

    def get(self) -> T:
        return self.queue.get()

    def empty(self) -> bool:
        return self.queue.empty()

    def get_or_none(self) -> T | None:
        try:
            return self.queue.get_nowait()
        except Empty:
            return None


# --------------------- Event Bus --------------------- #


class ExecutionEventType(str, Enum):
    GRAPH_EXEC_UPDATE = "graph_execution_update"
    NODE_EXEC_UPDATE = "node_execution_update"
    ERROR_COMMS_UPDATE = "error_comms_update"


class GraphExecutionEvent(GraphExecution):
    event_type: Literal[ExecutionEventType.GRAPH_EXEC_UPDATE] = (
        ExecutionEventType.GRAPH_EXEC_UPDATE
    )


class NodeExecutionEvent(NodeExecutionResult):
    event_type: Literal[ExecutionEventType.NODE_EXEC_UPDATE] = (
        ExecutionEventType.NODE_EXEC_UPDATE
    )


class SharedExecutionResponse(BaseModel):
    """Public-safe response for shared executions"""

    id: str
    graph_name: str
    graph_description: Optional[str]
    status: ExecutionStatus
    created_at: datetime
    outputs: CompletedBlockOutput  # Only the final outputs, no intermediate data
    # Deliberately exclude: user_id, inputs, credentials, node details


ExecutionEvent = Annotated[
    GraphExecutionEvent | NodeExecutionEvent, Field(discriminator="event_type")
]


class RedisExecutionEventBus(RedisEventBus[ExecutionEvent]):
    Model = ExecutionEvent  # type: ignore

    @property
    def event_bus_name(self) -> str:
        return config.execution_event_bus_name

    def publish(self, res: GraphExecution | NodeExecutionResult):
        if isinstance(res, GraphExecution):
            self._publish_graph_exec_update(res)
        else:
            self._publish_node_exec_update(res)

    def _publish_node_exec_update(self, res: NodeExecutionResult):
        event = NodeExecutionEvent.model_validate(res.model_dump())
        self._publish(event, f"{res.user_id}/{res.graph_id}/{res.graph_exec_id}")

    def _publish_graph_exec_update(self, res: GraphExecution):
        event = GraphExecutionEvent.model_validate(res.model_dump())
        self._publish(event, f"{res.user_id}/{res.graph_id}/{res.id}")

    def _publish(self, event: ExecutionEvent, channel: str):
        """
        truncate inputs and outputs to avoid large payloads
        """
        limit = config.max_message_size_limit // 2
        if isinstance(event, GraphExecutionEvent):
            event.inputs = truncate(event.inputs, limit)
            event.outputs = truncate(event.outputs, limit)
        elif isinstance(event, NodeExecutionEvent):
            event.input_data = truncate(event.input_data, limit)
            event.output_data = truncate(event.output_data, limit)

        super().publish_event(event, channel)

    def listen(
        self, user_id: str, graph_id: str = "*", graph_exec_id: str = "*"
    ) -> Generator[ExecutionEvent, None, None]:
        for event in self.listen_events(f"{user_id}/{graph_id}/{graph_exec_id}"):
            yield event


class AsyncRedisExecutionEventBus(AsyncRedisEventBus[ExecutionEvent]):
    Model = ExecutionEvent  # type: ignore

    @property
    def event_bus_name(self) -> str:
        return config.execution_event_bus_name

    @func_retry
    async def publish(self, res: GraphExecutionMeta | NodeExecutionResult):
        if isinstance(res, GraphExecutionMeta):
            await self._publish_graph_exec_update(res)
        else:
            await self._publish_node_exec_update(res)

    async def _publish_node_exec_update(self, res: NodeExecutionResult):
        event = NodeExecutionEvent.model_validate(res.model_dump())
        await self._publish(event, f"{res.user_id}/{res.graph_id}/{res.graph_exec_id}")

    async def _publish_graph_exec_update(self, res: GraphExecutionMeta):
        # GraphExecutionEvent requires inputs and outputs fields that GraphExecutionMeta doesn't have
        # Add default empty values for compatibility
        event_data = res.model_dump()
        event_data.setdefault("inputs", {})
        event_data.setdefault("outputs", {})
        event = GraphExecutionEvent.model_validate(event_data)
        await self._publish(event, f"{res.user_id}/{res.graph_id}/{res.id}")

    async def _publish(self, event: ExecutionEvent, channel: str):
        """
        truncate inputs and outputs to avoid large payloads
        """
        limit = config.max_message_size_limit // 2
        if isinstance(event, GraphExecutionEvent):
            event.inputs = truncate(event.inputs, limit)
            event.outputs = truncate(event.outputs, limit)
        elif isinstance(event, NodeExecutionEvent):
            event.input_data = truncate(event.input_data, limit)
            event.output_data = truncate(event.output_data, limit)

        await super().publish_event(event, channel)

    async def listen(
        self, user_id: str, graph_id: str = "*", graph_exec_id: str = "*"
    ) -> AsyncGenerator[ExecutionEvent, None]:
        async for event in self.listen_events(f"{user_id}/{graph_id}/{graph_exec_id}"):
            yield event


# --------------------- KV Data Functions --------------------- #


async def get_execution_kv_data(user_id: str, key: str) -> Any | None:
    """
    Get key-value data for a user and key.

    Args:
        user_id: The id of the User.
        key: The key to retrieve data for.

    Returns:
        The data associated with the key, or None if not found.
    """
    kv_data = await AgentNodeExecutionKeyValueData.prisma().find_unique(
        where={"userId_key": {"userId": user_id, "key": key}}
    )
    return (
        type_utils.convert(kv_data.data, type[Any])
        if kv_data and kv_data.data
        else None
    )


async def set_execution_kv_data(
    user_id: str, node_exec_id: str, key: str, data: Any
) -> Any | None:
    """
    Set key-value data for a user and key.

    Args:
        user_id: The id of the User.
        node_exec_id: The id of the AgentNodeExecution.
        key: The key to store data under.
        data: The data to store.
    """
    resp = await AgentNodeExecutionKeyValueData.prisma().upsert(
        where={"userId_key": {"userId": user_id, "key": key}},
        data={
            "create": AgentNodeExecutionKeyValueDataCreateInput(
                userId=user_id,
                agentNodeExecutionId=node_exec_id,
                key=key,
                data=SafeJson(data) if data is not None else None,
            ),
            "update": {
                "agentNodeExecutionId": node_exec_id,
                "data": SafeJson(data) if data is not None else None,
            },
        },
    )
    return type_utils.convert(resp.data, type[Any]) if resp and resp.data else None


async def get_block_error_stats(
    start_time: datetime, end_time: datetime
) -> list[BlockErrorStats]:
    """Get block execution stats using efficient SQL aggregation."""

    query_template = """
    SELECT 
        n."agentBlockId" as block_id,
        COUNT(*) as total_executions,
        SUM(CASE WHEN ne."executionStatus" = 'FAILED' THEN 1 ELSE 0 END) as failed_executions
    FROM {schema_prefix}"AgentNodeExecution" ne
    JOIN {schema_prefix}"AgentNode" n ON ne."agentNodeId" = n.id
    WHERE ne."addedTime" >= $1::timestamp AND ne."addedTime" <= $2::timestamp
    GROUP BY n."agentBlockId"
    HAVING COUNT(*) >= 10
    """

    result = await query_raw_with_schema(query_template, start_time, end_time)

    # Convert to typed data structures
    return [
        BlockErrorStats(
            block_id=row["block_id"],
            total_executions=int(row["total_executions"]),
            failed_executions=int(row["failed_executions"]),
        )
        for row in result
    ]


async def update_graph_execution_share_status(
    execution_id: str,
    user_id: str,
    is_shared: bool,
    share_token: str | None,
    shared_at: datetime | None,
) -> None:
    """Update the sharing status of a graph execution."""
    await AgentGraphExecution.prisma().update(
        where={"id": execution_id},
        data={
            "isShared": is_shared,
            "shareToken": share_token,
            "sharedAt": shared_at,
        },
    )


async def get_graph_execution_by_share_token(
    share_token: str,
) -> SharedExecutionResponse | None:
    """Get a shared execution with limited public-safe data."""
    execution = await AgentGraphExecution.prisma().find_first(
        where={
            "shareToken": share_token,
            "isShared": True,
            "isDeleted": False,
        },
        include={
            "AgentGraph": True,
            "NodeExecutions": {
                "include": {
                    "Output": True,
                    "Node": {
                        "include": {
                            "AgentBlock": True,
                        }
                    },
                },
            },
        },
    )

    if not execution:
        return None

    # Extract outputs from OUTPUT blocks only (consistent with GraphExecution.from_db)
    outputs: CompletedBlockOutput = defaultdict(list)
    if execution.NodeExecutions:
        for node_exec in execution.NodeExecutions:
            if node_exec.Node and node_exec.Node.agentBlockId:
                # Get the block definition to check its type
                block = get_block(node_exec.Node.agentBlockId)

                if block and block.block_type == BlockType.OUTPUT:
                    # For OUTPUT blocks, the data is stored in executionData or Input
                    # The executionData contains the structured input with 'name' and 'value' fields
                    if hasattr(node_exec, "executionData") and node_exec.executionData:
                        exec_data = type_utils.convert(
                            node_exec.executionData, dict[str, Any]
                        )
                        if "name" in exec_data:
                            name = exec_data["name"]
                            value = exec_data.get("value")
                            outputs[name].append(value)
                    elif node_exec.Input:
                        # Build input_data from Input relation
                        input_data = {}
                        for data in node_exec.Input:
                            if data.name and data.data is not None:
                                input_data[data.name] = type_utils.convert(
                                    data.data, JsonValue
                                )

                        if "name" in input_data:
                            name = input_data["name"]
                            value = input_data.get("value")
                            outputs[name].append(value)

    return SharedExecutionResponse(
        id=execution.id,
        graph_name=(
            execution.AgentGraph.name
            if (execution.AgentGraph and execution.AgentGraph.name)
            else "Untitled Agent"
        ),
        graph_description=(
            execution.AgentGraph.description if execution.AgentGraph else None
        ),
        status=ExecutionStatus(execution.executionStatus),
        created_at=execution.createdAt,
        outputs=outputs,
    )
