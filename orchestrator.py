"""Orchestrates guardrail, LLM-directed specialist review, and consolidation."""
from agents import ba_agent, guardrail_agent, planner_agent, qa_agent, reviewer_agent, risk_agent
from fallback_rules import _fallback_agents, _fallback_follow_up
from llm_client import LLMClient, LLMError, parse_json
import retriever

SPECIALISTS = [("ba", ba_agent), ("qa", qa_agent), ("risk", risk_agent)]


def _run_agent(client, module, user_message, system_prompt=None):
    try:
        raw = client.chat(system_prompt or module.SYSTEM_PROMPT, user_message, module.MAX_TOKENS)
    except LLMError as e:
        return {"name": module.NAME, "status": "failed", "raw": "", "data": None,
                "error": str(e), "fatal": e.fatal}
    return {"name": module.NAME, "status": "ok", "raw": raw, "data": parse_json(raw),
            "error": "", "fatal": False}


def _valid_classification(data):
    if not isinstance(data, dict):
        return False
    complexity = data.get("complexity")
    return (
        isinstance(complexity, str)
        and complexity.strip().lower() in {"low", "medium", "high"}
        and isinstance(data.get("run_qa"), bool)
        and isinstance(data.get("run_risk_review"), bool)
    )


def decide_agents(client, requirement) -> dict:
    """Use the planner when its ordered agent list is valid; otherwise apply local fallback rules."""
    try:
        planner = _run_agent(client, planner_agent, planner_agent.build_user_message(requirement))
        data = planner["data"]
        agents = data.get("agents_to_run") if isinstance(data, dict) else None
        reasoning = data.get("reasoning") if isinstance(data, dict) else None
        allowed = {key for key, _ in SPECIALISTS}
        if (isinstance(agents, list) and agents
                and all(isinstance(key, str) and key in allowed for key in agents)
                and isinstance(reasoning, str) and reasoning.strip()):
            return {
                "agents_to_run": list(dict.fromkeys(agents)),
                "reasoning": reasoning.strip(),
                "source": "planner",
            }
    except Exception:
        pass

    fallback_agents = _fallback_agents(requirement)
    if not fallback_agents:
        fallback_agents = ["qa"]
    return {
        "agents_to_run": fallback_agents,
        "reasoning": "Fallback rules selected reviewers based on requirement scope and risk indicators.",
        "source": "fallback_rules",
    }


def _reviewer_follow_up(data):
    if not isinstance(data, dict) or not isinstance(data.get("needs_follow_up"), bool):
        return None
    if not data["needs_follow_up"]:
        return False
    key = data.get("follow_up_specialist")
    allowed = {specialist_key for specialist_key, _ in SPECIALISTS}
    return key if isinstance(key, str) and key in allowed else None


