"""Graph/node execution persistence and event broadcast helpers."""
import logging
import threading
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

from redis.asyncio.lock import Lock as AsyncRedisLock

from backend.data import redis_client as redis
from backend.data.block import (
    BlockInput,
)
from backend.data.execution import (
    ExecutionStatus,
    GraphExecution,
    NodeExecutionResult,
)
from backend.data.model import GraphExecutionStats
from backend.util.clients import (
    get_async_execution_event_bus,
    get_database_manager_async_client,
    get_database_manager_client,
    get_execution_event_bus,
)
from backend.util.logging import TruncatedLogger
from backend.util.retry import (
    func_retry,
)
from backend.util.settings import Settings


if TYPE_CHECKING:
    from backend.executor import DatabaseManagerAsyncClient, DatabaseManagerClient


_logger = logging.getLogger(__name__)
logger = TruncatedLogger(_logger, prefix="[GraphExecutor]")
settings = Settings()


# Thread-local storage for ExecutionProcessor instances
_tls = threading.local()


def get_db_client() -> "DatabaseManagerClient":
    return get_database_manager_client()


def get_db_async_client() -> "DatabaseManagerAsyncClient":
    return get_database_manager_async_client()


@func_retry
async def send_async_execution_update(
    entry: GraphExecution | NodeExecutionResult | None,
) -> None:
    if entry is None:
        return
    await get_async_execution_event_bus().publish(entry)


@func_retry
def send_execution_update(entry: GraphExecution | NodeExecutionResult | None):
    if entry is None:
        return
    return get_execution_event_bus().publish(entry)


async def async_update_node_execution_status(
    db_client: "DatabaseManagerAsyncClient",
    exec_id: str,
    status: ExecutionStatus,
    execution_data: BlockInput | None = None,
    stats: dict[str, Any] | None = None,
) -> NodeExecutionResult:
    """Sets status and fetches+broadcasts the latest state of the node execution"""
    exec_update = await db_client.update_node_execution_status(
        exec_id, status, execution_data, stats
    )
    await send_async_execution_update(exec_update)
    return exec_update


def update_node_execution_status(
    db_client: "DatabaseManagerClient",
    exec_id: str,
    status: ExecutionStatus,
    execution_data: BlockInput | None = None,
    stats: dict[str, Any] | None = None,
) -> NodeExecutionResult:
    """Sets status and fetches+broadcasts the latest state of the node execution"""
    exec_update = db_client.update_node_execution_status(
        exec_id, status, execution_data, stats
    )
    send_execution_update(exec_update)
    return exec_update


async def async_update_graph_execution_state(
    db_client: "DatabaseManagerAsyncClient",
    graph_exec_id: str,
    status: ExecutionStatus | None = None,
    stats: GraphExecutionStats | None = None,
) -> GraphExecution | None:
    """Sets status and fetches+broadcasts the latest state of the graph execution"""
    graph_update = await db_client.update_graph_execution_stats(
        graph_exec_id, status, stats
    )
    if graph_update:
        await send_async_execution_update(graph_update)
    else:
        logger.error(f"Failed to update graph execution stats for {graph_exec_id}")
    return graph_update


def update_graph_execution_state(
    db_client: "DatabaseManagerClient",
    graph_exec_id: str,
    status: ExecutionStatus | None = None,
    stats: GraphExecutionStats | None = None,
) -> GraphExecution | None:
    """Sets status and fetches+broadcasts the latest state of the graph execution"""
    graph_update = db_client.update_graph_execution_stats(graph_exec_id, status, stats)
    if graph_update:
        send_execution_update(graph_update)
    else:
        logger.error(f"Failed to update graph execution stats for {graph_exec_id}")
    return graph_update


@asynccontextmanager
async def synchronized(key: str, timeout: int = settings.config.cluster_lock_timeout):
    r = await redis.get_redis_async()
    lock: AsyncRedisLock = r.lock(f"lock:{key}", timeout=timeout)
    try:
        await lock.acquire()
        yield
    finally:
        if await lock.locked() and await lock.owned():
            try:
                await lock.release()
            except Exception as e:
                logger.warning(f"Failed to release lock for key {key}: {e}")


def increment_execution_count(user_id: str) -> int:
    """
    Increment the execution count for a given user,
    this will be used to charge the user for the execution cost.
    """
    r = redis.get_redis()
    k = f"uec:{user_id}"  # User Execution Count global key
    counter = cast(int, r.incr(k))
    if counter == 1:
        r.expire(k, settings.config.execution_counter_expiration_time)
    return counter
