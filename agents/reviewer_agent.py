import json

NAME = "Senior Reviewer"
MAX_TOKENS = 1000

SYSTEM_PROMPT = (
    "You are the senior requirement reviewer. You receive the original requirement plus findings from a "
    "Business Analyst, a QA Engineer and a Risk Reviewer. Some reviewers may have failed; then rely on the others. "
    "Consolidate the findings; do not repeat everything. Be concise. "
    "Scoring guide: 9-10 very clear and implementation ready; 7-8 mostly clear with minor clarification; "
    "5-6 several important gaps; 0-4 major ambiguity or missing information. "
    "Keep status consistent with score: READY for 7-10, NEEDS CLARIFICATION for 5-6, "
    "and MAJOR GAPS for 0-4. "
    "Return ONLY valid JSON (no markdown, no extra text) with exactly these keys: "
    '"quality_score" (number 0-10, one decimal allowed), '
    '"status" (exactly one of: READY, NEEDS CLARIFICATION, MAJOR GAPS), '
    '"executive_summary" (2-3 sentences), '
    '"top_gaps" (at most 5 strings), '
    '"recommended_clarifications" (at most 5 strings), '
    '"recommended_acceptance_criteria" (at most 5 strings), '
    '"final_recommendation" (2-3 sentences).'
)


def build_user_message(requirement: str, agent_results: dict) -> str:
    """agent_results: {key: {"name", "status", "raw", "data", ...}} from the specialist agents."""
    parts = [f"Original requirement:\n{requirement}"]
    for result in agent_results.values():
        if result["status"] != "ok":
            parts.append(f"{result['name']} findings: FAILED - no findings available.")
        elif result["data"]:
            parts.append(f"{result['name']} findings:\n{json.dumps(result['data'], ensure_ascii=False)}")
        else:
            # The agent's JSON was malformed; pass a trimmed version of the raw text.
            parts.append(f"{result['name']} findings:\n{result['raw'][:1500]}")
    return "\n\n".join(parts)
