from typing import Optional

from app.core.config import settings
from app.services.evaluator.base import BaseEvaluator
from app.services.evaluator.mock_evaluator import MockEvaluator
from app.services.evaluator.vllm_evaluator import VLLMEvaluator


def get_evaluator(provider_name: Optional[str] = None) -> BaseEvaluator:
    """
    Factory to retrieve the configured AI evaluation provider.
    Explicitly supports 'vllm' (local OpenAI-compatible VLLM server) and 'mock' (test/demo).
    Never silently falls back to mock findings.
    """
    name = (provider_name or settings.EVALUATOR_PROVIDER).lower().strip()

    if name == "mock":
        return MockEvaluator()

    if name in ["vllm", "local_vllm", "openai"]:
        return VLLMEvaluator(
            base_url=settings.VLLM_BASE_URL,
            model=settings.VLLM_MODEL,
            timeout=settings.VLLM_TIMEOUT_SECONDS,
            api_key=settings.VLLM_API_KEY,
            temperature=settings.VLLM_TEMPERATURE,
        )

    raise ValueError(
        f"Unsupported evaluator provider: '{name}'. "
        "Supported providers: ['vllm', 'mock']. Configure 'vllm' for real AI evaluation."
    )
