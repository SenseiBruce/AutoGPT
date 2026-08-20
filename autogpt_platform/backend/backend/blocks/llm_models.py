"""LLM model enum and provider metadata registry."""

from enum import Enum, EnumMeta
from typing import NamedTuple


class ModelMetadata(NamedTuple):
    provider: str
    context_window: int
    max_output_tokens: int | None


class LlmModelMeta(EnumMeta):
    pass


class LlmModel(str, Enum, metaclass=LlmModelMeta):
    # OpenAI models
    O3_MINI = "o3-mini"
    O3 = "o3-2025-04-16"
    O1 = "o1"
    O1_MINI = "o1-mini"
    # GPT-5 models
    GPT5 = "gpt-5-2025-08-07"
    GPT5_MINI = "gpt-5-mini-2025-08-07"
    GPT5_NANO = "gpt-5-nano-2025-08-07"
    GPT5_CHAT = "gpt-5-chat-latest"
    GPT41 = "gpt-4.1-2025-04-14"
    GPT41_MINI = "gpt-4.1-mini-2025-04-14"
    GPT4O_MINI = "gpt-4o-mini"
    GPT4O = "gpt-4o"
    GPT4_TURBO = "gpt-4-turbo"
    GPT3_5_TURBO = "gpt-3.5-turbo"
    # Anthropic models
    CLAUDE_4_1_OPUS = "claude-opus-4-1-20250805"
    CLAUDE_4_OPUS = "claude-opus-4-20250514"
    CLAUDE_4_SONNET = "claude-sonnet-4-20250514"
    CLAUDE_4_5_SONNET = "claude-sonnet-4-5-20250929"
    CLAUDE_4_5_HAIKU = "claude-haiku-4-5-20251001"
    CLAUDE_3_7_SONNET = "claude-3-7-sonnet-20250219"
    CLAUDE_3_HAIKU = "claude-3-haiku-20240307"
    # AI/ML API models
    AIML_API_QWEN2_5_72B = "Qwen/Qwen2.5-72B-Instruct-Turbo"
    AIML_API_LLAMA3_1_70B = "nvidia/llama-3.1-nemotron-70b-instruct"
    AIML_API_LLAMA3_3_70B = "meta-llama/Llama-3.3-70B-Instruct-Turbo"
    AIML_API_META_LLAMA_3_1_70B = "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
    AIML_API_LLAMA_3_2_3B = "meta-llama/Llama-3.2-3B-Instruct-Turbo"
    # Groq models
    LLAMA3_3_70B = "llama-3.3-70b-versatile"
    LLAMA3_1_8B = "llama-3.1-8b-instant"
    # Ollama models
    OLLAMA_LLAMA3_3 = "llama3.3"
    OLLAMA_LLAMA3_2 = "llama3.2"
    OLLAMA_LLAMA3_8B = "llama3"
    OLLAMA_LLAMA3_405B = "llama3.1:405b"
    OLLAMA_DOLPHIN = "dolphin-mistral:latest"
    # OpenRouter models
    OPENAI_GPT_OSS_120B = "openai/gpt-oss-120b"
    OPENAI_GPT_OSS_20B = "openai/gpt-oss-20b"
    GEMINI_2_5_PRO = "google/gemini-2.5-pro-preview-03-25"
    GEMINI_2_5_FLASH = "google/gemini-2.5-flash"
    GEMINI_2_0_FLASH = "google/gemini-2.0-flash-001"
    GEMINI_2_5_FLASH_LITE_PREVIEW = "google/gemini-2.5-flash-lite-preview-06-17"
    GEMINI_2_0_FLASH_LITE = "google/gemini-2.0-flash-lite-001"
    MISTRAL_NEMO = "mistralai/mistral-nemo"
    COHERE_COMMAND_R_08_2024 = "cohere/command-r-08-2024"
    COHERE_COMMAND_R_PLUS_08_2024 = "cohere/command-r-plus-08-2024"
    DEEPSEEK_CHAT = "deepseek/deepseek-chat"  # Actually: DeepSeek V3
    DEEPSEEK_R1_0528 = "deepseek/deepseek-r1-0528"
    PERPLEXITY_SONAR = "perplexity/sonar"
    PERPLEXITY_SONAR_PRO = "perplexity/sonar-pro"
    PERPLEXITY_SONAR_DEEP_RESEARCH = "perplexity/sonar-deep-research"
    NOUSRESEARCH_HERMES_3_LLAMA_3_1_405B = "nousresearch/hermes-3-llama-3.1-405b"
    NOUSRESEARCH_HERMES_3_LLAMA_3_1_70B = "nousresearch/hermes-3-llama-3.1-70b"
    AMAZON_NOVA_LITE_V1 = "amazon/nova-lite-v1"
    AMAZON_NOVA_MICRO_V1 = "amazon/nova-micro-v1"
    AMAZON_NOVA_PRO_V1 = "amazon/nova-pro-v1"
    MICROSOFT_WIZARDLM_2_8X22B = "microsoft/wizardlm-2-8x22b"
    GRYPHE_MYTHOMAX_L2_13B = "gryphe/mythomax-l2-13b"
    META_LLAMA_4_SCOUT = "meta-llama/llama-4-scout"
    META_LLAMA_4_MAVERICK = "meta-llama/llama-4-maverick"
    GROK_4 = "x-ai/grok-4"
    KIMI_K2 = "moonshotai/kimi-k2"
    QWEN3_235B_A22B_THINKING = "qwen/qwen3-235b-a22b-thinking-2507"
    QWEN3_CODER = "qwen/qwen3-coder"
    # Llama API models
    LLAMA_API_LLAMA_4_SCOUT = "Llama-4-Scout-17B-16E-Instruct-FP8"
    LLAMA_API_LLAMA4_MAVERICK = "Llama-4-Maverick-17B-128E-Instruct-FP8"
    LLAMA_API_LLAMA3_3_8B = "Llama-3.3-8B-Instruct"
    LLAMA_API_LLAMA3_3_70B = "Llama-3.3-70B-Instruct"
    # v0 by Vercel models
    V0_1_5_MD = "v0-1.5-md"
    V0_1_5_LG = "v0-1.5-lg"
    V0_1_0_MD = "v0-1.0-md"

    @property
    def metadata(self) -> ModelMetadata:
        return MODEL_METADATA[self]

    @property
    def provider(self) -> str:
        return self.metadata.provider

    @property
    def context_window(self) -> int:
        return self.metadata.context_window

    @property
    def max_output_tokens(self) -> int | None:
        return self.metadata.max_output_tokens


