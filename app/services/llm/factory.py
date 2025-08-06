from app.core.config import settings
from app.services.llm.anthropic_service import AnthropicService
from app.services.llm.base import BaseLLMService
from app.services.llm.openai_service import OpenAIService


def get_llm_service() -> BaseLLMService:
    """Factory function to get the appropriate LLM service based on configuration."""
    if settings.LLM_PROVIDER == "openai":
        return OpenAIService()
    elif settings.LLM_PROVIDER == "anthropic":
        return AnthropicService()
    else:
        raise ValueError(f"Unknown LLM provider: {settings.LLM_PROVIDER}")