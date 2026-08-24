import logging
from langchain_core.messages import HumanMessage, SystemMessage
from app.agent.llm import get_llm
from app.agent.state import CorrelationOutput, IncidentState
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.agent.correlate")


async def correlate_node(state: IncidentState) -> dict:
    """
    LLM call: Correlates the error summary with recent git diffs to generate
    a root-cause hypothesis and strict numeric confidence score (0.0 - 1.0).
    """
    error_summary = state.get("error_summary", "")
    git_diff = state.get("git_diff", "")
    suspect_commit = state.get("suspect_commit", "unknown")
    deploy_status = state.get("suspect_commit_deploy_status") or "unknown"

    await thought_manager.broadcast_thought(
        node="correlate_node",
        status="started",
        thought=f"Correlating error diagnostics against commit diff [{suspect_commit}] (Deploy status: [{deploy_status}])...",
    )

    llm = get_llm()
    structured_llm = llm.with_structured_output(CorrelationOutput)

    system_prompt = (
        "You are a Principal Site Reliability Engineer (SRE) performing automated root cause analysis.\n\n"
        "### ANALYSIS RULES (Strict Priority Order):\n"
        "1. LITERAL ERRORS FIRST: Scan the git diff line-by-line for simple, concrete literal defects BEFORE reaching for complex architectural or behavioral theories (like race conditions, thread deadlocks, or lock contention). Look specifically for:\n"
        "   - Variable / identifier typos and misspellings (e.g., `MNGO_URI` instead of `MONGO_URI`, `proccess` instead of `process`)\n"
        "   - Misspelled environment variable keys or configuration constants\n"
        "   - Incorrect string literals, endpoint URLs, or ports\n"
        "   - Off-by-one errors, missing punctuation, or inverted boolean conditions\n"
        "2. IDENTIFIER MATCHING: If the error diagnostic text or stack trace mentions an identifier or variable (e.g. `MongoServerError`, `MONGO_URI`, `undefined`), and that identifier or a similar-looking typo appears in the diff, treat that as prime evidence and prioritize it above generic explanations.\n"
        "3. QUOTE EXACT DIFF LINES: You MUST quote the specific line(s) from the diff that you are basing your hypothesis on (e.g., `Diff line: '- MONGO_URI' / '+ MNGO_URI'`). If you cannot identify a specific line in the diff that caused the failure, state this explicitly and assign a lower confidence score (<= 0.4).\n"
        "4. DEPLOY STATUS AWARENESS:\n"
        "   - You are provided with the deploy status of the suspect commit on Render (`suspect_commit_deploy_status`).\n"
        "   - If the deploy status is NOT 'live' (e.g., 'update_failed', 'build_failed', 'deactivated', 'canceled', 'unknown'): the suspect commit NEVER ran in production. You must:\n"
        "     a) Explicitly state in the hypothesis: 'Note: This commit failed to deploy (Render status: <status>) and is not live in production.'\n"
        "     b) Significantly lower your confidence score (<= 0.35) because non-deployed code cannot cause active runtime incidents.\n"
        "     c) Note that no restart or rollback of the live container is needed for code that was never deployed."
    )

    user_prompt = (
        f"### Error Diagnostic Summary:\n{error_summary}\n\n"
        f"### Suspect Commit: {suspect_commit}\n"
        f"### Suspect Commit Render Deploy Status: {deploy_status}\n\n"
        f"### Recent Git Diffs:\n{git_diff[:3000]}\n\n"
        "Perform root-cause analysis according to the rules above. "
        "Produce a clear hypothesis citing the specific quoted diff line(s) and assign an accurate numeric confidence score (0.0 to 1.0)."
    )

    try:
        result: CorrelationOutput = await structured_llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )
        hypothesis = result.hypothesis
        # Ensure confidence is clamped to [0.0, 1.0]
        confidence = max(0.0, min(1.0, float(result.confidence)))
    except Exception as exc:
        logger.error(f"Error during correlate_node LLM call ({exc}). Using fallback hypothesis.")
        hypothesis = (
            f"Likely regression introduced in commit {suspect_commit} leading to {error_summary}."
        )
        confidence = 0.75

    thought_msg = (
        f"Hypothesis generated (Confidence: {confidence * 100:.1f}%): {hypothesis}"
    )

    await thought_manager.broadcast_thought(
        node="correlate_node",
        status="completed",
        thought=thought_msg,
        confidence=confidence,
        state_updates={
            "hypothesis": hypothesis,
            "confidence": confidence,
        },
    )

    return {
        "hypothesis": hypothesis,
        "confidence": confidence,
    }