def review(requirement: str, on_status=None) -> dict:
    """on_status(agent_key, state) is called with state in: running, done, failed, skipped."""
    def notify(key, state):
        if on_status:
            on_status(key, state)

    result = {"model": "", "agents": {}, "final": None, "error": "", "routing": None,
              "follow_up": None, "llm_calls": 0, "successful_calls": 0, "tokens": 0}

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
        notify("planner", "skipped")
        for key, _ in SPECIALISTS:
            notify(key, "skipped")
        notify("reviewer", "skipped")
        notify("follow_up", "skipped")
        return finish()

    notify("guardrail", "done")
    if decision == "BLOCK":
        reason_value = guardrail["data"].get("reason")
        reason = reason_value.strip() if isinstance(reason_value, str) else ""
        reason = reason or "The request did not pass the input guardrail."
        result["error"] = f"Request blocked by the guardrail: {reason}"
        notify("planner", "skipped")
        for key, _ in SPECIALISTS:
            notify(key, "skipped")
        notify("reviewer", "skipped")
        notify("follow_up", "skipped")
        return finish()

    notify("planner", "running")
    result["routing"] = decide_agents(client, requirement)
    notify("planner", "done" if result["routing"]["source"] == "planner" else "fallback")
    selected_keys = result["routing"]["agents_to_run"]
    selected_specialists = [(key, module) for key in selected_keys
                            for specialist_key, module in SPECIALISTS if specialist_key == key]

    for key, module in SPECIALISTS:
        if key not in selected_keys:
            result["agents"][key] = {
                "name": module.NAME, "status": "skipped_by_orchestrator", "raw": "",
                "data": None, "error": "", "fatal": False,
            }
            notify(key, "skipped_by_orchestrator")

    # Each selected specialist sees only the original requirement.
    for index, (key, module) in enumerate(selected_specialists):
        notify(key, "running")
        context = retriever.get_context(key, requirement)
        agent_result = _run_agent(client, module, module.build_user_message(requirement, context=context))
        result["agents"][key] = agent_result
        notify(key, "done" if agent_result["status"] == "ok" else "failed")
        if agent_result["fatal"]:  # e.g. bad API key: stop, do not waste calls
            result["error"] = agent_result["error"]
            for remaining_key, _ in selected_specialists[index + 1:]:
                notify(remaining_key, "skipped")
            notify("reviewer", "skipped")
            notify("follow_up", "skipped")
            return finish()

    # Senior Reviewer: only runs if at least one specialist succeeded.
    specialist_results = {
        key: result["agents"][key] for key in selected_keys if key in result["agents"]
    }
    if not any(agent["status"] == "ok" for agent in specialist_results.values()):
        result["error"] = "All specialist agents failed, so the Senior Reviewer was skipped."
        notify("reviewer", "skipped")
        notify("follow_up", "skipped")
        return finish()

    notify("reviewer", "running")
    skipped_keys = [key for key, _ in SPECIALISTS if key not in selected_keys]
    skip_note = (
        f"Orchestrator decision: skipped specialist(s) {', '.join(skipped_keys)}. "
        f"Reasoning: {result['routing']['reasoning']}"
        if skipped_keys else "Orchestrator decision: no specialists were skipped."
    )
    reviewer_message = reviewer_agent.build_user_message(
        requirement, specialist_results
    ) + "\n\n" + skip_note
    final = _run_agent(
        client, reviewer_agent,
        reviewer_message,
    )
    result["final"] = final
    notify("reviewer", "done" if final["status"] == "ok" else "failed")

    reviewer_decision = _reviewer_follow_up(final["data"]) if final["status"] == "ok" else None
    fallback_follow_up = reviewer_decision is None
    if fallback_follow_up or isinstance(reviewer_decision, str):
        key = _fallback_follow_up(requirement, specialist_results) if fallback_follow_up else reviewer_decision
        module = dict(SPECIALISTS)[key]
        notify("follow_up", "running")
        if fallback_follow_up:
            follow_up_prompt = (
                module.SYSTEM_PROMPT
                + " The Senior Reviewer did not return a usable assessment. Independently reassess your area "
                "of the original requirement, using your previous findings if available. Preserve your normal "
                "JSON response schema."
            )
        else:
            follow_up_prompt = (
                module.SYSTEM_PROMPT
                + " Focus only on the Senior Reviewer's listed gaps and clarify whether they are material. "
                + "Do not repeat unrelated findings; preserve your normal JSON response schema."
            )
        follow_up_message = (
            f"Original requirement:\n{requirement}\n\n"
            f"Senior Reviewer assessment:\n{final['raw'] or 'No usable Senior Reviewer assessment was returned.'}\n\n"
            f"Your previous findings (if any):\n"
            f"{result['agents'].get(key, {}).get('raw', 'No prior findings from this specialist.')}\n\n"
            "Provide one targeted follow-up assessment."
        )
        follow_up_context = retriever.get_context(key, requirement)
        if follow_up_context:
            follow_up_message = f"{follow_up_message}\n\n{follow_up_context}"
        follow_up = _run_agent(client, module, follow_up_message, follow_up_prompt)
        follow_up["name"] = f"{module.NAME} (targeted follow-up)"
        follow_up["specialist"] = key
        result["follow_up"] = follow_up
        if follow_up["status"] == "failed":
            result["error"] = f"Targeted follow-up failed: {follow_up['error']}"
        notify("follow_up", "done" if follow_up["status"] == "ok" else "failed")
    else:
        result["follow_up"] = None
        notify("follow_up", "skipped")
    return finish()
