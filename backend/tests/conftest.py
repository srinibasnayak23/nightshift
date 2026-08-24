import pytest
from fastapi.testclient import TestClient
from app.core.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def mock_llm_provider_for_tests() -> None:
    """Ensure tests run deterministically with mock LLM provider."""
    original_provider = settings.llm_provider
    settings.llm_provider = "mock"
    yield
    settings.llm_provider = original_provider


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    with TestClient(app) as test_client:
        yield test_client
