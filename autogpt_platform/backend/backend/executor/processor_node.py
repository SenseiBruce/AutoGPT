"""Node execution handlers."""

import asyncio
import logging
import threading
import time
from collections import defaultdict
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, Optional, TypeVar


from backend.blocks.io import AgentOutputBlock
from backend.data.block import (
    get_block,
)
from backend.data.credit import UsageTransactionMetadata
from backend.data.execution import (
    ExecutionQueue,
    ExecutionStatus,
    GraphExecutionEntry,
    NodeExecutionEntry,
    NodesInputMasks,
)
from backend.data.graph import Node
from backend.data.model import GraphExecutionStats, NodeExecutionStats
from backend.data.notifications import (
    AgentRunData,
    LowBalanceData,
    NotificationEventModel,
    NotificationType,
    ZeroBalanceData,
)
from backend.executor.activity_status_generator import (
    generate_activity_status_for_execution,
)
from backend.executor.utils import (
    ExecutionOutputEntry,
    LogMetadata,
    NodeExecutionProgress,
    block_usage_cost,
    execution_usage_cost,
)
from backend.integrations.creds_manager import IntegrationCredentialsManager
from backend.notifications.notifications import queue_notification
from backend.server.v2.AutoMod.manager import automod_manager
from backend.util.clients import (
    get_notification_manager_client,
)
from backend.util.decorator import (
    async_error_logged,
    async_time_measured,
    error_logged,
    time_measured,
)
from backend.util.exceptions import InsufficientBalanceError, ModerationError
from backend.util.file import clean_exec_files
from backend.util.logging import TruncatedLogger, configure_logging
from backend.util.metrics import DiscordChannel
from backend.util.process import set_service_name
from backend.util.retry import (
    func_retry,
    send_rate_limited_discord_alert,
)
from backend.util.settings import Settings
from backend.executor.execution_updates import (
    async_update_graph_execution_state,
    async_update_node_execution_status,
    get_db_async_client,
    get_db_client,
    increment_execution_count,
    send_async_execution_update,
    send_execution_update,
    update_graph_execution_state,
    update_node_execution_status,
)
from backend.executor.node_execution import _enqueue_next_nodes, execute_node

from .cluster_lock import ClusterLock

if TYPE_CHECKING:
    from backend.executor import DatabaseManagerAsyncClient, DatabaseManagerClient


_logger = logging.getLogger(__name__)
logger = TruncatedLogger(_logger, prefix="[GraphExecutor]")
settings = Settings()


# Thread-local storage for ExecutionProcessor instances
_tls = threading.local()


