import logging
from typing import Any, Type, TypeVar
from pydantic import BaseModel
from app.agent.state import CorrelationOutput, ErrorSummaryOutput
from app.core.config import settings

logger = logging.getLogger("nightshift.llm")

T = TypeVar("T", bound=BaseModel)


class MockStructuredModel:
    """Deterministic Mock LLM for offline testing and development without API keys."""

    def __init__(self, schema: Type[T]) -> None:
        self.schema = schema

    async def ainvoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        prompt_str = str(prompt)
        logger.info("Invoking Mock LLM with structured output schema: %s", self.schema.__name__)

        if self.schema == ErrorSummaryOutput or self.schema.__name__ == "ErrorSummaryOutput":
            # Extract service and error hints from prompt text
            service = "unknown-service"
            for s in [
                "blohelp",
                "payment-gateway",
                "auth-service",
                "order-processor",
                "inventory-api",
                "notification-worker",
                "ingress-router",
            ]:
                if s in prompt_str:
                    service = s
                    break

            error_type = "SystemFailure"
            if "deadlock" in prompt_str.lower():
                error_type = "DatabaseDeadlock"
            elif "timeout" in prompt_str.lower():
                error_type = "GatewayTimeout"
            elif "unauthorized" in prompt_str.lower() or "signature" in prompt_str.lower():
                error_type = "AuthenticationError"
            elif "memory" in prompt_str.lower() or "oom" in prompt_str.lower():
                error_type = "OutOfMemoryException"
            elif "lock" in prompt_str.lower():
                error_type = "OptimisticLockException"

            return ErrorSummaryOutput(
                error_type=error_type,
                affected_service=service,
                likely_component=f"{service}-core-handler",
                summary=f"Critical {error_type} in {service} causing downstream failure.",
            )

        if self.schema == CorrelationOutput or self.schema.__name__ == "CorrelationOutput":
            return CorrelationOutput(
                hypothesis=(
                    "The incident was likely triggered by a recent commit altering database transaction boundaries, "
                    "leading to lock contention and service timeouts under concurrent load."
                ),
                confidence=0.88,
            )

        # Generic fallback
        return self.schema()


class MockChatModel:
    """Mock Chat Model satisfying LangChain ChatModel interface."""

    def with_structured_output(self, schema: Type[T], *args: Any, **kwargs: Any) -> Any:
        return MockStructuredModel(schema)


def get_llm() -> Any:
    """
    Factory function returning the configured LLM client.
    Supports Anthropic Claude, Google Gemini, and Mock provider.
    """
    provider = settings.llm_provider.lower()

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not set. Falling back to mock LLM.")
            return MockChatModel()
        try:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=settings.anthropic_model,
                api_key=settings.anthropic_api_key,
                temperature=0.1,
            )
        except Exception as exc:
            logger.error("Failed to initialize ChatAnthropic: %s. Using mock fallback.", exc)
            return MockChatModel()

    elif provider == "gemini":
        if not settings.gemini_api_key:
            logger.warning("GEMINI_API_KEY not set. Falling back to mock LLM.")
            return MockChatModel()
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI

            return ChatGoogleGenerativeAI(
                model=settings.gemini_model,
                google_api_key=settings.gemini_api_key,
                temperature=0.1,
            )
        except Exception as exc:
            logger.error("Failed to initialize ChatGoogleGenerativeAI: %s. Using mock fallback.", exc)
            return MockChatModel()

    return MockChatModel()
