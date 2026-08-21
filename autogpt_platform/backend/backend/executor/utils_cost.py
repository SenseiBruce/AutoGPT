"""Execution cost calculation helpers."""

from backend.data.block import Block, BlockInput
from backend.data.block_cost_config import BLOCK_COSTS
from backend.util.cost_filter import compute_block_usage_cost, is_cost_filter_match
from backend.util.settings import Config

config = Config()

def execution_usage_cost(execution_count: int) -> tuple[int, int]:
    """
    Calculate the cost of executing a graph based on the current number of node executions.

    Args:
        execution_count: Number of node executions

    Returns:
        Tuple of cost amount and the number of execution count that is included in the cost.
    """
    return (
        (
            config.execution_cost_per_threshold
            if execution_count % config.execution_cost_count_threshold == 0
            else 0
        ),
        config.execution_cost_count_threshold,
    )


def block_usage_cost(
    block: Block,
    input_data: BlockInput,
    data_size: float = 0,
    run_time: float = 0,
) -> tuple[int, BlockInput]:
    """
    Calculate the cost of using a block based on the input data and the block type.

    Args:
        block: Block object
        input_data: Input data for the block
        data_size: Size of the input data in bytes
        run_time: Execution time of the block in seconds

    Returns:
        Tuple of cost amount and cost filter
    """
    return compute_block_usage_cost(
        BLOCK_COSTS.get(type(block)),
        input_data,
        data_size=data_size,
        run_time=run_time,
    )


def _is_cost_filter_match(cost_filter: BlockInput, input_data: BlockInput) -> bool:
    """Backward-compatible alias for :func:`is_cost_filter_match`. """
    return is_cost_filter_match(cost_filter, input_data)


