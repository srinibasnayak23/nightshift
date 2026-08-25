import logging
from langchain_core.messages import SystemMessage, HumanMessage
from app.agent.llm import get_llm
from app.agent.state import ErrorSummaryOutput, IncidentState
from app.services.thought_manager import thought_manager

logger = logging.getLogger("nightshift.agent.summarize")


async def summarize_node(state: IncidentState) -> dict:
    """
    LLM call: Analyzes raw log and extracts structured error summary
    including error type, affected service, and likely component.
    """
    raw_log = state.get("raw_log", "")

    await thought_manager.broadcast_thought(
        node="summarize_node",
        status="started",
        thought="Invoking LLM to analyze error signature and component impact...",
    )

    llm = get_llm()
    structured_llm = llm.with_structured_output(ErrorSummaryOutput)

    system_prompt = (
        "You are an expert AI Site Reliability Engineer (SRE). "
        "Analyze the given raw log message from a production microservice. "
        "Extract the precise error type, affected service name, most likely failing component/subsystem, "
        "and a crisp 1-2 sentence diagnostic summary."
    )

    try:
        result: ErrorSummaryOutput = await structured_llm.ainvoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"Analyze this raw log:\n{raw_log}"),
            ]
        )

        formatted_summary = (
            f"[{result.error_type}] Service: {result.affected_service} | "
            f"Component: {result.likely_component} | Details: {result.summary}"
        )
    except Exception as exc:
        logger.error(f"Error during summarize_node LLM call ({exc}). Using fallback summary.")
        formatted_summary = f"Error detected in service logs: {raw_log[:150]}"

    await thought_manager.broadcast_thought(
        node="summarize_node",
        status="completed",
        thought=f"Error diagnosed: {formatted_summary}",
        state_updates={"error_summary": formatted_summary},
    )

    return {"error_summary": formatted_summary}
