"""Pure cost-filter unit tests (no Prisma / Poetry required)."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

BACKEND_ROOT = Path(__file__).resolve().parents[1] / "autogpt_platform" / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from backend.util.cost_filter import (  # noqa: E402
    compute_block_usage_cost,
    is_cost_filter_match,
)


def test_is_cost_filter_match_subset_and_empty_equivalence():
    assert is_cost_filter_match({"model": "gpt"}, {"model": "gpt", "n": 1})
    assert is_cost_filter_match({"model": ""}, {"model": None})
    assert not is_cost_filter_match({"model": "gpt"}, {"model": "claude"})


def test_is_cost_filter_match_nested_objects():
    assert is_cost_filter_match(
        {"creds": {"provider": "openai"}},
        {"creds": {"provider": "openai", "id": "x"}},
    )
    assert not is_cost_filter_match(
        {"creds": {"provider": "openai"}},
        {"creds": {"provider": "anthropic"}},
    )


def test_compute_block_usage_cost_run_second_byte():
    run_cost = SimpleNamespace(
        cost_filter={"model": "gpt"},
        cost_type="run",
        cost_amount=5,
    )
    second_cost = SimpleNamespace(
        cost_filter={},
        cost_type="second",
        cost_amount=2,
    )
    byte_cost = SimpleNamespace(
        cost_filter={},
        cost_type="byte",
        cost_amount=3,
    )

    amount, filt = compute_block_usage_cost([run_cost], {"model": "gpt"})
    assert amount == 5
    assert filt == {"model": "gpt"}

    amount, _ = compute_block_usage_cost([second_cost], {}, run_time=4)
    assert amount == 8

    amount, _ = compute_block_usage_cost([byte_cost], {}, data_size=10)
    assert amount == 30


def test_compute_block_usage_cost_no_match_returns_zero():
    cost = SimpleNamespace(
        cost_filter={"model": "gpt"},
        cost_type="run",
        cost_amount=5,
    )
    assert compute_block_usage_cost([cost], {"model": "other"}) == (0, {})
    assert compute_block_usage_cost(None, {}) == (0, {})
