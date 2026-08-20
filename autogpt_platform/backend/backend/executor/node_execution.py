"""Node execution and successor enqueueing."""
import logging
from typing import TYPE_CHECKING, Optional, cast

import sentry_sdk

from backend.blocks.agent import AgentExecutorBlock
from backend.data.block import (
    BlockInput,
    BlockOutput,
    BlockOutputEntry,
    BlockSchema,
)
from backend.data.dynamic_fields import parse_execution_output
from backend.data.execution import (
    ExecutionStatus,
    NodeExecutionEntry,
    NodesInputMasks,
    UserContext,
)
from backend.data.graph import Link, Node
from backend.data.model import NodeExecutionStats
from backend.executor.utils import (
    LogMetadata,
    validate_exec,
)
from backend.integrations.creds_manager import IntegrationCredentialsManager
from backend.util import json
from backend.util.logging import TruncatedLogger
from backend.util.settings import Settings
from backend.executor.execution_updates import (
    async_update_node_execution_status,
    synchronized,
)

if TYPE_CHECKING:
    from backend.executor import DatabaseManagerAsyncClient


_logger = logging.getLogger(__name__)
logger = TruncatedLogger(_logger, prefix="[GraphExecutor]")
settings = Settings()


async def execute_node(
    node: Node,
    creds_manager: IntegrationCredentialsManager,
    data: NodeExecutionEntry,
    execution_stats: NodeExecutionStats | None = None,
    nodes_input_masks: Optional[NodesInputMasks] = None,
) -> BlockOutput:
    """
    Execute a node in the graph. This will trigger a block execution on a node,
    persist the execution result, and return the subsequent node to be executed.

    Args:
        db_client: The client to send execution updates to the server.
        creds_manager: The manager to acquire and release credentials.
        data: The execution data for executing the current node.
        execution_stats: The execution statistics to be updated.

    Returns:
        The subsequent node to be enqueued, or None if there is no subsequent node.
    """
    user_id = data.user_id
    graph_exec_id = data.graph_exec_id
    graph_id = data.graph_id
    node_exec_id = data.node_exec_id
    node_id = data.node_id
    node_block = node.block

    log_metadata = LogMetadata(
        logger=_logger,
        user_id=user_id,
        graph_eid=graph_exec_id,
        graph_id=graph_id,
        node_eid=node_exec_id,
        node_id=node_id,
        block_name=node_block.name,
    )

    # Sanity check: validate the execution input.
    input_data, error = validate_exec(node, data.inputs, resolve_input=False)
    if input_data is None:
        log_metadata.error(f"Skip execution, input validation error: {error}")
        yield "error", error
        return

    # Re-shape the input data for agent block.
    # AgentExecutorBlock specially separate the node input_data & its input_default.
    if isinstance(node_block, AgentExecutorBlock):
        _input_data = AgentExecutorBlock.Input(**node.input_default)
        _input_data.inputs = input_data
        if nodes_input_masks:
            _input_data.nodes_input_masks = nodes_input_masks
        _input_data.user_id = user_id
        input_data = _input_data.model_dump()
    data.inputs = input_data

    # Execute the node
    input_data_str = json.dumps(input_data)
    input_size = len(input_data_str)
    log_metadata.debug("Executed node with input", input=input_data_str)

    # Inject extra execution arguments for the blocks via kwargs
    extra_exec_kwargs: dict = {
        "graph_id": graph_id,
        "node_id": node_id,
        "graph_exec_id": graph_exec_id,
        "node_exec_id": node_exec_id,
        "user_id": user_id,
    }

    # Add user context from NodeExecutionEntry
    extra_exec_kwargs["user_context"] = data.user_context

    # Last-minute fetch credentials + acquire a system-wide read-write lock to prevent
    # changes during execution. ⚠️ This means a set of credentials can only be used by
    # one (running) block at a time; simultaneous execution of blocks using same
    # credentials is not supported.
    creds_lock = None
    input_model = cast(type[BlockSchema], node_block.input_schema)
    for field_name, input_type in input_model.get_credentials_fields().items():
        credentials_meta = input_type(**input_data[field_name])
        credentials, creds_lock = await creds_manager.acquire(
            user_id, credentials_meta.id
        )
        extra_exec_kwargs[field_name] = credentials

    output_size = 0

    # sentry tracking nonsense to get user counts for blocks because isolation scopes don't work :(
    scope = sentry_sdk.get_current_scope()

    # save the tags
    original_user = scope._user
    original_tags = dict(scope._tags) if scope._tags else {}
    # Set user ID for error tracking
    scope.set_user({"id": user_id})

    scope.set_tag("graph_id", graph_id)
    scope.set_tag("node_id", node_id)
    scope.set_tag("block_name", node_block.name)
    scope.set_tag("block_id", node_block.id)
    for k, v in (data.user_context or UserContext(timezone="UTC")).model_dump().items():
        scope.set_tag(f"user_context.{k}", v)

    try:
        async for output_name, output_data in node_block.execute(
            input_data, **extra_exec_kwargs
        ):
            output_data = json.to_dict(output_data)
            output_size += len(json.dumps(output_data))
            log_metadata.debug("Node produced output", **{output_name: output_data})
            yield output_name, output_data
    except Exception:
        # Capture exception WITH context still set before restoring scope
        sentry_sdk.capture_exception(scope=scope)
        sentry_sdk.flush()  # Ensure it's sent before we restore scope
        # Re-raise to maintain normal error flow
        raise
    finally:
        # Ensure credentials are released even if execution fails
        if creds_lock and (await creds_lock.locked()) and (await creds_lock.owned()):
            try:
                await creds_lock.release()
            except Exception as e:
                log_metadata.error(f"Failed to release credentials lock: {e}")

        # Update execution stats
        if execution_stats is not None:
            execution_stats += node_block.execution_stats
            execution_stats.input_size = input_size
            execution_stats.output_size = output_size

        # Restore scope AFTER error has been captured
        scope._user = original_user
        scope._tags = original_tags


