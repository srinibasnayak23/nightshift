import os
from dotenv import load_dotenv
from pydantic import BaseModel

# Load environment variables from .env file if present
load_dotenv()


class Settings(BaseModel):
    """Application Settings."""

    app_name: str = "Nightshift AI SRE - Reasoning Engine"
    app_version: str = "0.2.0"
    api_prefix: str = ""
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # CORS origins
    cors_origins: list[str] = [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*",
    ]

    # LLM Settings
    # Supports 'anthropic', 'gemini', or 'mock'
    llm_provider: str = os.getenv("LLM_PROVIDER", "").lower() or (
        "anthropic"
        if os.getenv("ANTHROPIC_API_KEY")
        else ("gemini" if os.getenv("GEMINI_API_KEY") else "mock")
    )
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # GitHub Tools Settings
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    github_repo: str = os.getenv("GITHUB_REPO", "srinibasnayak23/BloHelp")
    github_commits_limit: int = int(os.getenv("GITHUB_COMMITS_LIMIT", "5"))

    # Confidence Threshold for Escalation
    confidence_threshold: float = float(os.getenv("CONFIDENCE_THRESHOLD", "0.7"))

    # Render API Settings (for automated remediation)
    render_api_key: str = os.getenv("RENDER_API_KEY", "")
    render_target_service_id: str = os.getenv("RENDER_TARGET_SERVICE_ID", "")
    render_base_url: str = os.getenv("RENDER_BASE_URL", "https://api.render.com/v1")


settings = Settings()
