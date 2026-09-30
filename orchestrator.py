"""Orchestrates guardrail, LLM-directed specialist review, and consolidation."""
from agents import ba_agent, classifier_agent, guardrail_agent, qa_agent, reviewer_agent, risk_agent
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


def _needs_follow_up(data):
    if not isinstance(data, dict):
        return False
    status = str(data.get("status", "")).strip().upper()
    try:
        score = float(data.get("quality_score"))
    except (TypeError, ValueError):
        return False
    if not 0 <= score <= 10:
        return False
    if status == "MAJOR GAPS":
        return True
    expected_status = "READY" if score >= 7 else "NEEDS CLARIFICATION" if score > 4 else "MAJOR GAPS"
    return status != expected_status


def _choose_follow_up(data):
    focus = " ".join(str(item) for item in (
        data.get("top_gaps", []) + data.get("recommended_clarifications", [])
        if isinstance(data.get("top_gaps", []), list)
        and isinstance(data.get("recommended_clarifications", []), list)
        else []
    )).lower()
    if any(term in focus for term in ("test", "acceptance", "validation", "scenario", "boundary")):
        return "qa", qa_agent
    if any(term in focus for term in ("risk", "customer impact", "financial", "privacy", "security")):
        return "risk", risk_agent
    return "ba", ba_agent


def review(requirement: str, on_status=None) -> dict:
    """on_status(agent_key, state) is called with state in: running, done, failed, skipped."""
    def notify(key, state):
        if on_status:
            on_status(key, state)

    result = {"model": "", "agents": {}, "final": None, "error": "",
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
        notify("classifier", "skipped")
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
        notify("classifier", "skipped")
        for key, _ in SPECIALISTS:
            notify(key, "skipped")
        notify("reviewer", "skipped")
        notify("follow_up", "skipped")
        return finish()

    notify("classifier", "running")
    classification = _run_agent(
        client, classifier_agent, classifier_agent.build_user_message(requirement)
    )
    result["agents"]["classifier"] = classification
    if classification["fatal"]:
        result["error"] = classification["error"]
        notify("classifier", "failed")
        for key, _ in SPECIALISTS:
            notify(key, "skipped")
        notify("reviewer", "skipped")
        notify("follow_up", "skipped")
        return finish()
    classification_valid = _valid_classification(classification["data"])
    if not classification_valid and classification["status"] == "ok":
        classification["status"] = "failed"
        classification["error"] = "The classifier returned invalid routing data; all specialists were run."
    notify("classifier", "done" if classification_valid else "failed")

    if classification_valid:
        classification_data = classification["data"]
        selected_specialists = [
            (key, module) for key, module in SPECIALISTS
            if key == "ba"
            or (key == "qa" and classification_data["run_qa"])
            or (key == "risk" and classification_data["run_risk_review"])
        ]
    else:
        # If routing output is unusable, take the conservative path and run all reviewers.
        selected_specialists = SPECIALISTS

    # Each selected specialist sees only the original requirement.
    for key, module in selected_specialists:
        notify(key, "running")
        context = retriever.get_context(key, requirement)
        agent_result = _run_agent(client, module, module.build_user_message(requirement, context=context))
        result["agents"][key] = agent_result
        notify(key, "done" if agent_result["status"] == "ok" else "failed")
        if agent_result["fatal"]:  # e.g. bad API key: stop, do not waste calls
            result["error"] = agent_result["error"]
            for remaining_key, _ in SPECIALISTS:
                if remaining_key not in result["agents"]:
                    notify(remaining_key, "skipped")
            notify("reviewer", "skipped")
            notify("follow_up", "skipped")
            return finish()

    for key, _ in SPECIALISTS:
        if key not in result["agents"]:
            notify(key, "skipped")

    # Senior Reviewer: only runs if at least one specialist succeeded.
    specialist_results = {
        key: result["agents"][key] for key, _ in SPECIALISTS if key in result["agents"]
    }
    if not any(agent["status"] == "ok" for agent in specialist_results.values()):
        result["error"] = "All specialist agents failed, so the Senior Reviewer was skipped."
        notify("reviewer", "skipped")
        notify("follow_up", "skipped")
        return finish()

    notify("reviewer", "running")
    reviewer_context = retriever.get_context("reviewer", requirement)
    final = _run_agent(
        client, reviewer_agent,
        reviewer_agent.build_user_message(requirement, specialist_results, context=reviewer_context),
    )
    result["final"] = final
    notify("reviewer", "done" if final["status"] == "ok" else "failed")

    if final["status"] == "ok" and _needs_follow_up(final["data"]):
        key, module = _choose_follow_up(final["data"])
        notify("follow_up", "running")
        follow_up_prompt = (
            module.SYSTEM_PROMPT
            + " Focus only on the Senior Reviewer's listed gaps and clarify whether they are material. "
            + "Do not repeat unrelated findings; preserve your normal JSON response schema."
        )
        follow_up_message = (
            f"Original requirement:\n{requirement}\n\n"
            f"Senior Reviewer assessment:\n{final['raw']}\n\n"
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
