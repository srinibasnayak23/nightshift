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

    await thought_manager.broadcast_thought(
        node="correlate_node",
        status="started",
        thought=f"Correlating error diagnostics against commit diff [{suspect_commit}]...",
    )

    llm = get_llm()
    structured_llm = llm.with_structured_output(CorrelationOutput)

    system_prompt = (
        "You are a Principal SRE performing automated root cause analysis. "
        "You are given an error diagnostic summary and recent git commits with code diffs. "
        "Determine whether and how the recent code changes caused or contributed to this incident. "
        "Produce a clear, plain-language hypothesis explaining the failure mechanism, and assign "
        "a strict numeric confidence score between 0.0 (unrelated) and 1.0 (certain root cause)."
    )

    user_prompt = (
        f"### Error Diagnostic Summary:\n{error_summary}\n\n"
        f"### Suspect Commit: {suspect_commit}\n\n"
        f"### Recent Git Diffs:\n{git_diff[:2500]}\n\n"
        "Generate root-cause hypothesis and numeric confidence score."
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