class ExecutionProcessorNodeMixin:
    async def on_node_execution(
        self,
        node_exec: NodeExecutionEntry,
        node_exec_progress: NodeExecutionProgress,
        nodes_input_masks: Optional[NodesInputMasks],
        graph_stats_pair: tuple[GraphExecutionStats, threading.Lock],
    ) -> NodeExecutionStats:
        log_metadata = LogMetadata(
            logger=_logger,
            user_id=node_exec.user_id,
            graph_eid=node_exec.graph_exec_id,
            graph_id=node_exec.graph_id,
            node_eid=node_exec.node_exec_id,
            node_id=node_exec.node_id,
            block_name=b.name if (b := get_block(node_exec.block_id)) else "-",
        )
        db_client = get_db_async_client()
        node = await db_client.get_node(node_exec.node_id)
        execution_stats = NodeExecutionStats()

        timing_info, status = await self._on_node_execution(
            node=node,
            node_exec=node_exec,
            node_exec_progress=node_exec_progress,
            stats=execution_stats,
            db_client=db_client,
            log_metadata=log_metadata,
            nodes_input_masks=nodes_input_masks,
        )
        if isinstance(status, BaseException):
            raise status

        execution_stats.walltime = timing_info.wall_time
        execution_stats.cputime = timing_info.cpu_time

        graph_stats, graph_stats_lock = graph_stats_pair
        with graph_stats_lock:
            graph_stats.node_count += 1 + execution_stats.extra_steps
            graph_stats.nodes_cputime += execution_stats.cputime
            graph_stats.nodes_walltime += execution_stats.walltime
            graph_stats.cost += execution_stats.extra_cost
            if isinstance(execution_stats.error, Exception):
                graph_stats.node_error_count += 1

        node_error = execution_stats.error
        node_stats = execution_stats.model_dump()
        if node_error and not isinstance(node_error, str):
            node_stats["error"] = str(node_error) or node_stats.__class__.__name__

        await async_update_node_execution_status(
            db_client=db_client,
            exec_id=node_exec.node_exec_id,
            status=status,
            stats=node_stats,
        )
        await async_update_graph_execution_state(
            db_client=db_client,
            graph_exec_id=node_exec.graph_exec_id,
            stats=graph_stats,
        )

        return execution_stats

    @async_time_measured
    async def _on_node_execution(
        self,
        node: Node,
        node_exec: NodeExecutionEntry,
        node_exec_progress: NodeExecutionProgress,
        stats: NodeExecutionStats,
        db_client: "DatabaseManagerAsyncClient",
        log_metadata: LogMetadata,
        nodes_input_masks: Optional[NodesInputMasks] = None,
    ) -> ExecutionStatus:
        status = ExecutionStatus.RUNNING

        async def persist_output(output_name: str, output_data: Any) -> None:
            await db_client.upsert_execution_output(
                node_exec_id=node_exec.node_exec_id,
                output_name=output_name,
                output_data=output_data,
            )
            if exec_update := await db_client.get_node_execution(
                node_exec.node_exec_id
            ):
                await send_async_execution_update(exec_update)

            node_exec_progress.add_output(
                ExecutionOutputEntry(
                    node=node,
                    node_exec_id=node_exec.node_exec_id,
                    data=(output_name, output_data),
                )
            )

        try:
            log_metadata.info(f"Start node execution {node_exec.node_exec_id}")
            await async_update_node_execution_status(
                db_client=db_client,
                exec_id=node_exec.node_exec_id,
                status=ExecutionStatus.RUNNING,
            )

            async for output_name, output_data in execute_node(
                node=node,
                creds_manager=self.creds_manager,
                data=node_exec,
                execution_stats=stats,
                nodes_input_masks=nodes_input_masks,
            ):
                await persist_output(output_name, output_data)

            log_metadata.info(f"Finished node execution {node_exec.node_exec_id}")
            status = ExecutionStatus.COMPLETED

        except BaseException as e:
            stats.error = e

            if isinstance(e, ValueError):
                # Avoid user error being marked as an actual error.
                log_metadata.info(
                    f"Expected failure on node execution {node_exec.node_exec_id}: {type(e).__name__} - {e}"
                )
                status = ExecutionStatus.FAILED
            elif isinstance(e, Exception):
                # If the exception is not a ValueError, it is unexpected.
                log_metadata.exception(
                    f"Unexpected failure on node execution {node_exec.node_exec_id}: {type(e).__name__} - {e}"
                )
                status = ExecutionStatus.FAILED
            else:
                # CancelledError or SystemExit
                log_metadata.warning(
                    f"Interruption error on node execution {node_exec.node_exec_id}: {type(e).__name__}"
                )
                status = ExecutionStatus.TERMINATED

        finally:
            if status == ExecutionStatus.FAILED and stats.error is not None:
                await persist_output(
                    "error", str(stats.error) or type(stats.error).__name__
                )
        return status

    @func_retry
    async def _process_node_output(
        self,
        output: ExecutionOutputEntry,
        node_id: str,
        graph_exec: GraphExecutionEntry,
        log_metadata: LogMetadata,
        nodes_input_masks: Optional[NodesInputMasks],
        execution_queue: ExecutionQueue[NodeExecutionEntry],
    ) -> None:
        """Process a node's output, update its status, and enqueue next nodes.

        Args:
            output: The execution output entry to process
            node_id: The ID of the node that produced the output
            graph_exec: The graph execution entry
            log_metadata: Logger metadata for consistent logging
            nodes_input_masks: Optional map of node input overrides
            execution_queue: Queue to add next executions to
        """
        db_client = get_db_async_client()

        log_metadata.debug(f"Enqueue nodes for {node_id}: {output}")

        for next_execution in await _enqueue_next_nodes(
            db_client=db_client,
            node=output.node,
            output=output.data,
            user_id=graph_exec.user_id,
            graph_exec_id=graph_exec.graph_exec_id,
            graph_id=graph_exec.graph_id,
            log_metadata=log_metadata,
            nodes_input_masks=nodes_input_masks,
            user_context=graph_exec.user_context,
        ):
            execution_queue.add(next_execution)

