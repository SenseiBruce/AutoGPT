"""Execution domain models."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
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
    Mapping,
    Optional,
    TypeVar,
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
from .event_bus import AsyncRedisEventBus, RedisEventBus
from .includes import (
    EXECUTION_RESULT_INCLUDE,
    EXECUTION_RESULT_ORDER,
    GRAPH_EXECUTION_INCLUDE_WITH_NODES,
    graph_execution_include,
)
from .model import CredentialsMetaInput, GraphExecutionStats, NodeExecutionStats

T = TypeVar("T")

logger = logging.getLogger(__name__)
config = Config()


# -------------------------- Models -------------------------- #


class BlockErrorStats(BaseModel):
    """Typed data structure for block error statistics."""

    block_id: str
    total_executions: int
    failed_executions: int

    @property
    def error_rate(self) -> float:
        """Calculate error rate as a percentage."""
        if self.total_executions == 0:
            return 0.0
        return (self.failed_executions / self.total_executions) * 100


ExecutionStatus = AgentExecutionStatus
NodeInputMask = Mapping[str, JsonValue]
NodesInputMasks = Mapping[str, NodeInputMask]

# dest: source
VALID_STATUS_TRANSITIONS = {
    ExecutionStatus.QUEUED: [
        ExecutionStatus.INCOMPLETE,
    ],
    ExecutionStatus.RUNNING: [
        ExecutionStatus.INCOMPLETE,
        ExecutionStatus.QUEUED,
        ExecutionStatus.TERMINATED,  # For resuming halted execution
    ],
    ExecutionStatus.COMPLETED: [
        ExecutionStatus.RUNNING,
    ],
    ExecutionStatus.FAILED: [
        ExecutionStatus.INCOMPLETE,
        ExecutionStatus.QUEUED,
        ExecutionStatus.RUNNING,
    ],
    ExecutionStatus.TERMINATED: [
        ExecutionStatus.INCOMPLETE,
        ExecutionStatus.QUEUED,
        ExecutionStatus.RUNNING,
    ],
}


class GraphExecutionMeta(BaseDbModel):
    id: str  # type: ignore # Override base class to make this required
    user_id: str
    graph_id: str
    graph_version: int
    inputs: Optional[BlockInput]  # no default -> required in the OpenAPI spec
    credential_inputs: Optional[dict[str, CredentialsMetaInput]]
    nodes_input_masks: Optional[dict[str, BlockInput]]
    preset_id: Optional[str]
    status: ExecutionStatus
    started_at: datetime
    ended_at: datetime
    is_shared: bool = False
    share_token: Optional[str] = None

    class Stats(BaseModel):
        model_config = ConfigDict(
            extra="allow",
            arbitrary_types_allowed=True,
        )

        cost: int = Field(
            default=0,
            description="Execution cost (cents)",
        )
        duration: float = Field(
            default=0,
            description="Seconds from start to end of run",
        )
        duration_cpu_only: float = Field(
            default=0,
            description="CPU sec of duration",
        )
        node_exec_time: float = Field(
            default=0,
            description="Seconds of total node runtime",
        )
        node_exec_time_cpu_only: float = Field(
            default=0,
            description="CPU sec of node_exec_time",
        )
        node_exec_count: int = Field(
            default=0,
            description="Number of node executions",
        )
        node_error_count: int = Field(
            default=0,
            description="Number of node errors",
        )
        error: str | None = Field(
            default=None,
            description="Error message if any",
        )
        activity_status: str | None = Field(
            default=None,
            description="AI-generated summary of what the agent did",
        )
        correctness_score: float | None = Field(
            default=None,
            description="AI-generated score (0.0-1.0) indicating how well the execution achieved its intended purpose",
        )

        def to_db(self) -> GraphExecutionStats:
            return GraphExecutionStats(
                cost=self.cost,
                walltime=self.duration,
                cputime=self.duration_cpu_only,
                nodes_walltime=self.node_exec_time,
                nodes_cputime=self.node_exec_time_cpu_only,
                node_count=self.node_exec_count,
                node_error_count=self.node_error_count,
                error=self.error,
                activity_status=self.activity_status,
                correctness_score=self.correctness_score,
            )

    stats: Stats | None

    @staticmethod
    def from_db(_graph_exec: AgentGraphExecution):
        now = datetime.now(timezone.utc)
        # TODO: make started_at and ended_at optional
        start_time = _graph_exec.startedAt or _graph_exec.createdAt
        end_time = _graph_exec.updatedAt or now

        try:
            stats = GraphExecutionStats.model_validate(_graph_exec.stats)
        except ValueError as e:
            if _graph_exec.stats is not None:
                logger.warning(
                    "Failed to parse invalid graph execution stats "
                    f"{_graph_exec.stats}: {e}"
                )
            stats = None

        return GraphExecutionMeta(
            id=_graph_exec.id,
            user_id=_graph_exec.userId,
            graph_id=_graph_exec.agentGraphId,
            graph_version=_graph_exec.agentGraphVersion,
            inputs=cast(BlockInput | None, _graph_exec.inputs),
            credential_inputs=(
                {
                    name: CredentialsMetaInput.model_validate(cmi)
                    for name, cmi in cast(dict, _graph_exec.credentialInputs).items()
                }
                if _graph_exec.credentialInputs
                else None
            ),
            nodes_input_masks=cast(
                dict[str, BlockInput] | None, _graph_exec.nodesInputMasks
            ),
            preset_id=_graph_exec.agentPresetId,
            status=ExecutionStatus(_graph_exec.executionStatus),
            started_at=start_time,
            ended_at=end_time,
            stats=(
                GraphExecutionMeta.Stats(
                    cost=stats.cost,
                    duration=stats.walltime,
                    duration_cpu_only=stats.cputime,
                    node_exec_time=stats.nodes_walltime,
                    node_exec_time_cpu_only=stats.nodes_cputime,
                    node_exec_count=stats.node_count,
                    node_error_count=stats.node_error_count,
                    error=(
                        str(stats.error)
                        if isinstance(stats.error, Exception)
                        else stats.error
                    ),
                    activity_status=stats.activity_status,
                    correctness_score=stats.correctness_score,
                )
                if stats
                else None
            ),
            is_shared=_graph_exec.isShared,
            share_token=_graph_exec.shareToken,
        )


class GraphExecution(GraphExecutionMeta):
    inputs: BlockInput  # type: ignore - incompatible override is intentional
    outputs: CompletedBlockOutput

    @staticmethod
    def from_db(_graph_exec: AgentGraphExecution):
        if _graph_exec.NodeExecutions is None:
            raise ValueError("Node executions must be included in query")

        graph_exec = GraphExecutionMeta.from_db(_graph_exec)

        complete_node_executions = sorted(
            [
                NodeExecutionResult.from_db(ne, _graph_exec.userId)
                for ne in _graph_exec.NodeExecutions
                if ne.executionStatus != ExecutionStatus.INCOMPLETE
            ],
            key=lambda ne: (ne.queue_time is None, ne.queue_time or ne.add_time),
        )

        inputs = {
            **(
                graph_exec.inputs
                or {
                    # fallback: extract inputs from Agent Input Blocks
                    exec.input_data["name"]: exec.input_data.get("value")
                    for exec in complete_node_executions
                    if (
                        (block := get_block(exec.block_id))
                        and block.block_type == BlockType.INPUT
                    )
                }
            ),
            **{
                # input from webhook-triggered block
                "payload": exec.input_data["payload"]
                for exec in complete_node_executions
                if (
                    (block := get_block(exec.block_id))
                    and block.block_type
                    in [BlockType.WEBHOOK, BlockType.WEBHOOK_MANUAL]
                )
            },
        }

        outputs: CompletedBlockOutput = defaultdict(list)
        for exec in complete_node_executions:
            if (
                block := get_block(exec.block_id)
            ) and block.block_type == BlockType.OUTPUT:
                outputs[exec.input_data["name"]].append(exec.input_data.get("value"))

        return GraphExecution(
            **{
                field_name: getattr(graph_exec, field_name)
                for field_name in GraphExecutionMeta.model_fields
                if field_name != "inputs"
            },
            inputs=inputs,
            outputs=outputs,
        )


class GraphExecutionWithNodes(GraphExecution):
    node_executions: list["NodeExecutionResult"]

    @staticmethod
    def from_db(_graph_exec: AgentGraphExecution):
        if _graph_exec.NodeExecutions is None:
            raise ValueError("Node executions must be included in query")

        graph_exec_with_io = GraphExecution.from_db(_graph_exec)

        node_executions = sorted(
            [
                NodeExecutionResult.from_db(ne, _graph_exec.userId)
                for ne in _graph_exec.NodeExecutions
            ],
            key=lambda ne: (ne.queue_time is None, ne.queue_time or ne.add_time),
        )

        return GraphExecutionWithNodes(
            **{
                field_name: getattr(graph_exec_with_io, field_name)
                for field_name in GraphExecution.model_fields
            },
            node_executions=node_executions,
        )

    def to_graph_execution_entry(
        self,
        user_context: "UserContext",
        compiled_nodes_input_masks: Optional[NodesInputMasks] = None,
        parent_graph_exec_id: Optional[str] = None,
    ):
        return GraphExecutionEntry(
            user_id=self.user_id,
            graph_id=self.graph_id,
            graph_version=self.graph_version or 0,
            graph_exec_id=self.id,
            nodes_input_masks=compiled_nodes_input_masks,
            user_context=user_context,
            parent_graph_exec_id=parent_graph_exec_id,
        )


class NodeExecutionResult(BaseModel):
    user_id: str
    graph_id: str
    graph_version: int
    graph_exec_id: str
    node_exec_id: str
    node_id: str
    block_id: str
    status: ExecutionStatus
    input_data: BlockInput
    output_data: CompletedBlockOutput
    add_time: datetime
    queue_time: datetime | None
    start_time: datetime | None
    end_time: datetime | None

    @staticmethod
    def from_db(_node_exec: AgentNodeExecution, user_id: Optional[str] = None):
        try:
            stats = NodeExecutionStats.model_validate(_node_exec.stats or {})
        except (ValueError, ValidationError):
            stats = NodeExecutionStats()

        if stats.cleared_inputs:
            input_data: BlockInput = defaultdict()
            for name, messages in stats.cleared_inputs.items():
                input_data[name] = messages[-1] if messages else ""
        elif _node_exec.executionData:
            input_data = type_utils.convert(_node_exec.executionData, dict[str, Any])
        else:
            input_data: BlockInput = defaultdict()
            for data in _node_exec.Input or []:
                input_data[data.name] = type_utils.convert(data.data, JsonValue)

        output_data: CompletedBlockOutput = defaultdict(list)

        if stats.cleared_outputs:
            for name, messages in stats.cleared_outputs.items():
                output_data[name].extend(messages)
        else:
            for data in _node_exec.Output or []:
                output_data[data.name].append(type_utils.convert(data.data, JsonValue))

        graph_execution: AgentGraphExecution | None = _node_exec.GraphExecution
        if graph_execution:
            user_id = graph_execution.userId
        elif not user_id:
            raise ValueError(
                "AgentGraphExecution must be included or user_id passed in"
            )

        return NodeExecutionResult(
            user_id=user_id,
            graph_id=graph_execution.agentGraphId if graph_execution else "",
            graph_version=graph_execution.agentGraphVersion if graph_execution else 0,
            graph_exec_id=_node_exec.agentGraphExecutionId,
            block_id=_node_exec.Node.agentBlockId if _node_exec.Node else "",
            node_exec_id=_node_exec.id,
            node_id=_node_exec.agentNodeId,
            status=_node_exec.executionStatus,
            input_data=input_data,
            output_data=output_data,
            add_time=_node_exec.addedTime,
            queue_time=_node_exec.queuedTime,
            start_time=_node_exec.startedTime,
            end_time=_node_exec.endedTime,
        )

    def to_node_execution_entry(
        self, user_context: "UserContext"
    ) -> "NodeExecutionEntry":
        return NodeExecutionEntry(
            user_id=self.user_id,
            graph_exec_id=self.graph_exec_id,
            graph_id=self.graph_id,
            node_exec_id=self.node_exec_id,
            node_id=self.node_id,
            block_id=self.block_id,
            inputs=self.input_data,
            user_context=user_context,
        )


# --------------------- Model functions --------------------- #


