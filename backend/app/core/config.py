from pydantic import BaseModel
import os


class Settings(BaseModel):
    """Application Settings."""

    app_name: str = "Nightshift AI SRE - Ingestion Engine"
    app_version: str = "0.1.0"
    api_prefix: str = ""
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))

    # CORS origins: allowing frontend dev server and permissive wildcards for local testing
    cors_origins: list[str] = [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*",
    ]


settings = Settings()
