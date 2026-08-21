"""Node execution progress tracking."""

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
class ExecutionOutputEntry(BaseModel):
    node: Node
    node_exec_id: str
    data: BlockOutputEntry


class NodeExecutionProgress:
    def __init__(self):
        self.output: dict[str, list[ExecutionOutputEntry]] = defaultdict(list)
        self.tasks: dict[str, Future] = {}
        self._lock = threading.Lock()

    def add_task(self, node_exec_id: str, task: Future):
        self.tasks[node_exec_id] = task

    def add_output(self, output: ExecutionOutputEntry):
        with self._lock:
            self.output[output.node_exec_id].append(output)

    def pop_output(self) -> ExecutionOutputEntry | None:
        exec_id = self._next_exec()
        if not exec_id:
            return None

        if self._pop_done_task(exec_id):
            return self.pop_output()

        with self._lock:
            if next_output := self.output[exec_id]:
                return next_output.pop(0)

        return None

    def is_done(self, wait_time: float = 0.0) -> bool:
        exec_id = self._next_exec()
        if not exec_id:
            return True

        if self._pop_done_task(exec_id):
            return self.is_done(wait_time)

        if wait_time <= 0:
            return False

        try:
            self.tasks[exec_id].result(wait_time)
        except TimeoutError:
            pass
        except Exception as e:
            logger.error(
                f"Task for exec ID {exec_id} failed with error: {e.__class__.__name__} {str(e)}"
            )
            pass
        return self.is_done(0)

    def stop(self) -> list[str]:
        """
        Stops all tasks and clears the output.
        This is useful for cleaning up when the execution is cancelled or terminated.
        Returns a list of execution IDs that were stopped.
        """
        cancelled_ids = []
        for task_id, task in self.tasks.items():
            if task.done():
                continue
            task.cancel()
            cancelled_ids.append(task_id)
        return cancelled_ids

    def wait_for_done(self, timeout: float = 5.0):
        """
        Wait for all cancelled tasks to complete cancellation.

        Args:
            timeout: Maximum time to wait for cancellation in seconds
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            while self.pop_output():
                pass

            if self.is_done():
                return

            time.sleep(0.1)  # Small delay to avoid busy waiting

        raise TimeoutError(
            f"Timeout waiting for cancellation of tasks: {list(self.tasks.keys())}"
        )

    def _pop_done_task(self, exec_id: str) -> bool:
        task = self.tasks.get(exec_id)
        if not task:
            return True

        if not task.done():
            return False

        with self._lock:
            if self.output[exec_id]:
                return False

        self.tasks.pop(exec_id)
        return True

    def _next_exec(self) -> str | None:
        if not self.tasks:
            return None
        return next(iter(self.tasks.keys()))
