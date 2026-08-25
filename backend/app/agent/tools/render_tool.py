import json
import logging
from typing import Any
import httpx
from app.core.config import settings

logger = logging.getLogger("nightshift.tools.render")


class RenderTool:
    """MCP-style tool for automated remediation actions on Render services."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_service_id: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.render_api_key
        self.base_url = (base_url or settings.render_base_url).rstrip("/")
        self.default_service_id = (
            default_service_id if default_service_id is not None else settings.render_target_service_id
        )

    def _get_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Nightshift-AI-SRE/0.3.0",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def restart_service(self, service_id: str | None = None) -> dict[str, Any]:
        """
        Trigger a rolling restart for a Render service.
        API: POST /v1/services/{serviceId}/restart
        """
        target_id = service_id or self.default_service_id
        if not target_id:
            logger.error("Render restart failed: service_id not provided and RENDER_TARGET_SERVICE_ID not set.")
            return {
                "success": False,
                "action": "restart",
                "error": "Missing service_id (RENDER_TARGET_SERVICE_ID is not configured).",
            }

        # Simulated fallback if no API key is provided
        if not self.api_key:
            logger.warning(
                "RENDER_API_KEY is not configured. Simulating service restart for service [%s].",
                target_id,
            )
            return {
                "success": True,
                "action": "restart",
                "simulated": True,
                "service_id": target_id,
                "message": f"Simulated restart triggered for service {target_id} (BloHelp).",
            }

        endpoint = f"{self.base_url}/services/{target_id}/restart"
        logger.info("Executing Render API restart request to: %s", endpoint)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(endpoint, headers=self._get_headers(), json={})

                if response.status_code in (200, 201, 202, 204):
                    logger.info("Render service [%s] restart accepted successfully.", target_id)
                    data = response.json() if response.text else {}
                    return {
                        "success": True,
                        "action": "restart",
                        "service_id": target_id,
                        "status_code": response.status_code,
                        "data": data,
                        "message": f"Successfully triggered restart for service {target_id}.",
                    }

                error_msg = (
                    f"Render API restart failed with HTTP {response.status_code}: {response.text[:300]}"
                )
                logger.error(error_msg)
                return {
                    "success": False,
                    "action": "restart",
                    "service_id": target_id,
                    "status_code": response.status_code,
                    "error": error_msg,
                }

        except Exception as exc:
            logger.error("Exception occurred during Render restart API call: %s", exc, exc_info=True)
            return {
                "success": False,
                "action": "restart",
                "service_id": target_id,
                "error": f"Render API connection failed: {str(exc)}",
            }

    async def rollback_deployment(
        self, service_id: str | None = None, commit_id: str | None = None
    ) -> dict[str, Any]:
        """
        Deploy / Rollback to a specific commit SHA on a Render service.
        API: POST /v1/services/{serviceId}/deploys
        """
        target_id = service_id or self.default_service_id
        if not target_id:
            logger.error("Render rollback failed: service_id not provided and RENDER_TARGET_SERVICE_ID not set.")
            return {
                "success": False,
                "action": "rollback",
                "error": "Missing service_id (RENDER_TARGET_SERVICE_ID is not configured).",
            }

        # Simulated fallback if no API key is provided
        if not self.api_key:
            logger.warning(
                "RENDER_API_KEY is not configured. Simulating service rollback for service [%s] commit [%s].",
                target_id,
                commit_id,
            )
            return {
                "success": True,
                "action": "rollback",
                "simulated": True,
                "service_id": target_id,
                "commit_id": commit_id or "previous-healthy-commit",
                "deploy_id": "dep-mock-simulated-99",
                "message": f"Simulated rollback to commit {commit_id} triggered for service {target_id}.",
            }

        endpoint = f"{self.base_url}/services/{target_id}/deploys"
        payload: dict[str, Any] = {"clearCache": "do_not_clear"}
        if commit_id and commit_id not in ("unknown", "none"):
            payload["commitId"] = commit_id

        logger.info("Executing Render API rollback deploy to [%s] with payload: %s", endpoint, payload)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(endpoint, headers=self._get_headers(), json=payload)

                if response.status_code in (200, 201, 202):
                    data = response.json() if response.text else {}
                    deploy_id = data.get("id", "unknown-deploy-id")
                    logger.info(
                        "Render deploy/rollback created for service [%s]. Deploy ID: [%s]",
                        target_id,
                        deploy_id,
                    )
                    return {
                        "success": True,
                        "action": "rollback",
                        "service_id": target_id,
                        "commit_id": commit_id,
                        "deploy_id": deploy_id,
                        "status_code": response.status_code,
                        "data": data,
                        "message": f"Successfully triggered rollback deploy [{deploy_id}] to commit {commit_id}.",
                    }

                error_msg = (
                    f"Render API rollback failed with HTTP {response.status_code}: {response.text[:300]}"
                )
                logger.error(error_msg)
                return {
                    "success": False,
                    "action": "rollback",
                    "service_id": target_id,
                    "commit_id": commit_id,
                    "status_code": response.status_code,
                    "error": error_msg,
                }

        except Exception as exc:
            logger.error("Exception occurred during Render rollback API call: %s", exc, exc_info=True)
            return {
                "success": False,
                "action": "rollback",
                "service_id": target_id,
                "commit_id": commit_id,
                "error": f"Render API connection failed: {str(exc)}",
            }

    async def get_deploy_status_for_commit(
        self, commit_sha: str | None = None, service_id: str | None = None
    ) -> str | None:
        """
        Query Render API GET /v1/services/{serviceId}/deploys to retrieve the deployment
        status for a given commit SHA (e.g., 'live', 'update_failed', 'build_failed', 'deactivated').
        """
        target_id = service_id or self.default_service_id
        if not target_id:
            logger.debug("Render deploy status skipped: service_id not configured.")
            return None

        if not self.api_key:
            logger.debug("RENDER_API_KEY not configured. Returning simulated deploy status 'live'.")
            return "live"

        endpoint = f"{self.base_url}/services/{target_id}/deploys"
        params = {"limit": 10}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(endpoint, headers=self._get_headers(), params=params)
                if response.status_code == 200:
                    deploys = response.json()
                    if not deploys:
                        return None

                    if not commit_sha or commit_sha.lower() in ("unknown", "none", ""):
                        first_deploy = deploys[0].get("deploy", {})
                        return first_deploy.get("status")

                    clean_sha = commit_sha.strip().lower()
                    for item in deploys:
                        deploy_obj = item.get("deploy", {})
                        commit_obj = deploy_obj.get("commit", {})
                        deploy_commit_id = str(commit_obj.get("id", "")).lower()
                        if (
                            deploy_commit_id.startswith(clean_sha)
                            or clean_sha.startswith(deploy_commit_id[:7])
                            or clean_sha == deploy_commit_id
                        ):
                            status = deploy_obj.get("status")
                            logger.info(
                                "Found Render deploy status [%s] for commit [%s] (Deploy ID: %s)",
                                status,
                                commit_sha,
                                deploy_obj.get("id"),
                            )
                            return status

                    # Fallback to latest deploy status if specific commit not found in recent history
                    latest_deploy = deploys[0].get("deploy", {})
                    latest_status = latest_deploy.get("status")
                    logger.info(
                        "Commit [%s] not in recent 10 deploys. Latest deploy status: [%s]",
                        commit_sha,
                        latest_status,
                    )
                    return latest_status

                logger.warning(
                    "Render deploys API returned HTTP %d: %s",
                    response.status_code,
                    response.text[:200],
                )
                return None
        except Exception as exc:
            logger.warning("Failed to query Render deploy status for commit [%s]: %s", commit_sha, exc)
            return None


render_tool = RenderTool()

