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


class ExecutionProcessor:
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

    @async_error_logged(swallow=True)
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

    def _charge_usage(
        self,
        node_exec: NodeExecutionEntry,
        execution_count: int,
    ) -> tuple[int, int]:
        total_cost = 0
        remaining_balance = 0
        db_client = get_db_client()
        block = get_block(node_exec.block_id)
        if not block:
            logger.error(f"Block {node_exec.block_id} not found.")
            return total_cost, 0

        cost, matching_filter = block_usage_cost(
            block=block, input_data=node_exec.inputs
        )
        if cost > 0:
            remaining_balance = db_client.spend_credits(
                user_id=node_exec.user_id,
                cost=cost,
                metadata=UsageTransactionMetadata(
                    graph_exec_id=node_exec.graph_exec_id,
                    graph_id=node_exec.graph_id,
                    node_exec_id=node_exec.node_exec_id,
                    node_id=node_exec.node_id,
                    block_id=node_exec.block_id,
                    block=block.name,
                    input=matching_filter,
                    reason=f"Ran block {node_exec.block_id} {block.name}",
                ),
            )
            total_cost += cost

        cost, usage_count = execution_usage_cost(execution_count)
        if cost > 0:
            remaining_balance = db_client.spend_credits(
                user_id=node_exec.user_id,
                cost=cost,
                metadata=UsageTransactionMetadata(
                    graph_exec_id=node_exec.graph_exec_id,
                    graph_id=node_exec.graph_id,
                    input={
                        "execution_count": usage_count,
                        "charge": "Execution Cost",
                    },
                    reason=f"Execution Cost for {usage_count} blocks of ex_id:{node_exec.graph_exec_id} g_id:{node_exec.graph_id}",
                ),
            )
            total_cost += cost

        return total_cost, remaining_balance

    @time_measured
    def _on_graph_execution(
        self,
        graph_exec: GraphExecutionEntry,
        cancel: threading.Event,
        log_metadata: LogMetadata,
        execution_stats: GraphExecutionStats,
        cluster_lock: ClusterLock,
    ) -> ExecutionStatus:
        """
        Returns:
            dict: The execution statistics of the graph execution.
            ExecutionStatus: The final status of the graph execution.
            Exception | None: The error that occurred during the execution, if any.
        """
        execution_status: ExecutionStatus = ExecutionStatus.RUNNING
        error: Exception | None = None
        db_client = get_db_client()
        execution_stats_lock = threading.Lock()

        # State holders ----------------------------------------------------
        running_node_execution: dict[str, NodeExecutionProgress] = defaultdict(
            NodeExecutionProgress
        )
        running_node_evaluation: dict[str, Future] = {}
        execution_queue = ExecutionQueue[NodeExecutionEntry]()

        try:
            if db_client.get_credits(graph_exec.user_id) <= 0:
                raise InsufficientBalanceError(
                    user_id=graph_exec.user_id,
                    message="You have no credits left to run an agent.",
                    balance=0,
                    amount=1,
                )

            # Input moderation
            try:
                if moderation_error := asyncio.run_coroutine_threadsafe(
                    automod_manager.moderate_graph_execution_inputs(
                        db_client=get_db_async_client(),
                        graph_exec=graph_exec,
                    ),
                    self.node_evaluation_loop,
                ).result(timeout=30.0):
                    raise moderation_error
            except asyncio.TimeoutError:
                log_metadata.warning(
                    f"Input moderation timed out for graph execution {graph_exec.graph_exec_id}, bypassing moderation and continuing execution"
                )
                # Continue execution without moderation

            # ------------------------------------------------------------
            # Pre‑populate queue ---------------------------------------
            # ------------------------------------------------------------
            for node_exec in db_client.get_node_executions(
                graph_exec.graph_exec_id,
                statuses=[
                    ExecutionStatus.RUNNING,
                    ExecutionStatus.QUEUED,
                    ExecutionStatus.TERMINATED,
                ],
            ):
                node_entry = node_exec.to_node_execution_entry(graph_exec.user_context)
                execution_queue.add(node_entry)

            # ------------------------------------------------------------
            # Main dispatch / polling loop -----------------------------
            # ------------------------------------------------------------
            while not execution_queue.empty():
                if cancel.is_set():
                    break

                queued_node_exec = execution_queue.get()

                log_metadata.debug(
                    f"Dispatching node execution {queued_node_exec.node_exec_id} "
                    f"for node {queued_node_exec.node_id}",
                )

                # Charge usage (may raise) ------------------------------
                try:
                    cost, remaining_balance = self._charge_usage(
                        node_exec=queued_node_exec,
                        execution_count=increment_execution_count(graph_exec.user_id),
                    )
                    with execution_stats_lock:
                        execution_stats.cost += cost
                    # Check if we crossed the low balance threshold
                    self._handle_low_balance(
                        db_client=db_client,
                        user_id=graph_exec.user_id,
                        current_balance=remaining_balance,
                        transaction_cost=cost,
                    )
                except InsufficientBalanceError as balance_error:
                    error = balance_error  # Set error to trigger FAILED status
                    node_exec_id = queued_node_exec.node_exec_id
                    db_client.upsert_execution_output(
                        node_exec_id=node_exec_id,
                        output_name="error",
                        output_data=str(error),
                    )
                    update_node_execution_status(
                        db_client=db_client,
                        exec_id=node_exec_id,
                        status=ExecutionStatus.FAILED,
                    )

                    self._handle_insufficient_funds_notif(
                        db_client,
                        graph_exec.user_id,
                        graph_exec.graph_id,
                        error,
                    )
                    # Gracefully stop the execution loop
                    break

                # Add input overrides -----------------------------
                node_id = queued_node_exec.node_id
                if (nodes_input_masks := graph_exec.nodes_input_masks) and (
                    node_input_mask := nodes_input_masks.get(node_id)
                ):
                    queued_node_exec.inputs.update(node_input_mask)

                # Kick off async node execution -------------------------
                node_execution_task = asyncio.run_coroutine_threadsafe(
                    self.on_node_execution(
                        node_exec=queued_node_exec,
                        node_exec_progress=running_node_execution[node_id],
                        nodes_input_masks=nodes_input_masks,
                        graph_stats_pair=(
                            execution_stats,
                            execution_stats_lock,
                        ),
                    ),
                    self.node_execution_loop,
                )
                running_node_execution[node_id].add_task(
                    node_exec_id=queued_node_exec.node_exec_id,
                    task=node_execution_task,
                )

                # Poll until queue refills or all inflight work done ----
                while execution_queue.empty() and (
                    running_node_execution or running_node_evaluation
                ):
                    if cancel.is_set():
                        break

                    # --------------------------------------------------
                    # Handle inflight evaluations ---------------------
                    # --------------------------------------------------
                    node_output_found = False
                    for node_id, inflight_exec in list(running_node_execution.items()):
                        if cancel.is_set():
                            break

                        # node evaluation future -----------------
                        if inflight_eval := running_node_evaluation.get(node_id):
                            if not inflight_eval.done():
                                continue
                            try:
                                inflight_eval.result(timeout=0)
                                running_node_evaluation.pop(node_id)
                            except Exception as e:
                                log_metadata.error(f"Node eval #{node_id} failed: {e}")

                        # node execution future ---------------------------
                        if inflight_exec.is_done():
                            running_node_execution.pop(node_id)
                            continue

                        if output := inflight_exec.pop_output():
                            node_output_found = True
                            running_node_evaluation[node_id] = (
                                asyncio.run_coroutine_threadsafe(
                                    self._process_node_output(
                                        output=output,
                                        node_id=node_id,
                                        graph_exec=graph_exec,
                                        log_metadata=log_metadata,
                                        nodes_input_masks=nodes_input_masks,
                                        execution_queue=execution_queue,
                                    ),
                                    self.node_evaluation_loop,
                                )
                            )
                    if (
                        not node_output_found
                        and execution_queue.empty()
                        and (running_node_execution or running_node_evaluation)
                    ):
                        cluster_lock.refresh()
                        time.sleep(0.1)

            # loop done --------------------------------------------------

            # Output moderation
            try:
                if moderation_error := asyncio.run_coroutine_threadsafe(
                    automod_manager.moderate_graph_execution_outputs(
                        db_client=get_db_async_client(),
                        graph_exec_id=graph_exec.graph_exec_id,
                        user_id=graph_exec.user_id,
                        graph_id=graph_exec.graph_id,
                    ),
                    self.node_evaluation_loop,
                ).result(timeout=30.0):
                    raise moderation_error
            except asyncio.TimeoutError:
                log_metadata.warning(
                    f"Output moderation timed out for graph execution {graph_exec.graph_exec_id}, bypassing moderation and continuing execution"
                )
                # Continue execution without moderation

            # Determine final execution status based on whether there was an error or termination
            if cancel.is_set():
                execution_status = ExecutionStatus.TERMINATED
            elif error is not None:
                execution_status = ExecutionStatus.FAILED
            else:
                execution_status = ExecutionStatus.COMPLETED

            if error:
                execution_stats.error = str(error) or type(error).__name__

            return execution_status

        except BaseException as e:
            error = (
                e
                if isinstance(e, Exception)
                else Exception(f"{e.__class__.__name__}: {e}")
            )
            if not execution_stats.error:
                execution_stats.error = str(error)

            known_errors = (InsufficientBalanceError, ModerationError)
            if isinstance(error, known_errors):
                return ExecutionStatus.FAILED

            execution_status = ExecutionStatus.FAILED
            log_metadata.exception(
                f"Failed graph execution {graph_exec.graph_exec_id}: {error}"
            )

            # Send rate-limited Discord alert for unknown/unexpected errors
            send_rate_limited_discord_alert(
                "graph_execution",
                error,
                "unknown_error",
                f"🚨 **Unknown Graph Execution Error**\n"
                f"User: {graph_exec.user_id}\n"
                f"Graph ID: {graph_exec.graph_id}\n"
                f"Execution ID: {graph_exec.graph_exec_id}\n"
                f"Error Type: {type(error).__name__}\n"
                f"Error: {str(error)[:200]}{'...' if len(str(error)) > 200 else ''}\n",
            )

            raise

        finally:
            self._cleanup_graph_execution(
                execution_queue=execution_queue,
                running_node_execution=running_node_execution,
                running_node_evaluation=running_node_evaluation,
                execution_status=execution_status,
                error=error,
                graph_exec_id=graph_exec.graph_exec_id,
                log_metadata=log_metadata,
                db_client=db_client,
            )

    @error_logged(swallow=True)
    def _cleanup_graph_execution(
        self,
        execution_queue: ExecutionQueue[NodeExecutionEntry],
        running_node_execution: dict[str, "NodeExecutionProgress"],
        running_node_evaluation: dict[str, Future],
        execution_status: ExecutionStatus,
        error: Exception | None,
        graph_exec_id: str,
        log_metadata: LogMetadata,
        db_client: "DatabaseManagerClient",
    ) -> None:
        """
        Clean up running node executions and evaluations when graph execution ends.
        This method is decorated with @error_logged(swallow=True) to ensure cleanup
        never fails in the finally block.
        """
        # Cancel and wait for all node executions to complete
        for node_id, inflight_exec in running_node_execution.items():
            if inflight_exec.is_done():
                continue
            log_metadata.info(f"Stopping node execution {node_id}")
            inflight_exec.stop()

        for node_id, inflight_exec in running_node_execution.items():
            try:
                inflight_exec.wait_for_done(timeout=3600.0)
            except TimeoutError:
                log_metadata.exception(
                    f"Node execution #{node_id} did not stop in time, "
                    "it may be stuck or taking too long."
                )

        # Wait the remaining inflight evaluations to finish
        for node_id, inflight_eval in running_node_evaluation.items():
            try:
                inflight_eval.result(timeout=3600.0)
            except TimeoutError:
                log_metadata.exception(
                    f"Node evaluation #{node_id} did not stop in time, "
                    "it may be stuck or taking too long."
                )

        while queued_execution := execution_queue.get_or_none():
            update_node_execution_status(
                db_client=db_client,
                exec_id=queued_execution.node_exec_id,
                status=execution_status,
                stats={"error": str(error)} if error else None,
            )

        clean_exec_files(graph_exec_id)

    @async_error_logged(swallow=True)
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
