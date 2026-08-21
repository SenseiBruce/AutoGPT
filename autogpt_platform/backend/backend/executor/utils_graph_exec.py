"""Graph execution start/stop and queue helpers."""

import asyncio
import logging
import threading
import time
from collections import defaultdict
from concurrent.futures import Future
from typing import Mapping, Optional, cast

from pydantic import BaseModel, JsonValue, ValidationError

from backend.data import execution as execution_db
from backend.data import graph as graph_db
from backend.data.block import (
    Block,
    BlockInput,
    BlockOutputEntry,
    BlockType,
    get_block,
)
from backend.data.block_cost_config import BLOCK_COSTS
from backend.data.db import prisma
from backend.util.cost_filter import compute_block_usage_cost, is_cost_filter_match
from backend.executor.utils_meta import get_user_context
from backend.executor.utils_validate import validate_and_construct_node_execution_input


# Import dynamic field utilities from centralized location
from backend.data.dynamic_fields import merge_execution_input
from backend.data.execution import (
    ExecutionStatus,
    GraphExecutionMeta,
    GraphExecutionStats,
    GraphExecutionWithNodes,
    NodesInputMasks,
    UserContext,
)
from backend.data.graph import GraphModel, Node
from backend.data.model import CredentialsMetaInput
from backend.data.rabbitmq import Exchange, ExchangeType, Queue, RabbitMQConfig
from backend.data.user import get_user_by_id
from backend.util.cache import cached
from backend.util.clients import (
    get_async_execution_event_bus,

    get_async_execution_queue,
    get_database_manager_async_client,
    get_integration_credentials_store,
)
from backend.util.exceptions import GraphValidationError, NotFoundError
from backend.util.logging import TruncatedLogger, is_structured_logging_enabled
from backend.util.settings import Config
from backend.util.type import convert


@cached(maxsize=1000, ttl_seconds=3600)
def create_execution_queue_config() -> RabbitMQConfig:
    """
    Define two exchanges and queues:
    - 'graph_execution' (DIRECT) for run tasks.
    - 'graph_execution_cancel' (FANOUT) for cancel requests.
    """
    run_queue = Queue(
        name=GRAPH_EXECUTION_QUEUE_NAME,
        exchange=GRAPH_EXECUTION_EXCHANGE,
        routing_key=GRAPH_EXECUTION_ROUTING_KEY,
        durable=True,
        auto_delete=False,
        arguments={
            # x-consumer-timeout (1 week)
            # Problem: Default 30-minute consumer timeout kills long-running graph executions
            # Original error: "Consumer acknowledgement timed out after 1800000 ms (30 minutes)"
            # Solution: Disable consumer timeout entirely - let graphs run indefinitely
            # Safety: Heartbeat mechanism now handles dead consumer detection instead
            # Use case: Graph executions that take hours to complete (AI model training, etc.)
            "x-consumer-timeout": GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS
            * 1000,
        },
    )
    cancel_queue = Queue(
        name=GRAPH_EXECUTION_CANCEL_QUEUE_NAME,
        exchange=GRAPH_EXECUTION_CANCEL_EXCHANGE,
        routing_key="",  # not used for FANOUT
        durable=True,
        auto_delete=False,
    )
    return RabbitMQConfig(
        vhost="/",
        exchanges=[GRAPH_EXECUTION_EXCHANGE, GRAPH_EXECUTION_CANCEL_EXCHANGE],
        queues=[run_queue, cancel_queue],
    )


class CancelExecutionEvent(BaseModel):
    graph_exec_id: str


async def _get_child_executions(parent_exec_id: str) -> list["GraphExecutionMeta"]:
    """
    Get all child executions of a parent execution using the execution_db pattern.

    Args:
        parent_exec_id: Parent graph execution ID

    Returns:
        List of child graph executions
    """
    from backend.data.db import prisma

    if prisma.is_connected():
        edb = execution_db
    else:
        edb = get_database_manager_async_client()

    return await edb.get_child_graph_executions(parent_exec_id)


async def stop_graph_execution(
    user_id: str,
    graph_exec_id: str,
    wait_timeout: float = 15.0,
    cascade: bool = True,
):
    """
    Stop a graph execution and optionally all its child executions.

    Mechanism:
    1. Set the cancel event for this execution
    2. If cascade=True, recursively stop all child executions
    3. Graph executor's cancel handler thread detects the event, terminates workers,
       reinitializes worker pool, and returns.
    4. Update execution statuses in DB and set `error` outputs to `"TERMINATED"`.

    Args:
        user_id: User ID who owns the execution
        graph_exec_id: Graph execution ID to stop
        wait_timeout: Maximum time to wait for execution to stop (seconds)
        cascade: If True, recursively stop all child executions
    """
    queue_client = await get_async_execution_queue()
    db = execution_db if prisma.is_connected() else get_database_manager_async_client()

    # First, find and stop all child executions if cascading
    if cascade:
        children = await _get_child_executions(graph_exec_id)
        logger.info(
            f"Stopping {len(children)} child executions of execution {graph_exec_id}"
        )

        # Stop all children in parallel (recursively, with cascading enabled)
        if children:
            await asyncio.gather(
                *[
                    stop_graph_execution(
                        user_id=user_id,
                        graph_exec_id=child.id,
                        wait_timeout=wait_timeout,
                        cascade=True,  # Recursively cascade to grandchildren
                    )
                    for child in children
                ],
                return_exceptions=True,  # Don't fail parent stop if child stop fails
            )

    # Now stop this execution
    await queue_client.publish_message(
        routing_key="",
        message=CancelExecutionEvent(graph_exec_id=graph_exec_id).model_dump_json(),
        exchange=GRAPH_EXECUTION_CANCEL_EXCHANGE,
    )

    if not wait_timeout:
        return

    start_time = time.time()
    while time.time() - start_time < wait_timeout:
        graph_exec = await db.get_graph_execution_meta(
            execution_id=graph_exec_id, user_id=user_id
        )

        if not graph_exec:
            raise NotFoundError(f"Graph execution #{graph_exec_id} not found.")

        if graph_exec.status in [
            ExecutionStatus.TERMINATED,
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
        ]:
            # If graph execution is terminated/completed/failed, cancellation is complete
            await get_async_execution_event_bus().publish(graph_exec)
            return

        if graph_exec.status in [
            ExecutionStatus.QUEUED,
            ExecutionStatus.INCOMPLETE,
        ]:
            # If the graph is still on the queue, we can prevent them from being executed
            # by setting the status to TERMINATED.
            graph_exec.status = ExecutionStatus.TERMINATED

            await asyncio.gather(
                # Update graph execution status
                db.update_graph_execution_stats(
                    graph_exec_id=graph_exec.id,
                    status=ExecutionStatus.TERMINATED,
                ),
                # Publish graph execution event
                get_async_execution_event_bus().publish(graph_exec),
            )
            return

        if graph_exec.status == ExecutionStatus.RUNNING:
            await asyncio.sleep(0.1)

    raise TimeoutError(
        f"Graph execution #{graph_exec_id} will need to take longer than {wait_timeout} seconds to stop. "
        f"You can check the status of the execution in the UI or try again later."
    )