MODEL_METADATA = {
    # https://platform.openai.com/docs/models
    LlmModel.O3: ModelMetadata("openai", 200000, 100000),
    LlmModel.O3_MINI: ModelMetadata("openai", 200000, 100000),  # o3-mini-2025-01-31
    LlmModel.O1: ModelMetadata("openai", 200000, 100000),  # o1-2024-12-17
    LlmModel.O1_MINI: ModelMetadata("openai", 128000, 65536),  # o1-mini-2024-09-12
    # GPT-5 models
    LlmModel.GPT5: ModelMetadata("openai", 400000, 128000),
    LlmModel.GPT5_MINI: ModelMetadata("openai", 400000, 128000),
    LlmModel.GPT5_NANO: ModelMetadata("openai", 400000, 128000),
    LlmModel.GPT5_CHAT: ModelMetadata("openai", 400000, 16384),
    LlmModel.GPT41: ModelMetadata("openai", 1047576, 32768),
    LlmModel.GPT41_MINI: ModelMetadata("openai", 1047576, 32768),
    LlmModel.GPT4O_MINI: ModelMetadata(
        "openai", 128000, 16384
    ),  # gpt-4o-mini-2024-07-18
    LlmModel.GPT4O: ModelMetadata("openai", 128000, 16384),  # gpt-4o-2024-08-06
    LlmModel.GPT4_TURBO: ModelMetadata(
        "openai", 128000, 4096
    ),  # gpt-4-turbo-2024-04-09
    LlmModel.GPT3_5_TURBO: ModelMetadata("openai", 16385, 4096),  # gpt-3.5-turbo-0125
    # https://docs.anthropic.com/en/docs/about-claude/models
    LlmModel.CLAUDE_4_1_OPUS: ModelMetadata(
        "anthropic", 200000, 32000
    ),  # claude-opus-4-1-20250805
    LlmModel.CLAUDE_4_OPUS: ModelMetadata(
        "anthropic", 200000, 32000
    ),  # claude-4-opus-20250514
    LlmModel.CLAUDE_4_SONNET: ModelMetadata(
        "anthropic", 200000, 64000
    ),  # claude-4-sonnet-20250514
    LlmModel.CLAUDE_4_5_SONNET: ModelMetadata(
        "anthropic", 200000, 64000
    ),  # claude-sonnet-4-5-20250929
    LlmModel.CLAUDE_4_5_HAIKU: ModelMetadata(
        "anthropic", 200000, 64000
    ),  # claude-haiku-4-5-20251001
    LlmModel.CLAUDE_3_7_SONNET: ModelMetadata(
        "anthropic", 200000, 64000
    ),  # claude-3-7-sonnet-20250219
    LlmModel.CLAUDE_3_HAIKU: ModelMetadata(
        "anthropic", 200000, 4096
    ),  # claude-3-haiku-20240307
    # https://docs.aimlapi.com/api-overview/model-database/text-models
    LlmModel.AIML_API_QWEN2_5_72B: ModelMetadata("aiml_api", 32000, 8000),
    LlmModel.AIML_API_LLAMA3_1_70B: ModelMetadata("aiml_api", 128000, 40000),
    LlmModel.AIML_API_LLAMA3_3_70B: ModelMetadata("aiml_api", 128000, None),
    LlmModel.AIML_API_META_LLAMA_3_1_70B: ModelMetadata("aiml_api", 131000, 2000),
    LlmModel.AIML_API_LLAMA_3_2_3B: ModelMetadata("aiml_api", 128000, None),
    # https://console.groq.com/docs/models
    LlmModel.LLAMA3_3_70B: ModelMetadata("groq", 128000, 32768),
    LlmModel.LLAMA3_1_8B: ModelMetadata("groq", 128000, 8192),
    # https://ollama.com/library
    LlmModel.OLLAMA_LLAMA3_3: ModelMetadata("ollama", 8192, None),
    LlmModel.OLLAMA_LLAMA3_2: ModelMetadata("ollama", 8192, None),
    LlmModel.OLLAMA_LLAMA3_8B: ModelMetadata("ollama", 8192, None),
    LlmModel.OLLAMA_LLAMA3_405B: ModelMetadata("ollama", 8192, None),
    LlmModel.OLLAMA_DOLPHIN: ModelMetadata("ollama", 32768, None),
    # https://openrouter.ai/models
    LlmModel.GEMINI_2_5_PRO: ModelMetadata("open_router", 1050000, 8192),
    LlmModel.GEMINI_2_5_FLASH: ModelMetadata("open_router", 1048576, 65535),
    LlmModel.GEMINI_2_0_FLASH: ModelMetadata("open_router", 1048576, 8192),
    LlmModel.GEMINI_2_5_FLASH_LITE_PREVIEW: ModelMetadata(
        "open_router", 1048576, 65535
    ),
    LlmModel.GEMINI_2_0_FLASH_LITE: ModelMetadata("open_router", 1048576, 8192),
    LlmModel.MISTRAL_NEMO: ModelMetadata("open_router", 128000, 4096),
    LlmModel.COHERE_COMMAND_R_08_2024: ModelMetadata("open_router", 128000, 4096),
    LlmModel.COHERE_COMMAND_R_PLUS_08_2024: ModelMetadata("open_router", 128000, 4096),
    LlmModel.DEEPSEEK_CHAT: ModelMetadata("open_router", 64000, 2048),
    LlmModel.DEEPSEEK_R1_0528: ModelMetadata("open_router", 163840, 163840),
    LlmModel.PERPLEXITY_SONAR: ModelMetadata("open_router", 127000, 127000),
    LlmModel.PERPLEXITY_SONAR_PRO: ModelMetadata("open_router", 200000, 8000),
    LlmModel.PERPLEXITY_SONAR_DEEP_RESEARCH: ModelMetadata(
        "open_router",
        128000,
        128000,
    ),
    LlmModel.NOUSRESEARCH_HERMES_3_LLAMA_3_1_405B: ModelMetadata(
        "open_router", 131000, 4096
    ),
    LlmModel.NOUSRESEARCH_HERMES_3_LLAMA_3_1_70B: ModelMetadata(
        "open_router", 12288, 12288
    ),
    LlmModel.OPENAI_GPT_OSS_120B: ModelMetadata("open_router", 131072, 131072),
    LlmModel.OPENAI_GPT_OSS_20B: ModelMetadata("open_router", 131072, 32768),
    LlmModel.AMAZON_NOVA_LITE_V1: ModelMetadata("open_router", 300000, 5120),
    LlmModel.AMAZON_NOVA_MICRO_V1: ModelMetadata("open_router", 128000, 5120),
    LlmModel.AMAZON_NOVA_PRO_V1: ModelMetadata("open_router", 300000, 5120),
    LlmModel.MICROSOFT_WIZARDLM_2_8X22B: ModelMetadata("open_router", 65536, 4096),
    LlmModel.GRYPHE_MYTHOMAX_L2_13B: ModelMetadata("open_router", 4096, 4096),
    LlmModel.META_LLAMA_4_SCOUT: ModelMetadata("open_router", 131072, 131072),
    LlmModel.META_LLAMA_4_MAVERICK: ModelMetadata("open_router", 1048576, 1000000),
    LlmModel.GROK_4: ModelMetadata("open_router", 256000, 256000),
    LlmModel.KIMI_K2: ModelMetadata("open_router", 131000, 131000),
    LlmModel.QWEN3_235B_A22B_THINKING: ModelMetadata("open_router", 262144, 262144),
    LlmModel.QWEN3_CODER: ModelMetadata("open_router", 262144, 262144),
    # Llama API models
    LlmModel.LLAMA_API_LLAMA_4_SCOUT: ModelMetadata("llama_api", 128000, 4028),
    LlmModel.LLAMA_API_LLAMA4_MAVERICK: ModelMetadata("llama_api", 128000, 4028),
    LlmModel.LLAMA_API_LLAMA3_3_8B: ModelMetadata("llama_api", 128000, 4028),
    LlmModel.LLAMA_API_LLAMA3_3_70B: ModelMetadata("llama_api", 128000, 4028),
    # v0 by Vercel models
    LlmModel.V0_1_5_MD: ModelMetadata("v0", 128000, 64000),
    LlmModel.V0_1_5_LG: ModelMetadata("v0", 512000, 64000),
    LlmModel.V0_1_0_MD: ModelMetadata("v0", 128000, 64000),
}

for model in LlmModel:
    if model not in MODEL_METADATA:
        raise ValueError(f"Missing MODEL_METADATA metadata for model: {model}")

