"""Graph execution entry handlers."""

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


class ExecutionProcessorGraphMixin:
    def on_graph_executor_start(self):
        configure_logging()
        set_service_name("GraphExecutor")
        self.tid = threading.get_ident()
        self.creds_manager = IntegrationCredentialsManager()
        self.node_execution_loop = asyncio.new_event_loop()
        self.node_evaluation_loop = asyncio.new_event_loop()
        self.node_execution_thread = threading.Thread(
            target=self.node_execution_loop.run_forever, daemon=True
        )
        self.node_evaluation_thread = threading.Thread(
            target=self.node_evaluation_loop.run_forever, daemon=True
        )
        self.node_execution_thread.start()
        self.node_evaluation_thread.start()
        logger.info(f"[GraphExecutor] {self.tid} started")

    @error_logged(swallow=False)
    def on_graph_execution(
        self,
        graph_exec: GraphExecutionEntry,
        cancel: threading.Event,
        cluster_lock: ClusterLock,
    ):
        log_metadata = LogMetadata(
            logger=_logger,
            user_id=graph_exec.user_id,
            graph_eid=graph_exec.graph_exec_id,
            graph_id=graph_exec.graph_id,
            node_id="*",
            node_eid="*",
            block_name="-",
        )
        db_client = get_db_client()

        exec_meta = db_client.get_graph_execution_meta(
            user_id=graph_exec.user_id,
            execution_id=graph_exec.graph_exec_id,
        )
        if exec_meta is None:
            log_metadata.warning(
                f"Skipped graph execution #{graph_exec.graph_exec_id}, the graph execution is not found."
            )
            return

        if exec_meta.status in [ExecutionStatus.QUEUED, ExecutionStatus.INCOMPLETE]:
            log_metadata.info(f"⚙️ Starting graph execution #{graph_exec.graph_exec_id}")
            exec_meta.status = ExecutionStatus.RUNNING
            send_execution_update(
                db_client.update_graph_execution_start_time(graph_exec.graph_exec_id)
            )
        elif exec_meta.status == ExecutionStatus.RUNNING:
            log_metadata.info(
                f"⚙️ Graph execution #{graph_exec.graph_exec_id} is already running, continuing where it left off."
            )
        elif exec_meta.status == ExecutionStatus.FAILED:
            exec_meta.status = ExecutionStatus.RUNNING
            log_metadata.info(
                f"⚙️ Graph execution #{graph_exec.graph_exec_id} was disturbed, continuing where it left off."
            )
            update_graph_execution_state(
                db_client=db_client,
                graph_exec_id=graph_exec.graph_exec_id,
                status=ExecutionStatus.RUNNING,
            )
        else:
            log_metadata.warning(
                f"Skipped graph execution {graph_exec.graph_exec_id}, the graph execution status is `{exec_meta.status}`."
            )
            return

        if exec_meta.stats is None:
            exec_stats = GraphExecutionStats()
        else:
            exec_stats = exec_meta.stats.to_db()

        timing_info, status = self._on_graph_execution(
            graph_exec=graph_exec,
            cancel=cancel,
            log_metadata=log_metadata,
            execution_stats=exec_stats,
            cluster_lock=cluster_lock,
        )
        exec_stats.walltime += timing_info.wall_time
        exec_stats.cputime += timing_info.cpu_time

        try:
            # Failure handling
            if isinstance(status, BaseException):
                raise status
            exec_meta.status = status

            # Activity status handling
            activity_response = asyncio.run_coroutine_threadsafe(
                generate_activity_status_for_execution(
                    graph_exec_id=graph_exec.graph_exec_id,
                    graph_id=graph_exec.graph_id,
                    graph_version=graph_exec.graph_version,
                    execution_stats=exec_stats,
                    db_client=get_db_async_client(),
                    user_id=graph_exec.user_id,
                    execution_status=status,
                ),
                self.node_execution_loop,
            ).result(timeout=60.0)
            if activity_response is not None:
                exec_stats.activity_status = activity_response["activity_status"]
                exec_stats.correctness_score = activity_response["correctness_score"]
                log_metadata.info(
                    f"Generated activity status: {activity_response['activity_status']} "
                    f"(correctness: {activity_response['correctness_score']:.2f})"
                )
            else:
                log_metadata.debug(
                    "Activity status generation disabled, not setting fields"
                )
        finally:
            # Communication handling
            self._handle_agent_run_notif(db_client, graph_exec, exec_stats)

            update_graph_execution_state(
                db_client=db_client,
                graph_exec_id=graph_exec.graph_exec_id,
                status=exec_meta.status,
                stats=exec_stats,
            )

