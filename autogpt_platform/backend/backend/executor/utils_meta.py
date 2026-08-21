"""Execution logging and user-context helpers."""

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
async def get_user_context(user_id: str) -> UserContext:
    """
    Get UserContext for a user, always returns a valid context with timezone.
    Defaults to UTC if user has no timezone set.
    """
    user_context = UserContext(timezone="UTC")  # Default to UTC
    try:
        if prisma.is_connected():
            user = await get_user_by_id(user_id)
        else:
            user = await get_database_manager_async_client().get_user_by_id(user_id)

        if user and user.timezone and user.timezone != "not-set":
            user_context.timezone = user.timezone
            logger.debug(f"Retrieved user context: timezone={user.timezone}")
        else:
            logger.debug("User has no timezone set, using UTC")
    except Exception as e:
        logger.warning(f"Could not fetch user timezone: {e}")
        # Continue with UTC as default

    return user_context


config = Config()
logger = TruncatedLogger(logging.getLogger(__name__), prefix="[GraphExecutorUtil]")

# ============ Resource Helpers ============ #


class LogMetadata(TruncatedLogger):
    def __init__(
        self,
        logger: logging.Logger,
        user_id: str,
        graph_eid: str,
        graph_id: str,
        node_eid: str,
        node_id: str,
        block_name: str,
        max_length: int = 1000,
    ):
        metadata = {
            "component": "ExecutionManager",
            "user_id": user_id,
            "graph_eid": graph_eid,
            "graph_id": graph_id,
            "node_eid": node_eid,
            "node_id": node_id,
            "block_name": block_name,
        }
        prefix = (
            "[ExecutionManager]"
            if is_structured_logging_enabled()
            else f"[ExecutionManager|uid:{user_id}|gid:{graph_id}|nid:{node_id}]|geid:{graph_eid}|neid:{node_eid}|{block_name}]"  # noqa
        )
        super().__init__(
            logger,
            max_length=max_length,
            prefix=prefix,
            metadata=metadata,
        )


