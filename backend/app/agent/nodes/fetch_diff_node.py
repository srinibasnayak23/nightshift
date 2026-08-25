import logging
from app.agent.state import IncidentState
from app.agent.tools.github_diff import github_tool
from app.agent.tools.render_tool import render_tool
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.agent.fetch_diff")


async def fetch_diff_node(state: IncidentState) -> dict:
    """
    Tool call: Fetches recent commit history and diffs from GitHub REST API (or local git),
    pinpoints suspect commits, and queries Render for the suspect commit's deploy status.
    """
    error_summary = state.get("error_summary", "")

    await thought_manager.broadcast_thought(
        node="fetch_diff_node",
        status="started",
        thought=f"Querying repository [{github_tool.repo}] for recent commits and diffs...",
    )

    try:
        git_diff, suspect_commit = await github_tool.fetch_recent_diffs()
    except Exception as exc:
        logger.error(f"Failed to fetch git diff: {exc}")
        git_diff = "Unable to retrieve git diff."
        suspect_commit = "unknown"

    # Query Render deploy status for the suspect commit
    deploy_status = None
    try:
        deploy_status = await render_tool.get_deploy_status_for_commit(suspect_commit)
    except Exception as exc:
        logger.warning("Failed to retrieve Render deploy status: %s", exc)
        deploy_status = "unknown"

    deploy_status_label = deploy_status or "unknown"
    thought_msg = (
        f"Fetched commit history from {github_tool.repo}. "
        f"Suspect commit identified: [{suspect_commit}] (Deploy status on Render: [{deploy_status_label}])."
    )

    await thought_manager.broadcast_thought(
        node="fetch_diff_node",
        status="completed",
        thought=thought_msg,
        state_updates={
            "git_diff": git_diff,
            "suspect_commit": suspect_commit,
            "suspect_commit_deploy_status": deploy_status,
        },
    )

    return {
        "git_diff": git_diff,
        "suspect_commit": suspect_commit,
        "suspect_commit_deploy_status": deploy_status,
    }

