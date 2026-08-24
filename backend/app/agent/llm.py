import logging
import re
from typing import Any, Type, TypeVar
from pydantic import BaseModel
from app.agent.state import CodeFixOutput, CorrelationOutput, ErrorSummaryOutput
from app.core.config import settings

logger = logging.getLogger("nightshift.llm")

T = TypeVar("T", bound=BaseModel)


class MockStructuredModel:
    """Deterministic Mock LLM for offline testing and development without API keys."""

    def __init__(self, schema: Type[T]) -> None:
        self.schema = schema

    async def ainvoke(self, prompt: Any, *args: Any, **kwargs: Any) -> Any:
        prompt_str = str(prompt)
        prompt_lower = prompt_str.lower()
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
                if s in prompt_lower:
                    service = s
                    break

            error_type = "SystemFailure"
            if "deadlock" in prompt_lower:
                error_type = "DatabaseDeadlock"
            elif "timeout" in prompt_lower:
                error_type = "GatewayTimeout"
            elif "unauthorized" in prompt_lower or "signature" in prompt_lower:
                error_type = "AuthenticationError"
            elif "memory" in prompt_lower or "oom" in prompt_lower:
                error_type = "OutOfMemoryException"
            elif "lock" in prompt_lower:
                error_type = "OptimisticLockException"

            return ErrorSummaryOutput(
                error_type=error_type,
                affected_service=service,
                likely_component=f"{service}-core-handler",
                summary=f"Critical {error_type} in {service} causing downstream failure.",
            )

        if self.schema == CorrelationOutput or self.schema.__name__ == "CorrelationOutput":
            deploy_status = "live"
            for status in ["update_failed", "build_failed", "deactivated", "canceled"]:
                if f"deploy status: {status}" in prompt_lower or f"render status: {status}" in prompt_lower:
                    deploy_status = status
                    break

            # Look specifically in user prompt for literal typo identifiers
            eval_text = prompt_lower
            if "### error diagnostic summary:" in prompt_lower:
                eval_text = prompt_lower.split("### error diagnostic summary:")[1]

            has_typo_or_fixable_bug = any(
                keyword in eval_text
                for keyword in ["mngo_uri", "mongo_uri", "mongo_urii", "wrong uri"]
            )

            if has_typo_or_fixable_bug:
                status_note = (
                    f" Render deploy status is '{deploy_status}' (broken deployment)."
                    if deploy_status != "live"
                    else ""
                )
                return CorrelationOutput(
                    hypothesis=(
                        "The diff reveals a literal defect/typo in the code: "
                        "'- MONGO_URI' was replaced with '+ MNGO_URI'."
                        f"{status_note} An automated Code Fix commit to GitHub is recommended to restore deployment."
                    ),
                    confidence=0.95,
                )

            if deploy_status != "live":
                return CorrelationOutput(
                    hypothesis=(
                        f"The git diff contains changes, but Render deploy status is '{deploy_status}'. "
                        f"Note: This commit failed to deploy (Render status: {deploy_status}) and is not live in production. "
                        "No rollback or restart of the live container is needed for non-deployed code."
                    ),
                    confidence=0.30,
                )

            # Default generic regression hypothesis quoting the suspect commit
            return CorrelationOutput(
                hypothesis=(
                    "The diff introduces changes to core request handling in the suspect commit. "
                    "Diff line: '+ async def handle_request(...)' leading to unexpected downstream timeouts."
                ),
                confidence=0.88,
            )

        if self.schema == CodeFixOutput or self.schema.__name__ == "CodeFixOutput":
            file_path = "server/server.js"
            path_match = re.search(r"target file path:\s*([^\s\n\r\(\)]+)", prompt_lower)
            if path_match:
                candidate = path_match.group(1).strip()
                if candidate and candidate.endswith((".js", ".ts", ".py", ".json", ".env")):
                    file_path = candidate

            code_patch = (
                f"--- a/{file_path}\n"
                f"+++ b/{file_path}\n"
                "@@ -15,3 +15,3 @@\n"
                "-mongoose.connect(process.env.MONGO_URII)\n"
                "+mongoose.connect(process.env.MONGO_URI)"
            )
            updated_content = (
                "require('dotenv').config();\n"
                "const express = require('express');\n"
                "const mongoose = require('mongoose');\n"
                "const cors = require('cors');\n\n"
                "const app = express();\n"
                "app.use(cors());\n"
                "app.use(express.json());\n\n"
                "app.use('/api/voters', require('./routes/voters'));\n"
                "app.get('/health', (_, res) => res.json({ status: 'ok' }));\n\n"
                "mongoose.connect(process.env.MONGO_URI)\n"
                "  .then(() => console.log('MongoDB connected successfully'))\n"
                "  .catch((err) => console.error('MongoDB connection error:', err));\n\n"
                "const PORT = process.env.PORT || 5000;\n"
                "app.listen(PORT, () => console.log(`Server running on port ${PORT}`));\n"
            )

            return CodeFixOutput(
                is_fixable=True,
                file_path=file_path,
                code_patch=code_patch,
                updated_file_content=updated_content,
                commit_message="fix(server): correct MONGO_URII typo to MONGO_URI in database connection",
                explanation="Fixes the typo in environment variable reference from MONGO_URII to MONGO_URI so mongoose connects successfully.",
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
