"""Orchestrator: runs BA, QA, Risk (each on the ORIGINAL requirement), then the Senior Reviewer.
Normal run = exactly 4 LLM calls."""
from agents import ba_agent, guardrail_agent, qa_agent, reviewer_agent, risk_agent
from llm_client import LLMClient, LLMError, parse_json

SPECIALISTS = [("ba", ba_agent), ("qa", qa_agent), ("risk", risk_agent)]


def _run_agent(client, module, user_message):
    try:
        raw = client.chat(module.SYSTEM_PROMPT, user_message, module.MAX_TOKENS)
    except LLMError as e:
        return {"name": module.NAME, "status": "failed", "raw": "", "data": None,
                "error": str(e), "fatal": e.fatal}
    return {"name": module.NAME, "status": "ok", "raw": raw, "data": parse_json(raw),
            "error": "", "fatal": False}


def review(requirement: str, on_status=None) -> dict:
    """on_status(agent_key, state) is called with state in: running, done, failed, skipped."""
    def notify(key, state):
        if on_status:
            on_status(key, state)

    result = {"model": "", "agents": {}, "final": None, "error": "",
              "llm_calls": 0, "successful_calls": 0, "tokens": 0}

    try:
        client = LLMClient()
    except LLMError as e:
        result["error"] = str(e)
        return result
    result["model"] = client.model

    def finish():
        result["llm_calls"] = client.total_requests
        result["successful_calls"] = client.successful_calls
        result["tokens"] = client.total_tokens
        return result

    notify("guardrail", "running")
    guardrail = _run_agent(client, guardrail_agent,
                           guardrail_agent.build_user_message(requirement))
    result["agents"]["guardrail"] = guardrail
    decision_value = (guardrail["data"] or {}).get("decision", "")
    decision = decision_value.strip().upper() if isinstance(decision_value, str) else ""
    if guardrail["status"] != "ok" or decision not in {"ALLOW", "BLOCK"}:
        guardrail["status"] = "failed"
        if not guardrail["error"]:
            guardrail["error"] = "The guardrail returned no valid ALLOW/BLOCK decision."
        result["error"] = f"Guardrail failed: {guardrail['error']}"
        notify("guardrail", "failed")
        for key, _ in SPECIALISTS:
            notify(key, "skipped")
        notify("reviewer", "skipped")
        return finish()

    notify("guardrail", "done")
    if decision == "BLOCK":
        reason_value = guardrail["data"].get("reason")
        reason = reason_value.strip() if isinstance(reason_value, str) else ""
        reason = reason or "The request did not pass the input guardrail."
        result["error"] = f"Request blocked by the guardrail: {reason}"
        for key, _ in SPECIALISTS:
            notify(key, "skipped")
        notify("reviewer", "skipped")
        return finish()

    # Specialists: each sees only the original requirement.
    for key, module in SPECIALISTS:
        notify(key, "running")
        agent_result = _run_agent(client, module, module.build_user_message(requirement))
        result["agents"][key] = agent_result
        notify(key, "done" if agent_result["status"] == "ok" else "failed")
        if agent_result["fatal"]:  # e.g. bad API key: stop, do not waste calls
            result["error"] = agent_result["error"]
            for remaining_key, _ in SPECIALISTS:
                if remaining_key not in result["agents"]:
                    notify(remaining_key, "skipped")
            notify("reviewer", "skipped")
            return finish()

    # Senior Reviewer: only runs if at least one specialist succeeded.
    if not any(a["status"] == "ok" for a in result["agents"].values()):
        result["error"] = "All specialist agents failed, so the Senior Reviewer was skipped."
        notify("reviewer", "skipped")
        return finish()

    notify("reviewer", "running")
    final = _run_agent(client, reviewer_agent, reviewer_agent.build_user_message(requirement, result["agents"]))
    result["final"] = final
    notify("reviewer", "done" if final["status"] == "ok" else "failed")
    return finish()