async def add_graph_execution(
    graph_id: str,
    user_id: str,
    inputs: Optional[BlockInput] = None,
    preset_id: Optional[str] = None,
    graph_version: Optional[int] = None,
    graph_credentials_inputs: Optional[Mapping[str, CredentialsMetaInput]] = None,
    nodes_input_masks: Optional[NodesInputMasks] = None,
    parent_graph_exec_id: Optional[str] = None,
    is_sub_graph: bool = False,
) -> GraphExecutionWithNodes:
    """
    Adds a graph execution to the queue and returns the execution entry.

    Args:
        graph_id: The ID of the graph to execute.
        user_id: The ID of the user executing the graph.
        inputs: The input data for the graph execution.
        preset_id: The ID of the preset to use.
        graph_version: The version of the graph to execute.
        graph_credentials_inputs: Credentials inputs to use in the execution.
            Keys should map to the keys generated by `GraphModel.aggregate_credentials_inputs`.
        nodes_input_masks: Node inputs to use in the execution.
        parent_graph_exec_id: The ID of the parent graph execution (for nested executions).
        is_sub_graph: Whether this is a sub-graph execution.
    Returns:
        GraphExecutionEntry: The entry for the graph execution.
    Raises:
        ValueError: If the graph is not found or if there are validation errors.
    """
    if prisma.is_connected():
        edb = execution_db
    else:
        edb = get_database_manager_async_client()

    graph, starting_nodes_input, compiled_nodes_input_masks = (
        await validate_and_construct_node_execution_input(
            graph_id=graph_id,
            user_id=user_id,
            graph_inputs=inputs or {},
            graph_version=graph_version,
            graph_credentials_inputs=graph_credentials_inputs,
            nodes_input_masks=nodes_input_masks,
            is_sub_graph=is_sub_graph,
        )
    )
    graph_exec = None

    try:
        # Sanity check: running add_graph_execution with the properties of
        # the graph_exec created here should create the same execution again.
        graph_exec = await edb.create_graph_execution(
            user_id=user_id,
            graph_id=graph_id,
            graph_version=graph.version,
            inputs=inputs or {},
            credential_inputs=graph_credentials_inputs,
            nodes_input_masks=nodes_input_masks,
            starting_nodes_input=starting_nodes_input,
            preset_id=preset_id,
            parent_graph_exec_id=parent_graph_exec_id,
        )

        graph_exec_entry = graph_exec.to_graph_execution_entry(
            user_context=await get_user_context(user_id),
            compiled_nodes_input_masks=compiled_nodes_input_masks,
            parent_graph_exec_id=parent_graph_exec_id,
        )
        logger.info(
            f"Created graph execution #{graph_exec.id} for graph "
            f"#{graph_id} with {len(starting_nodes_input)} starting nodes. "
            f"Now publishing to execution queue."
        )

        exec_queue = await get_async_execution_queue()
        await exec_queue.publish_message(
            routing_key=GRAPH_EXECUTION_ROUTING_KEY,
            message=graph_exec_entry.model_dump_json(),
            exchange=GRAPH_EXECUTION_EXCHANGE,
        )
        logger.info(f"Published execution {graph_exec.id} to RabbitMQ queue")

        graph_exec.status = ExecutionStatus.QUEUED
        await edb.update_graph_execution_stats(
            graph_exec_id=graph_exec.id,
            status=graph_exec.status,
        )
        await get_async_execution_event_bus().publish(graph_exec)

        return graph_exec
    except BaseException as e:
        err = str(e) or type(e).__name__
        if not graph_exec:
            logger.error(f"Unable to execute graph #{graph_id} failed: {err}")
            raise

        logger.error(
            f"Unable to publish graph #{graph_id} exec #{graph_exec.id}: {err}"
        )
        await edb.update_node_execution_status_batch(
            [node_exec.node_exec_id for node_exec in graph_exec.node_executions],
            ExecutionStatus.FAILED,
        )
        await edb.update_graph_execution_stats(
            graph_exec_id=graph_exec.id,
            status=ExecutionStatus.FAILED,
            stats=GraphExecutionStats(error=err),
        )
        raise


# ============ Execution Output Helpers ============ #


