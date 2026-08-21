"""Pure block-cost matching helpers (no DB / Prisma imports)."""

from __future__ import annotations

from typing import Any, Mapping


def is_cost_filter_match(
    cost_filter: Mapping[str, Any] | Any,
    input_data: Mapping[str, Any] | Any,
) -> bool:
    """
    Filter rules:
      - If cost_filter is an object, then check if cost_filter is the subset of input_data
      - Otherwise, check if cost_filter is equal to input_data.
      - Undefined, null, and empty string are considered as equal.
    """
    if not isinstance(cost_filter, dict) or not isinstance(input_data, dict):
        return cost_filter == input_data

    return all(
        (not input_data.get(k) and not v)
        or (input_data.get(k) and is_cost_filter_match(v, input_data[k]))
        for k, v in cost_filter.items()
    )


def compute_block_usage_cost(
    block_costs: list[Any] | None,
    input_data: Mapping[str, Any],
    data_size: float = 0,
    run_time: float = 0,
) -> tuple[int, dict[str, Any]]:
    """
    Calculate usage cost from a list of BlockCost-like objects.

    Each cost entry is expected to expose ``cost_filter``, ``cost_type``, and
    ``cost_amount``. ``cost_type`` should be comparable to the string values
    ``run``, ``second``, and ``byte`` (enum ``.value`` is accepted).
    """
    if not block_costs:
        return 0, {}

    for block_cost in block_costs:
        cost_filter = block_cost.cost_filter
        if not is_cost_filter_match(cost_filter, input_data):
            continue

        cost_type = getattr(block_cost.cost_type, "value", block_cost.cost_type)
        if cost_type == "run":
            return block_cost.cost_amount, dict(cost_filter)
        if cost_type == "second":
            return int(run_time * block_cost.cost_amount), dict(cost_filter)
        if cost_type == "byte":
            return int(data_size * block_cost.cost_amount), dict(cost_filter)

    return 0, {}
