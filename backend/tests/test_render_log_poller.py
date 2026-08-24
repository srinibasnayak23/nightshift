import asyncio
from unittest.mock import AsyncMock, patch
import httpx
import pytest
from app.models.log import LogLevel, LogPayload
from app.services.render_log_poller import RenderLogPoller, clean_ansi


def test_clean_ansi() -> None:
    """Test stripping of ANSI terminal escape codes."""
    raw = "\x1b[34m\x1b[1m==>\x1b(B\x1b[m \x1b[1mDownloading cache...\x1b(B\x1b[m"
    assert clean_ansi(raw) == "==> Downloading cache..."

    color_msg = "\x1b[0;32m\x1b[1m==> \x1b[0m\x1b[1mYour service is live 🎉\x1b[0m"
    assert clean_ansi(color_msg) == "==> Your service is live 🎉"

    assert clean_ansi("") == ""
    assert clean_ansi("Normal plain text message") == "Normal plain text message"


def test_extract_log_level() -> None:
    """Test log level extraction from Render labels and fallback message inspection."""
    poller = RenderLogPoller(service_name="BloHelp")

    # From explicit level label
    labels_err = [{"name": "level", "value": "error"}, {"name": "type", "value": "app"}]
    assert poller._extract_log_level(labels_err, "Sample log") == LogLevel.ERROR

    labels_warn = [{"name": "level", "value": "warning"}]
    assert poller._extract_log_level(labels_warn, "Sample log") == LogLevel.WARN

    labels_debug = [{"name": "level", "value": "debug"}]
    assert poller._extract_log_level(labels_debug, "Sample log") == LogLevel.INFO

    # Fallback to message keyword when no label present
    assert poller._extract_log_level([], "MongoServerError: Authentication failed") == LogLevel.ERROR
    assert poller._extract_log_level([], "Warning: Deprecated API usage") == LogLevel.WARN
    assert poller._extract_log_level([], "Server running on port 5000") == LogLevel.INFO


def test_mark_seen_deduplication() -> None:
    """Test deduplication cache and LRU eviction."""
    poller = RenderLogPoller(max_seen_ids=3)

    assert poller._mark_seen("id-1") is True
    assert poller._mark_seen("id-1") is False  # Duplicate

    assert poller._mark_seen("id-2") is True
    assert poller._mark_seen("id-3") is True
    assert poller._mark_seen("id-4") is True  # Evicts id-1

    # id-1 was evicted, so it can be seen again if max_seen_ids was small
    assert "id-1" not in poller._seen_log_ids
    assert "id-2" in poller._seen_log_ids
    assert "id-3" in poller._seen_log_ids
    assert "id-4" in poller._seen_log_ids


def test_parse_render_log() -> None:
    """Test parsing a raw Render log entry into a LogPayload."""
    poller = RenderLogPoller(service_name="BloHelp")

    entry = {
        "id": "log-abc-123",
        "timestamp": "2026-08-24T12:00:00.000Z",
        "labels": [
            {"name": "level", "value": "error"},
            {"name": "instance", "value": "srv-inst-1"},
        ],
        "message": "\x1b[31mFailed to connect to MongoDB\x1b[0m",
    }

    payload = poller.parse_render_log(entry)
    assert payload is not None
    assert payload.service == "BloHelp"
    assert payload.level == LogLevel.ERROR
    assert payload.message == "Failed to connect to MongoDB"
    assert payload.timestamp == "2026-08-24T12:00:00.000Z"

    # Empty message should return None
    empty_entry = {"id": "log-empty", "message": "\x1b[m   \x1b[0m"}
    assert poller.parse_render_log(empty_entry) is None


@pytest.mark.asyncio
async def test_poll_once_success() -> None:
    """Test poll_once fetching logs and feeding into ingest_log."""
    poller = RenderLogPoller(
        api_key="mock-key",
        owner_id="tea-mock-owner",
        service_id="srv-mock-service",
        service_name="BloHelp",
    )

    mock_response_data = {
        "hasMore": False,
        "nextStartTime": "2026-08-24T12:00:05.000Z",
        "logs": [
            {
                "id": "log-1",
                "timestamp": "2026-08-24T12:00:01.000Z",
                "labels": [{"name": "level", "value": "info"}],
                "message": "Server started on port 5000",
            },
            {
                "id": "log-2",
                "timestamp": "2026-08-24T12:00:02.000Z",
                "labels": [{"name": "level", "value": "error"}],
                "message": "Connection to database failed: ECONNREFUSED",
            },
        ],
    }

    with patch("app.services.render_log_poller.process_and_ingest_log", new_callable=AsyncMock) as mock_ingest:
        with patch.object(poller, "fetch_logs", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_response_data

            count = await poller.poll_once()

            assert count == 2
            assert mock_ingest.call_count == 2
            first_call_payload = mock_ingest.call_args_list[0][0][0]
            assert isinstance(first_call_payload, LogPayload)
            assert first_call_payload.service == "BloHelp"
            assert first_call_payload.level == LogLevel.INFO
            assert first_call_payload.message == "Server started on port 5000"

            second_call_payload = mock_ingest.call_args_list[1][0][0]
            assert second_call_payload.level == LogLevel.ERROR
            assert second_call_payload.message == "Connection to database failed: ECONNREFUSED"

            # Check deduplication on second poll
            count_second = await poller.poll_once()
            assert count_second == 0  # Already seen log-1 and log-2


@pytest.mark.asyncio
async def test_poll_once_pagination() -> None:
    """Test pagination across multiple pages when hasMore is True."""
    poller = RenderLogPoller(
        api_key="mock-key",
        owner_id="tea-mock-owner",
        service_id="srv-mock-service",
        service_name="BloHelp",
    )

    page1 = {
        "hasMore": True,
        "nextStartTime": "2026-08-24T12:00:02.000Z",
        "logs": [
            {
                "id": "page1-log1",
                "timestamp": "2026-08-24T12:00:01.000Z",
                "labels": [{"name": "level", "value": "info"}],
                "message": "Page 1 message",
            }
        ],
    }
    page2 = {
        "hasMore": False,
        "nextStartTime": "2026-08-24T12:00:03.000Z",
        "logs": [
            {
                "id": "page2-log1",
                "timestamp": "2026-08-24T12:00:02.500Z",
                "labels": [{"name": "level", "value": "warn"}],
                "message": "Page 2 message",
            }
        ],
    }

    with patch("app.services.render_log_poller.process_and_ingest_log", new_callable=AsyncMock) as mock_ingest:
        with patch.object(poller, "fetch_logs", new_callable=AsyncMock, side_effect=[page1, page2]):
            count = await poller.poll_once()
            assert count == 2
            assert mock_ingest.call_count == 2
            assert poller._last_seen_time == "2026-08-24T12:00:03.000Z"


@pytest.mark.asyncio
async def test_poller_start_and_stop_lifecycle() -> None:
    """Test clean startup and shutdown of poller task."""
    poller = RenderLogPoller(
        api_key="mock-key",
        owner_id="tea-mock-owner",
        service_id="srv-mock-service",
        interval_seconds=0.1,
    )

    with patch.object(poller, "poll_once", new_callable=AsyncMock) as mock_poll:
        await poller.start()
        assert poller._running is True
        assert poller._task is not None

        # Give loop a brief moment to run
        await asyncio.sleep(0.15)
        assert mock_poll.call_count >= 1

        await poller.stop()
        assert poller._running is False
        assert poller._task is None
