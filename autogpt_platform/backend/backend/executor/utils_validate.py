"""Node/graph validation and starting-input construction."""

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
# ============ Execution Input Helpers ============ #

# Dynamic field utilities are now imported from backend.data.dynamic_fields


def validate_exec(
    node: Node,
    data: BlockInput,
    resolve_input: bool = True,
) -> tuple[BlockInput | None, str]:
    """
    Validate the input data for a node execution.

    Args:
        node: The node to execute.
        data: The input data for the node execution.
        resolve_input: Whether to resolve dynamic pins into dict/list/object.

    Returns:
        A tuple of the validated data and the block name.
        If the data is invalid, the first element will be None, and the second element
        will be an error message.
        If the data is valid, the first element will be the resolved input data, and
        the second element will be the block name.
    """
    node_block = get_block(node.block_id)
    if not node_block:
        return None, f"Block for {node.block_id} not found."
    schema = node_block.input_schema

    # Input data (without default values) should contain all required fields.
    error_prefix = f"Input data missing or mismatch for `{node_block.name}`:"
    if missing_links := schema.get_missing_links(data, node.input_links):
        return None, f"{error_prefix} unpopulated links {missing_links}"

    # Merge input data with default values and resolve dynamic dict/list/object pins.
    input_default = schema.get_input_defaults(node.input_default)
    data = {**input_default, **data}
    if resolve_input:
        data = merge_execution_input(data)

    # Convert non-matching data types to the expected input schema.
    for name, data_type in schema.__annotations__.items():
        value = data.get(name)
        if (value is not None) and (type(value) is not data_type):
            data[name] = convert(value, data_type)

    # Input data post-merge should contain all required fields from the schema.
    if missing_input := schema.get_missing_input(data):
        return None, f"{error_prefix} missing input {missing_input}"

    # Last validation: Validate the input values against the schema.
    if error := schema.get_mismatch_error(data):
        error_message = f"{error_prefix} {error}"
        logger.warning(error_message)
        return None, error_message

    return data, node_block.name


async def _validate_node_input_credentials(
    graph: GraphModel,
    user_id: str,
    nodes_input_masks: Optional[NodesInputMasks] = None,
) -> dict[str, dict[str, str]]:
    """
    Checks all credentials for all nodes of the graph and returns structured errors.

    Returns:
        dict[node_id, dict[field_name, error_message]]: Credential validation errors per node
    """
    credential_errors: dict[str, dict[str, str]] = defaultdict(dict)

    for node in graph.nodes:
        block = node.block

        # Find any fields of type CredentialsMetaInput
        credentials_fields = block.input_schema.get_credentials_fields()
        if not credentials_fields:
            continue

        for field_name, credentials_meta_type in credentials_fields.items():
            try:
                if (
                    nodes_input_masks
                    and (node_input_mask := nodes_input_masks.get(node.id))
                    and field_name in node_input_mask
                ):
                    credentials_meta = credentials_meta_type.model_validate(
                        node_input_mask[field_name]
                    )
                elif field_name in node.input_default:
                    credentials_meta = credentials_meta_type.model_validate(
                        node.input_default[field_name]
                    )
                else:
                    # Missing credentials
                    credential_errors[node.id][
                        field_name
                    ] = "These credentials are required"
                    continue
            except ValidationError as e:
                credential_errors[node.id][field_name] = f"Invalid credentials: {e}"
                continue

            try:
                # Fetch the corresponding Credentials and perform sanity checks
                credentials = await get_integration_credentials_store().get_creds_by_id(
                    user_id, credentials_meta.id
                )
            except Exception as e:
                # Handle any errors fetching credentials
                credential_errors[node.id][
                    field_name
                ] = f"Credentials not available: {e}"
                continue

            if not credentials:
                credential_errors[node.id][
                    field_name
                ] = f"Unknown credentials #{credentials_meta.id}"
                continue

            if (
                credentials.provider != credentials_meta.provider
                or credentials.type != credentials_meta.type
            ):
                logger.warning(
                    f"Invalid credentials #{credentials.id} for node #{node.id}: "
                    "type/provider mismatch: "
                    f"{credentials_meta.type}<>{credentials.type};"
                    f"{credentials_meta.provider}<>{credentials.provider}"
                )
                credential_errors[node.id][
                    field_name
                ] = "Invalid credentials: type/provider mismatch"
                continue

    return credential_errors