async def _enqueue_next_nodes(
    db_client: "DatabaseManagerAsyncClient",
    node: Node,
    output: BlockOutputEntry,
    user_id: str,
    graph_exec_id: str,
    graph_id: str,
    log_metadata: LogMetadata,
    nodes_input_masks: Optional[NodesInputMasks],
    user_context: UserContext,
) -> list[NodeExecutionEntry]:
    async def add_enqueued_execution(
        node_exec_id: str, node_id: str, block_id: str, data: BlockInput
    ) -> NodeExecutionEntry:
        await async_update_node_execution_status(
            db_client=db_client,
            exec_id=node_exec_id,
            status=ExecutionStatus.QUEUED,
            execution_data=data,
        )
        return NodeExecutionEntry(
            user_id=user_id,
            graph_exec_id=graph_exec_id,
            graph_id=graph_id,
            node_exec_id=node_exec_id,
            node_id=node_id,
            block_id=block_id,
            inputs=data,
            user_context=user_context,
        )

    async def register_next_executions(node_link: Link) -> list[NodeExecutionEntry]:
        try:
            return await _register_next_executions(node_link)
        except Exception as e:
            log_metadata.exception(f"Failed to register next executions: {e}")
            return []

    async def _register_next_executions(node_link: Link) -> list[NodeExecutionEntry]:
        enqueued_executions = []
        next_output_name = node_link.source_name
        next_input_name = node_link.sink_name
        next_node_id = node_link.sink_id

        output_name, _ = output
        next_data = parse_execution_output(output, next_output_name)
        if next_data is None and output_name != next_output_name:
            return enqueued_executions
        next_node = await db_client.get_node(next_node_id)

        # Multiple node can register the same next node, we need this to be atomic
        # To avoid same execution to be enqueued multiple times,
        # Or the same input to be consumed multiple times.
        async with synchronized(f"upsert_input-{next_node_id}-{graph_exec_id}"):
            # Add output data to the earliest incomplete execution, or create a new one.
            next_node_exec_id, next_node_input = await db_client.upsert_execution_input(
                node_id=next_node_id,
                graph_exec_id=graph_exec_id,
                input_name=next_input_name,
                input_data=next_data,
            )
            await async_update_node_execution_status(
                db_client=db_client,
                exec_id=next_node_exec_id,
                status=ExecutionStatus.INCOMPLETE,
            )

            # Complete missing static input pins data using the last execution input.
            static_link_names = {
                link.sink_name
                for link in next_node.input_links
                if link.is_static and link.sink_name not in next_node_input
            }
            if static_link_names and (
                latest_execution := await db_client.get_latest_node_execution(
                    next_node_id, graph_exec_id
                )
            ):
                for name in static_link_names:
                    next_node_input[name] = latest_execution.input_data.get(name)

            # Apply node input overrides
            node_input_mask = None
            if nodes_input_masks and (
                node_input_mask := nodes_input_masks.get(next_node.id)
            ):
                next_node_input.update(node_input_mask)

            # Validate the input data for the next node.
            next_node_input, validation_msg = validate_exec(next_node, next_node_input)
            suffix = f"{next_output_name}>{next_input_name}~{next_node_exec_id}:{validation_msg}"

            # Incomplete input data, skip queueing the execution.
            if not next_node_input:
                log_metadata.info(f"Skipped queueing {suffix}")
                return enqueued_executions

            # Input is complete, enqueue the execution.
            log_metadata.info(f"Enqueued {suffix}")
            enqueued_executions.append(
                await add_enqueued_execution(
                    node_exec_id=next_node_exec_id,
                    node_id=next_node_id,
                    block_id=next_node.block_id,
                    data=next_node_input,
                )
            )

            # Next execution stops here if the link is not static.
            if not node_link.is_static:
                return enqueued_executions

            # If link is static, there could be some incomplete executions waiting for it.
            # Load and complete the input missing input data, and try to re-enqueue them.
            for iexec in await db_client.get_node_executions(
                node_id=next_node_id,
                graph_exec_id=graph_exec_id,
                statuses=[ExecutionStatus.INCOMPLETE],
            ):
                idata = iexec.input_data
                ineid = iexec.node_exec_id

                static_link_names = {
                    link.sink_name
                    for link in next_node.input_links
                    if link.is_static and link.sink_name not in idata
                }
                for input_name in static_link_names:
                    idata[input_name] = next_node_input[input_name]

                # Apply node input overrides
                if node_input_mask:
                    idata.update(node_input_mask)

                idata, msg = validate_exec(next_node, idata)
                suffix = f"{next_output_name}>{next_input_name}~{ineid}:{msg}"
                if not idata:
                    log_metadata.info(f"Enqueueing static-link skipped: {suffix}")
                    continue
                log_metadata.info(f"Enqueueing static-link execution {suffix}")
                enqueued_executions.append(
                    await add_enqueued_execution(
                        node_exec_id=iexec.node_exec_id,
                        node_id=next_node_id,
                        block_id=next_node.block_id,
                        data=idata,
                    )
                )
            return enqueued_executions

    return [
        execution
        for link in node.output_links
        for execution in await register_next_executions(link)
    ]


