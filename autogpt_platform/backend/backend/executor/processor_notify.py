"""Notification handlers."""

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


class ExecutionProcessorNotifyMixin:
    def _handle_agent_run_notif(
        self,
        db_client: "DatabaseManagerClient",
        graph_exec: GraphExecutionEntry,
        exec_stats: GraphExecutionStats,
    ):
        metadata = db_client.get_graph_metadata(
            graph_exec.graph_id, graph_exec.graph_version
        )
        outputs = db_client.get_node_executions(
            graph_exec.graph_exec_id,
            block_ids=[AgentOutputBlock().id],
        )

        named_outputs = [
            {
                key: value[0] if key == "name" else value
                for key, value in output.output_data.items()
            }
            for output in outputs
        ]

        queue_notification(
            NotificationEventModel(
                user_id=graph_exec.user_id,
                type=NotificationType.AGENT_RUN,
                data=AgentRunData(
                    outputs=named_outputs,
                    agent_name=metadata.name if metadata else "Unknown Agent",
                    credits_used=exec_stats.cost,
                    execution_time=exec_stats.walltime,
                    graph_id=graph_exec.graph_id,
                    node_count=exec_stats.node_count,
                ),
            )
        )

    def _handle_insufficient_funds_notif(
        self,
        db_client: "DatabaseManagerClient",
        user_id: str,
        graph_id: str,
        e: InsufficientBalanceError,
    ):
        shortfall = abs(e.amount) - e.balance
        metadata = db_client.get_graph_metadata(graph_id)
        base_url = (
            settings.config.frontend_base_url or settings.config.platform_base_url
        )

        queue_notification(
            NotificationEventModel(
                user_id=user_id,
                type=NotificationType.ZERO_BALANCE,
                data=ZeroBalanceData(
                    current_balance=e.balance,
                    billing_page_link=f"{base_url}/profile/credits",
                    shortfall=shortfall,
                    agent_name=metadata.name if metadata else "Unknown Agent",
                ),
            )
        )

        try:
            user_email = db_client.get_user_email_by_id(user_id)

            alert_message = (
                f"❌ **Insufficient Funds Alert**\n"
                f"User: {user_email or user_id}\n"
                f"Agent: {metadata.name if metadata else 'Unknown Agent'}\n"
                f"Current balance: ${e.balance / 100:.2f}\n"
                f"Attempted cost: ${abs(e.amount) / 100:.2f}\n"
                f"Shortfall: ${abs(shortfall) / 100:.2f}\n"
                f"[View User Details]({base_url}/admin/spending?search={user_email})"
            )

            get_notification_manager_client().discord_system_alert(
                alert_message, DiscordChannel.PRODUCT
            )
        except Exception as alert_error:
            logger.error(
                f"Failed to send insufficient funds Discord alert: {alert_error}"
            )

    def _handle_low_balance(
        self,
        db_client: "DatabaseManagerClient",
        user_id: str,
        current_balance: int,
        transaction_cost: int,
    ):
        """Check and handle low balance scenarios after a transaction"""
        LOW_BALANCE_THRESHOLD = settings.config.low_balance_threshold

        balance_before = current_balance + transaction_cost

        if (
            current_balance < LOW_BALANCE_THRESHOLD
            and balance_before >= LOW_BALANCE_THRESHOLD
        ):
            base_url = (
                settings.config.frontend_base_url or settings.config.platform_base_url
            )
            queue_notification(
                NotificationEventModel(
                    user_id=user_id,
                    type=NotificationType.LOW_BALANCE,
                    data=LowBalanceData(
                        current_balance=current_balance,
                        billing_page_link=f"{base_url}/profile/credits",
                    ),
                )
            )

            try:
                user_email = db_client.get_user_email_by_id(user_id)
                alert_message = (
                    f"⚠️ **Low Balance Alert**\n"
                    f"User: {user_email or user_id}\n"
                    f"Balance dropped below ${LOW_BALANCE_THRESHOLD / 100:.2f}\n"
                    f"Current balance: ${current_balance / 100:.2f}\n"
                    f"Transaction cost: ${transaction_cost / 100:.2f}\n"
                    f"[View User Details]({base_url}/admin/spending?search={user_email})"
                )
                get_notification_manager_client().discord_system_alert(
                    alert_message, DiscordChannel.PRODUCT
                )
            except Exception as e:
                logger.error(f"Failed to send low balance Discord alert: {e}")