def make_node_credentials_input_map(
    graph: GraphModel,
    graph_credentials_input: Mapping[str, CredentialsMetaInput],
) -> NodesInputMasks:
    """
    Maps credentials for an execution to the correct nodes.

    Params:
        graph: The graph to be executed.
        graph_credentials_input: A (graph_input_name, credentials_meta) map.

    Returns:
        dict[node_id, dict[field_name, CredentialsMetaRaw]]: Node credentials input map.
    """
    result: dict[str, dict[str, JsonValue]] = {}

    # Get aggregated credentials fields for the graph
    graph_cred_inputs = graph.aggregate_credentials_inputs()

    for graph_input_name, (_, compatible_node_fields) in graph_cred_inputs.items():
        # Best-effort map: skip missing items
        if graph_input_name not in graph_credentials_input:
            continue

        # Use passed-in credentials for all compatible node input fields
        for node_id, node_field_name in compatible_node_fields:
            if node_id not in result:
                result[node_id] = {}
            result[node_id][node_field_name] = graph_credentials_input[
                graph_input_name
            ].model_dump(exclude_none=True)

    return result


async def validate_graph_with_credentials(
    graph: GraphModel,
    user_id: str,
    nodes_input_masks: Optional[NodesInputMasks] = None,
) -> Mapping[str, Mapping[str, str]]:
    """
    Validate graph including credentials and return structured errors per node.

    Returns:
        dict[node_id, dict[field_name, error_message]]: Validation errors per node
    """
    # Get input validation errors
    node_input_errors = GraphModel.validate_graph_get_errors(
        graph, for_run=True, nodes_input_masks=nodes_input_masks
    )

    # Get credential input/availability/validation errors
    node_credential_input_errors = await _validate_node_input_credentials(
        graph, user_id, nodes_input_masks
    )

    # Merge credential errors with structural errors
    for node_id, field_errors in node_credential_input_errors.items():
        if node_id not in node_input_errors:
            node_input_errors[node_id] = {}
        node_input_errors[node_id].update(field_errors)

    return node_input_errors


async def _construct_starting_node_execution_input(
    graph: GraphModel,
    user_id: str,
    graph_inputs: BlockInput,
    nodes_input_masks: Optional[NodesInputMasks] = None,
) -> list[tuple[str, BlockInput]]:
    """
    Validates and prepares the input data for executing a graph.
    This function checks the graph for starting nodes, validates the input data
    against the schema, and resolves dynamic input pins into a single list,
    dictionary, or object.

    Args:
        graph (GraphModel): The graph model to execute.
        user_id (str): The ID of the user executing the graph.
        data (BlockInput): The input data for the graph execution.
        node_credentials_map: `dict[node_id, dict[input_name, CredentialsMetaInput]]`

    Returns:
        list[tuple[str, BlockInput]]: A list of tuples, each containing the node ID and
            the corresponding input data for that node.
    """
    # Use new validation function that includes credentials
    validation_errors = await validate_graph_with_credentials(
        graph, user_id, nodes_input_masks
    )
    n_error_nodes = len(validation_errors)
    n_errors = sum(len(errors) for errors in validation_errors.values())
    if validation_errors:
        raise GraphValidationError(
            f"Graph validation failed: {n_errors} issues on {n_error_nodes} nodes",
            node_errors=validation_errors,
        )

    nodes_input = []
    for node in graph.starting_nodes:
        input_data = {}
        block = node.block

        # Note block should never be executed.
        if block.block_type == BlockType.NOTE:
            continue

        # Extract request input data, and assign it to the input pin.
        if block.block_type == BlockType.INPUT:
            input_name = cast(str | None, node.input_default.get("name"))
            if input_name and input_name in graph_inputs:
                input_data = {"value": graph_inputs[input_name]}

        # Apply node input overrides
        if nodes_input_masks and (node_input_mask := nodes_input_masks.get(node.id)):
            input_data.update(node_input_mask)

        input_data, error = validate_exec(node, input_data)
        if input_data is None:
            raise ValueError(error)
        else:
            nodes_input.append((node.id, input_data))

    if not nodes_input:
        raise ValueError(
            "No starting nodes found for the graph, make sure an AgentInput or blocks with no inbound links are present as starting nodes."
        )

    return nodes_input


