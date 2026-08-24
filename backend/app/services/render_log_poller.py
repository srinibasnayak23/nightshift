import asyncio
from collections import deque
from datetime import datetime, timezone
import logging
import re
from typing import Any
import httpx
from app.core.config import settings
from app.models.log import LogLevel, LogPayload
from app.services.log_service import process_and_ingest_log

logger = logging.getLogger("nightshift.services.render_log_poller")

# Regex to strip ANSI/VT100 escape sequences (colors, formatting, character set shifts)
ANSI_ESCAPE_RE = re.compile(
    r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\([A-Za-z0-9]|\)[A-Za-z0-9])"
)

# Fallback error detection keywords if level label is missing
ERROR_KEYWORDS = (
    "error",
    "fatal",
    "critical",
    "exception",
    "panic",
    "traceback",
    "unhandled",
    "syntaxerror",
    "typeerror",
    "connection refused",
)
WARN_KEYWORDS = ("warn", "warning", "deprecated", "timeout", "timed out")


def clean_ansi(text: str) -> str:
    """Remove ANSI escape codes from string and strip trailing whitespace."""
    if not text:
        return ""
    cleaned = ANSI_ESCAPE_RE.sub("", text)
    return cleaned.strip()


class RenderLogPoller:
    """
    Background worker service that periodically queries the Render Logs API
    (GET /v1/logs) for BloHelp's runtime logs, normalizes each entry,
    and feeds it in-process to the Nightshift log ingestion pipeline.
    """

    def __init__(
        self,
        api_key: str | None = None,
        owner_id: str | None = None,
        service_id: str | None = None,
        base_url: str | None = None,
        interval_seconds: float | None = None,
        service_name: str | None = None,
        max_seen_ids: int = 5000,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.render_api_key
        self.owner_id = owner_id if owner_id is not None else settings.render_owner_id
        self.service_id = (
            service_id if service_id is not None else settings.render_target_service_id
        )
        self.base_url = (base_url or settings.render_base_url).rstrip("/")
        self.interval = (
            interval_seconds
            if interval_seconds is not None
            else settings.render_poll_interval_seconds
        )
        self.service_name = (
            service_name if service_name is not None else settings.render_service_name
        )

        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._last_seen_time: str | None = None
        self._max_seen_ids = max_seen_ids
        self._seen_log_ids: set[str] = set()
        self._seen_ids_queue: deque[str] = deque()

    @property
    def is_configured(self) -> bool:
        """Check if all required configuration parameters are present."""
        return bool(self.api_key and self.owner_id and self.service_id)

    def _mark_seen(self, log_id: str) -> bool:
        """
        Record log entry ID in deduplication cache.
        Returns True if newly seen, False if duplicate.
        """
        if not log_id:
            return True
        if log_id in self._seen_log_ids:
            return False

        self._seen_log_ids.add(log_id)
        self._seen_ids_queue.append(log_id)

        # Evict oldest IDs to maintain bounded memory
        while len(self._seen_ids_queue) > self._max_seen_ids:
            oldest = self._seen_ids_queue.popleft()
            self._seen_log_ids.discard(oldest)

        return True

    def _extract_log_level(self, labels: list[dict[str, Any]], message: str) -> LogLevel:
        """Extract and normalize log level from Render labels or message contents."""
        for label in labels:
            if isinstance(label, dict) and label.get("name") == "level":
                val = str(label.get("value", "")).strip().lower()
                if val in ("error", "err", "fatal", "critical"):
                    return LogLevel.ERROR
                if val in ("warn", "warning"):
                    return LogLevel.WARN
                if val in ("info", "debug", "trace", "notice", "verbose"):
                    return LogLevel.INFO

        # Fallback inspection of message text
        msg_lower = message.lower()
        if any(kw in msg_lower for kw in ERROR_KEYWORDS):
            return LogLevel.ERROR
        if any(kw in msg_lower for kw in WARN_KEYWORDS):
            return LogLevel.WARN

        return LogLevel.INFO

    def parse_render_log(self, entry: dict[str, Any]) -> LogPayload | None:
        """
        Transform a single Render log entry dict into a validated LogPayload.
        Returns None if the entry is empty or invalid.
        """
        raw_message = str(entry.get("message", ""))
        clean_msg = clean_ansi(raw_message)
        if not clean_msg:
            return None

        raw_timestamp = entry.get("timestamp")
        timestamp_str = (
            str(raw_timestamp).strip()
            if raw_timestamp
            else datetime.now(timezone.utc).isoformat()
        )

        labels = entry.get("labels") or []
        level = self._extract_log_level(labels, clean_msg)

        try:
            return LogPayload(
                timestamp=timestamp_str,
                service=self.service_name,
                level=level,
                message=clean_msg,
            )
        except Exception as exc:
            logger.warning("Failed to validate parsed LogPayload from Render: %s", exc)
            return None

    async def fetch_logs(
        self, client: httpx.AsyncClient, start_time: str | None = None
    ) -> dict[str, Any]:
        """Query GET /v1/logs from Render API."""
        endpoint = f"{self.base_url}/logs"
        params: dict[str, Any] = {
            "ownerId": self.owner_id,
            "resource": [self.service_id],
            "direction": "forward",
            "limit": 100,
        }
        if start_time:
            params["startTime"] = start_time

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": "Nightshift-AI-SRE/0.2.0 (RenderPoller)",
        }

        response = await client.get(endpoint, params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    async def poll_once(self, client: httpx.AsyncClient | None = None) -> int:
        """
        Execute a single poll cycle against Render API and forward new logs to ingestion.
        Returns number of newly ingested logs.
        """
        if not self.is_configured:
            logger.debug("RenderLogPoller skipped: credentials or service ID missing.")
            return 0

        # On very first poll, initialize start_time to current UTC time if not set
        if not self._last_seen_time:
            self._last_seen_time = datetime.now(timezone.utc).isoformat()

        should_close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=15.0)
            should_close_client = True

        ingested_count = 0
        current_start_time = self._last_seen_time
        max_pages = 5  # Guard against unbounded loops in high-traffic spikes

        try:
            page = 0
            while page < max_pages:
                page += 1
                data = await self.fetch_logs(client, start_time=current_start_time)
                logs_list = data.get("logs") or []
                has_more = bool(data.get("hasMore", False))
                next_start_time = data.get("nextStartTime")

                for entry in logs_list:
                    log_id = str(entry.get("id", ""))
                    if log_id and not self._mark_seen(log_id):
                        # Duplicate entry already processed
                        continue

                    payload = self.parse_render_log(entry)
                    if payload:
                        # Feed in-process directly to Nightshift ingestion pipeline
                        await process_and_ingest_log(payload)
                        ingested_count += 1

                if next_start_time:
                    self._last_seen_time = next_start_time
                    current_start_time = next_start_time

                if not has_more or not next_start_time or not logs_list:
                    break

            if ingested_count > 0:
                logger.info(
                    "Polled Render: Ingested %d new logs for [%s]. Next start: %s",
                    ingested_count,
                    self.service_name,
                    self._last_seen_time,
                )

            return ingested_count

        finally:
            if should_close_client:
                await client.aclose()

    async def _poll_loop(self) -> None:
        """Continuous polling background loop."""
        logger.info(
            "Render log poller started for service [%s] (%s). Polling every %.1fs.",
            self.service_name,
            self.service_id,
            self.interval,
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            while self._running:
                try:
                    await self.poll_once(client=client)
                except asyncio.CancelledError:
                    logger.info("Render log poller loop cancelled.")
                    break
                except httpx.HTTPStatusError as http_err:
                    logger.warning(
                        "Render Logs API HTTP %d error: %s. Will retry in %.1fs.",
                        http_err.response.status_code,
                        http_err.response.text[:200],
                        self.interval,
                    )
                except httpx.RequestError as req_err:
                    logger.warning(
                        "Render Logs API network error (%s). Will retry in %.1fs.",
                        req_err,
                        self.interval,
                    )
                except Exception as exc:
                    logger.error(
                        "Unexpected error in Render log poller: %s. Will retry in %.1fs.",
                        exc,
                        self.interval,
                        exc_info=True,
                    )

                try:
                    await asyncio.sleep(self.interval)
                except asyncio.CancelledError:
                    break

        logger.info("Render log poller background loop terminated.")

    async def start(self) -> None:
        """Start the background log polling task."""
        if self._running:
            logger.warning("RenderLogPoller is already running.")
            return

        if not settings.render_poller_enabled:
            logger.info("RenderLogPoller is disabled via RENDER_POLLER_ENABLED.")
            return

        if not self.is_configured:
            logger.warning(
                "RenderLogPoller disabled: missing RENDER_API_KEY, RENDER_OWNER_ID, or RENDER_TARGET_SERVICE_ID."
            )
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the background log polling task cleanly."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("RenderLogPoller stopped cleanly.")


# Global singleton instance
render_log_poller = RenderLogPoller()
