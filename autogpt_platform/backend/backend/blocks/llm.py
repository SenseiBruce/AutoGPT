# flake8: noqa: E501
"""LLM blocks public API."""

from backend.blocks.llm_blocks import (
    AIBlockBase,
    AIConversationBlock,
    AIListGeneratorBlock,
    AICredentialsField,
    AIStructuredResponseGeneratorBlock,
    AITextGeneratorBlock,
    AITextSummarizerBlock,
    SummaryStyle,
    TEST_CREDENTIALS,
    TEST_CREDENTIALS_INPUT,
    trim_prompt,
)
from backend.blocks.llm_call import (
    LLMResponse,
    ToolCall,
    ToolContentBlock,
    convert_openai_tool_fmt_to_anthropic,
    extract_openai_reasoning,
    extract_openai_tool_calls,
    get_parallel_tool_calls_param,
    llm_call,
)
from backend.blocks.llm_models import LlmModel, ModelMetadata

__all__ = [
    "AIBlockBase",
    "AIConversationBlock",
    "AIListGeneratorBlock",
    "AICredentialsField",
    "AIStructuredResponseGeneratorBlock",
    "AITextGeneratorBlock",
    "AITextSummarizerBlock",
    "LLMResponse",
    "LlmModel",
    "ModelMetadata",
    "SummaryStyle",
    "TEST_CREDENTIALS",
    "TEST_CREDENTIALS_INPUT",
    "ToolCall",
    "ToolContentBlock",
    "convert_openai_tool_fmt_to_anthropic",
    "extract_openai_reasoning",
    "extract_openai_tool_calls",
    "get_parallel_tool_calls_param",
    "llm_call",
    "trim_prompt",
]
