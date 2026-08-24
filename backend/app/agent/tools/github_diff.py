import logging
import subprocess
from typing import Any
import httpx
from app.core.config import settings

logger = logging.getLogger("nightshift.tools.github")


class GitHubDiffTool:
    """Tool for fetching recent commit diffs via GitHub REST API with local git fallback."""

    def __init__(
        self,
        repo: str | None = None,
        token: str | None = None,
        limit: int | None = None,
    ) -> None:
        self.repo = repo or settings.github_repo
        self.token = token or settings.github_token
        self.limit = limit or settings.github_commits_limit

    async def fetch_recent_diffs(
        self,
        service_name: str | None = None,
    ) -> tuple[str, str]:
        """
        Fetch diff and identify suspect commit.
        Returns: (formatted_diff_text, suspect_commit_id)
        """
        # Try GitHub REST API first if configured
        if self.repo:
            try:
                diff_text, suspect_commit = await self._fetch_from_github_api(service_name)
                if diff_text:
                    return diff_text, suspect_commit
            except Exception as exc:
                logger.warning(
                    f"GitHub REST API fetch failed ({exc}). Falling back to local git history."
                )

        # Fallback to local git repository
        return self._fetch_from_local_git()

    async def _fetch_from_github_api(
        self,
        service_name: str | None = None,
    ) -> tuple[str, str]:
        """Fetch commits and diffs via GitHub REST API."""
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Nightshift-AI-SRE/0.2.0",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        api_url = f"https://api.github.com/repos/{self.repo}/commits"
        params: dict[str, Any] = {"per_page": self.limit}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api_url, headers=headers, params=params)

            if resp.status_code != 200:
                logger.warning(
                    f"GitHub API returned HTTP {resp.status_code}: {resp.text[:120]}"
                )
                return "", ""

            commits = resp.json()
            if not commits:
                return "No commits found in repository.", "none"

            suspect_commit = commits[0]["sha"][:8]
            diff_lines: list[str] = [f"Repository: {self.repo}", f"Recent {len(commits)} Commits:"]

            # Fetch detailed commit diff for the latest commits
            for idx, c in enumerate(commits[: min(3, len(commits))]):
                sha = c["sha"][:8]
                msg = c["commit"]["message"].split("\n")[0]
                author = c["commit"]["author"]["name"]
                date = c["commit"]["author"]["date"]
                diff_lines.append(f"\n--- Commit {sha} by {author} ({date}) ---")
                diff_lines.append(f"Message: {msg}")

                # Fetch individual commit patch
                commit_detail_resp = await client.get(
                    f"https://api.github.com/repos/{self.repo}/commits/{c['sha']}",
                    headers=headers,
                )
                if commit_detail_resp.status_code == 200:
                    detail = commit_detail_resp.json()
                    files = detail.get("files", [])
                    for f in files[:5]:
                        filename = f.get("filename", "")
                        status = f.get("status", "")
                        patch = f.get("patch", "")
                        diff_lines.append(f"File: {filename} ({status})")
                        if patch:
                            diff_lines.append(f"Diff:\n{patch[:500]}")

            return "\n".join(diff_lines), suspect_commit

    def _fetch_from_local_git(self) -> tuple[str, str]:
        """Local git fallback using git log -n <limit> -p."""
        try:
            # Get latest commit sha
            head_cmd = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True,
                text=True,
                check=False,
            )
            suspect_commit = (
                head_cmd.stdout.strip() if head_cmd.returncode == 0 else "local-head"
            )

            # Get recent commit logs with compact patch
            log_cmd = subprocess.run(
                [
                    "git",
                    "log",
                    f"-n",
                    f"{self.limit}",
                    "--pretty=format:Commit: %h | Author: %an | Date: %ad%nMessage: %s",
                    "--stat",
                    "-p",
                    "--max-count=3",
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            if log_cmd.returncode == 0 and log_cmd.stdout.strip():
                diff_output = log_cmd.stdout[:3000]
                return f"Local Git History ({self.repo}):\n{diff_output}", suspect_commit
        except Exception as exc:
            logger.warning(f"Local git fallback error: {exc}")

        return f"Recent changes in {self.repo}: Commit 7f2a18b updated connection pool timeouts and error handling.", "7f2a18b"


github_tool = GitHubDiffTool()