async def validate_and_construct_node_execution_input(
    graph_id: str,
    user_id: str,
    graph_inputs: BlockInput,
    graph_version: Optional[int] = None,
    graph_credentials_inputs: Optional[Mapping[str, CredentialsMetaInput]] = None,
    nodes_input_masks: Optional[NodesInputMasks] = None,
    is_sub_graph: bool = False,
) -> tuple[GraphModel, list[tuple[str, BlockInput]], NodesInputMasks]:
    """
    Public wrapper that handles graph fetching, credential mapping, and validation+construction.
    This centralizes the logic used by both scheduler validation and actual execution.

    Args:
        graph_id: The ID of the graph to validate/construct.
        user_id: The ID of the user.
        graph_inputs: The input data for the graph execution.
        graph_version: The version of the graph to use.
        graph_credentials_inputs: Credentials inputs to use.
        nodes_input_masks: Node inputs to use.
        is_sub_graph: Whether this is a sub-graph execution.

    Returns:
        GraphModel: Full graph object for the given `graph_id`.
        list[tuple[node_id, BlockInput]]: Starting node IDs with corresponding inputs.
        dict[str, BlockInput]: Node input masks including all passed-in credentials.

    Raises:
        NotFoundError: If the graph is not found.
        GraphValidationError: If the graph has validation issues.
        ValueError: If there are other validation errors.
    """
    if prisma.is_connected():
        gdb = graph_db
    else:
        gdb = get_database_manager_async_client()

    graph: GraphModel | None = await gdb.get_graph(
        graph_id=graph_id,
        user_id=user_id,
        version=graph_version,
        include_subgraphs=True,
        # Execution/access permission is checked by validate_graph_execution_permissions
        skip_access_check=True,
    )
    if not graph:
        raise NotFoundError(f"Graph #{graph_id} not found.")

    # Validate that the user has permission to execute this graph
    # This checks both library membership and execution permissions,
    # raising specific exceptions for appropriate error handling.
    await gdb.validate_graph_execution_permissions(
        user_id=user_id,
        graph_id=graph.id,
        graph_version=graph.version,
        is_sub_graph=is_sub_graph,
    )

    nodes_input_masks = _merge_nodes_input_masks(
        (
            make_node_credentials_input_map(graph, graph_credentials_inputs)
            if graph_credentials_inputs
            else {}
        ),
        nodes_input_masks or {},
    )

    starting_nodes_input = await _construct_starting_node_execution_input(
        graph=graph,
        user_id=user_id,
        graph_inputs=graph_inputs,
        nodes_input_masks=nodes_input_masks,
    )

    return graph, starting_nodes_input, nodes_input_masks


def _merge_nodes_input_masks(
    overrides_map_1: NodesInputMasks,
    overrides_map_2: NodesInputMasks,
) -> NodesInputMasks:
    """Perform a per-node merge of input overrides"""
    result = dict(overrides_map_1).copy()
    for node_id, overrides2 in overrides_map_2.items():
        if node_id in result:
            result[node_id] = {**result[node_id], **overrides2}
        else:
            result[node_id] = overrides2
    return result


# ============ Execution Queue Helpers ============ #

GRAPH_EXECUTION_EXCHANGE = Exchange(
    name="graph_execution",
    type=ExchangeType.DIRECT,
    durable=True,
    auto_delete=False,
)
GRAPH_EXECUTION_QUEUE_NAME = "graph_execution_queue"
GRAPH_EXECUTION_ROUTING_KEY = "graph_execution.run"

GRAPH_EXECUTION_CANCEL_EXCHANGE = Exchange(
    name="graph_execution_cancel",
    type=ExchangeType.FANOUT,
    durable=True,
    auto_delete=True,
)
GRAPH_EXECUTION_CANCEL_QUEUE_NAME = "graph_execution_cancel_queue"

# Graceful shutdown timeout constants
# Agent executions can run for up to 1 day, so we need a graceful shutdown period
# that allows long-running executions to complete naturally
GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS = 24 * 60 * 60  # 1 day to complete active executions


