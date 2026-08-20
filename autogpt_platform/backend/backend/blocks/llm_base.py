# flake8: noqa: E501
"""LLM block implementations."""

import logging
from abc import ABC
from typing import Literal

from pydantic import SecretStr

from backend.blocks.llm_models import LlmModel
from backend.data.block import (
    Block,
)
from backend.data.model import (
    APIKeyCredentials,
    CredentialsMetaInput,
)
from backend.integrations.providers import ProviderName
from backend.util.logging import TruncatedLogger
from backend.util.text import TextFormatter

logger = TruncatedLogger(logging.getLogger(__name__), "[LLM-Block]")
fmt = TextFormatter(autoescape=False)

LLMProviderName = Literal[
    ProviderName.AIML_API,
    ProviderName.ANTHROPIC,
    ProviderName.GROQ,
    ProviderName.OLLAMA,
    ProviderName.OPENAI,
    ProviderName.OPEN_ROUTER,
    ProviderName.LLAMA_API,
    ProviderName.V0,
]
AICredentials = CredentialsMetaInput[LLMProviderName, Literal["api_key"]]

TEST_CREDENTIALS = APIKeyCredentials(
    id="769f6af7-820b-4d5d-9b7a-ab82bbc165f",
    provider="openai",
    api_key=SecretStr("mock-openai-api-key"),
    title="Mock OpenAI API key",
    expires_at=None,
)
TEST_CREDENTIALS_INPUT = {
    "provider": TEST_CREDENTIALS.provider,
    "id": TEST_CREDENTIALS.id,
    "type": TEST_CREDENTIALS.type,
    "title": TEST_CREDENTIALS.title,
}


def AICredentialsField():
    from backend.data.model import CredentialsField
    return CredentialsField(
        description="API key for the LLM provider.",
        discriminator="model",
        discriminator_mapping={
            model.value: model.metadata.provider for model in LlmModel
        },
    )

class AIBlockBase(Block, ABC):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.prompt = []

    def merge_llm_stats(self, block: "AIBlockBase"):
        self.merge_stats(block.execution_stats)
        self.prompt = block.prompt


def trim_prompt(s: str) -> str:
    """Removes indentation up to and including `|` from a multi-line prompt."""
    lines = s.strip().split("\n")
    return "\n".join([line.strip().lstrip("|") for line in lines])


