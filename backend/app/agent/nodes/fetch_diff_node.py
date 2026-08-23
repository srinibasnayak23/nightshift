import logging
from app.agent.state import IncidentState
from app.agent.tools.github_diff import github_tool
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.agent.fetch_diff")


async def fetch_diff_node(state: IncidentState) -> dict:
    """
    Tool call: Fetches recent commit history and diffs from GitHub REST API (or local git),
    pinpointing suspect commits.
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

    thought_msg = (
        f"Fetched commit history from {github_tool.repo}. "
        f"Suspect commit identified: [{suspect_commit}]."
    )

    await thought_manager.broadcast_thought(
        node="fetch_diff_node",
        status="completed",
        thought=thought_msg,
        state_updates={
            "git_diff": git_diff,
            "suspect_commit": suspect_commit,
        },
    )

    return {
        "git_diff": git_diff,
        "suspect_commit": suspect_commit,
    }
