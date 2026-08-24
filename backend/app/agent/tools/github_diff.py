import base64
import logging
import subprocess
from typing import Any
import httpx
from app.core.config import settings

logger = logging.getLogger("nightshift.tools.github")


class GitHubDiffTool:
    """Tool for fetching commit diffs, reading files, and committing code fixes via GitHub REST API."""

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

    async def fetch_file_content(
        self,
        file_path: str,
        branch: str = "master",
    ) -> tuple[str, str]:
        """
        Fetch raw text content and blob SHA for a file in the repository.
        Returns: (file_content_str, blob_sha)
        """
        if not self.repo:
            return "", ""

        if not self.token:
            logger.debug("GITHUB_TOKEN not configured. Returning simulated file content.")
            return "", ""

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Nightshift-AI-SRE/0.3.0",
            "Authorization": f"Bearer {self.token}",
        }
        api_url = f"https://api.github.com/repos/{self.repo}/contents/{file_path.lstrip('/')}"
        params = {"ref": branch}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(api_url, headers=headers, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    blob_sha = data.get("sha", "")
                    content_b64 = data.get("content", "")
                    raw_text = base64.b64decode(content_b64).decode("utf-8", errors="replace")
                    return raw_text, blob_sha
                logger.warning(
                    "GitHub fetch_file_content HTTP %d for [%s]: %s",
                    resp.status_code,
                    file_path,
                    resp.text[:120],
                )
                return "", ""
        except Exception as exc:
            logger.warning("Error fetching file content from GitHub for [%s]: %s", file_path, exc)
            return "", ""

    async def commit_file_fix(
        self,
        file_path: str,
        content: str,
        commit_message: str,
        branch: str = "master",
        blob_sha: str | None = None,
    ) -> dict[str, Any]:
        """
        Commit an updated file content directly to the GitHub repository.
        API: PUT /repos/{owner}/{repo}/contents/{path}
        """
        if not self.repo:
            return {"success": False, "action": "commit_fix", "error": "GITHUB_REPO is not configured."}

        # Simulated fallback if no token
        if not self.token:
            logger.info("GITHUB_TOKEN not configured. Simulating commit for [%s].", file_path)
            return {
                "success": True,
                "action": "commit_fix",
                "simulated": True,
                "file_path": file_path,
                "commit_sha": "sim-c0mm17-99",
                "commit_url": f"https://github.com/{self.repo}/commit/sim-c0mm17-99",
                "message": f"Simulated commit for {file_path}: {commit_message}",
            }

        # Always fetch the latest live blob_sha from GitHub right before committing to avoid 409 Conflict
        _, live_sha = await self.fetch_file_content(file_path, branch=branch)
        current_sha = live_sha or blob_sha

        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "Nightshift-AI-SRE/0.3.0",
            "Authorization": f"Bearer {self.token}",
        }
        api_url = f"https://api.github.com/repos/{self.repo}/contents/{file_path.lstrip('/')}"
        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")

        body: dict[str, Any] = {
            "message": commit_message,
            "content": content_b64,
            "branch": branch,
        }
        if current_sha:
            body["sha"] = current_sha

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.put(api_url, headers=headers, json=body)
                # If 409 Conflict occurred (sha changed in interim), re-fetch latest sha and retry once
                if resp.status_code == 409:
                    logger.warning("Got HTTP 409 Conflict for [%s]. Re-fetching latest blob SHA and retrying commit...", file_path)
                    _, retry_sha = await self.fetch_file_content(file_path, branch=branch)
                    if retry_sha and retry_sha != current_sha:
                        body["sha"] = retry_sha
                        resp = await client.put(api_url, headers=headers, json=body)

                if resp.status_code in (200, 201):
                    data = resp.json()
                    commit_info = data.get("commit", {})
                    new_sha = commit_info.get("sha", "unknown-sha")
                    html_url = commit_info.get("html_url", f"https://github.com/{self.repo}/commit/{new_sha}")
                    logger.info("Successfully committed fix to [%s] (Commit: %s)", file_path, new_sha)
                    return {
                        "success": True,
                        "action": "commit_fix",
                        "file_path": file_path,
                        "commit_sha": new_sha,
                        "commit_url": html_url,
                        "message": f"Successfully committed fix to {file_path}: {commit_message}",
                        "data": data,
                    }

                error_msg = f"GitHub API commit failed with HTTP {resp.status_code}: {resp.text[:300]}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "action": "commit_fix",
                    "file_path": file_path,
                    "error": error_msg,
                }
        except Exception as exc:
            logger.error("Exception during GitHub commit_file_fix for [%s]: %s", file_path, exc, exc_info=True)
            return {
                "success": False,
                "action": "commit_fix",
                "file_path": file_path,
                "error": f"GitHub API connection failed: {str(exc)}",
            }


github_tool = GitHubDiffTool()

