import logging
import re
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from app.agent.llm import get_llm
from app.agent.state import CodeFixOutput, IncidentState
from app.agent.tools.github_diff import github_tool
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.agent.generate_fix")


def extract_target_file_path(git_diff: str, error_summary: str, hypothesis: str) -> str:
    """Extract candidate file path from git diff, error summary, or hypothesis."""
    # Look for 'File: <path>' from git_diff parser
    diff_file_match = re.search(r"File:\s*([^\s\(\)]+)", git_diff)
    if diff_file_match:
        return diff_file_match.group(1).strip()

    # Look for common paths like server/server.js, src/..., etc.
    combined = f"{error_summary} {hypothesis} {git_diff}"
    path_match = re.search(r"([a-zA-Z0-9_\-\./]+\.(?:js|ts|py|json|env|yaml|yml))", combined)
    if path_match:
        return path_match.group(1).strip()

    # Default fallback for BloHelp repository
    return "server/server.js"


async def generate_fix_node(state: IncidentState) -> dict[str, Any]:
    """
    LLM call: Analyzes the root-cause hypothesis, error diagnostics, and source file
    to generate a minimal, safe code fix and formatted diff ready for git commit.
    """
    error_summary = state.get("error_summary", "")
    hypothesis = state.get("hypothesis", "")
    git_diff = state.get("git_diff", "")
    suspect_commit = state.get("suspect_commit", "unknown")
    deploy_status = state.get("suspect_commit_deploy_status") or "live"
    confidence = float(state.get("confidence", 0.0))

    # If confidence is low, code fix is not applicable
    if confidence < 0.7:
        logger.info("Skipping code fix generation: confidence (%.2f) < threshold (0.7).", confidence)
        return {"proposed_fix": None}

    file_path = extract_target_file_path(git_diff, error_summary, hypothesis)

    await thought_manager.broadcast_thought(
        node="generate_fix_node",
        status="started",
        thought=f"Synthesizing automated code remediation patch for [{file_path}]...",
    )

    # Fetch current file content from GitHub repository
    current_content, blob_sha = await github_tool.fetch_file_content(file_path)

    llm = get_llm()
    structured_llm = llm.with_structured_output(CodeFixOutput)

    system_prompt = (
        "You are a Staff Software Engineer & AI SRE performing automated code remediation.\n"
        "Your task is to generate a minimal, safe, and precise code patch that resolves the diagnosed incident.\n\n"
        "### RULES FOR CODE FIX GENERATION:\n"
        "1. Fix the root cause directly: correct typos (e.g. `MNGO_URI` or `MONGO_URII` -> `MONGO_URI`), missing checks, incorrect configuration values, or syntax errors.\n"
        "2. Do NOT rewrite unrelated code or change formatting unnecessarily.\n"
        "3. Provide `code_patch` in unified diff format (e.g. `--- old\n+++ new\n- line\n+ line`).\n"
        "4. Provide `updated_file_content` containing the FULL, ready-to-commit file content.\n"
        "5. Provide a conventional commit message (e.g. `fix(server): correct MONGO_URII typo to MONGO_URI in server.js`).\n"
        "6. Provide a concise explanation of why the fix works."
    )

    user_prompt = (
        f"### Error Diagnostic:\n{error_summary}\n\n"
        f"### Root-Cause Hypothesis:\n{hypothesis}\n\n"
        f"### Target File Path: {file_path}\n\n"
        f"### Current File Content:\n{current_content[:3000] if current_content else '(File content unavailable)'}\n\n"
        f"### Recent Git Diff Context:\n{git_diff[:2000]}\n\n"
        "Generate the structured CodeFixOutput patch."
    )

    proposed_fix: dict[str, Any] | None = None
    try:
        result: CodeFixOutput = await structured_llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )
        if result.is_fixable and result.updated_file_content:
            proposed_fix = {
                "file_path": result.file_path or file_path,
                "code_patch": result.code_patch,
                "updated_file_content": result.updated_file_content,
                "commit_message": result.commit_message,
                "explanation": result.explanation,
                "blob_sha": blob_sha,
            }
            logger.info("Generated code fix for [%s]: %s", proposed_fix["file_path"], proposed_fix["commit_message"])
    except Exception as exc:
        logger.error(f"Error during generate_fix_node LLM invocation: {exc}", exc_info=True)
        proposed_fix = None

    if proposed_fix:
        thought_msg = (
            f"Code remediation proposed for [{proposed_fix['file_path']}]: {proposed_fix['commit_message']}. "
            "Awaiting human approval to commit to GitHub."
        )
    else:
        thought_msg = f"No automated code patch synthesized for [{file_path}]. Falling back to standard infrastructure remediation."

    await thought_manager.broadcast_thought(
        node="generate_fix_node",
        status="completed",
        thought=thought_msg,
        state_updates={"proposed_fix": proposed_fix},
    )

    return {"proposed_fix": proposed_fix}
