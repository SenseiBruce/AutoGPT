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


def init_worker():
    """Initialize ExecutionProcessor instance in thread-local storage"""
    _tls.processor = ExecutionProcessor()
    _tls.processor.on_graph_executor_start()


def execute_graph(
    graph_exec_entry: "GraphExecutionEntry",
    cancel_event: threading.Event,
    cluster_lock: ClusterLock,
):
    """Execute graph using thread-local ExecutionProcessor instance"""
    return _tls.processor.on_graph_execution(
        graph_exec_entry, cancel_event, cluster_lock
    )


T = TypeVar("T")



from backend.executor.processor_graph import ExecutionProcessorGraphMixin
from backend.executor.processor_graph_run import ExecutionProcessorGraphRunMixin
from backend.executor.processor_node import ExecutionProcessorNodeMixin
from backend.executor.processor_notify import ExecutionProcessorNotifyMixin


class ExecutionProcessor(
    ExecutionProcessorNodeMixin,
    ExecutionProcessorGraphMixin,
    ExecutionProcessorGraphRunMixin,
    ExecutionProcessorNotifyMixin,
):
    """
    This class contains event handlers for the process pool executor events.

    The main events are:
        on_graph_executor_start: Initialize the process that executes the graph.
        on_graph_execution: Execution logic for a graph.
        on_node_execution: Execution logic for a node.

    The execution flow:
        1. Graph execution request is added to the queue.
        2. Graph executor loop picks the request from the queue.
        3. Graph executor loop submits the graph execution request to the executor pool.
      [on_graph_execution]
        4. Graph executor initialize the node execution queue.
        5. Graph executor adds the starting nodes to the node execution queue.
        6. Graph executor waits for all nodes to be executed.
      [on_node_execution]
        7. Node executor picks the node execution request from the queue.
        8. Node executor executes the node.
        9. Node executor enqueues the next executed nodes to the node execution queue.
    """
