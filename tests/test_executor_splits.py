"""Structural checks for executor processor / cost-helper splits."""

from __future__ import annotations

from pathlib import Path

EXECUTOR = (
    Path(__file__).resolve().parents[1]
    / "autogpt_platform"
    / "backend"
    / "backend"
    / "executor"
)


def test_on_node_execution_lives_in_node_mixin():
    node = (EXECUTOR / "processor_node.py").read_text(encoding="utf-8")
    assert "async def on_node_execution" in node
    assert "async def _on_node_execution" in node
    assert "async def _process_node_output" in node


def test_processor_entrypoint_is_mixin_composition():
    processor = (EXECUTOR / "processor.py").read_text(encoding="utf-8")
    assert "ExecutionProcessorNodeMixin" in processor
    assert "ExecutionProcessorGraphMixin" in processor
    assert len(processor.splitlines()) < 200


def test_block_usage_cost_exported_from_utils():
    utils = (EXECUTOR / "utils.py").read_text(encoding="utf-8")
    assert "block_usage_cost" in utils
    assert (EXECUTOR / "utils_cost.py").is_file()
