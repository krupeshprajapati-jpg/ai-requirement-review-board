"""Fallback routing logic used when planner output is missing or unusable."""


def _fallback_agents(requirement):
    """Choose relevant reviewers with local rules when planner output is unusable."""
    text = requirement.lower()
    trivial_terms = ("typo", "spelling correction", "punctuation fix", "static label", "copy-only")
    trivial = any(term in text for term in trivial_terms)
    agents = []
    if not trivial:
        agents.append("ba")

    non_testable_terms = ("intuitive", "user-friendly", "easy to use", "seamless", "modern", "beautiful")
    action_terms = (
        "should", "must", "shall", "allow", "enable", "display", "show", "save", "send",
        "create", "update", "delete", "download", "select", "submit", "retry", "receive",
        "view", "enter", "apply", "process",
    )
    if not (any(term in text for term in non_testable_terms)
            and not any(term in text for term in action_terms)):
        agents.append("qa")

    risk_terms = (
        "financial", "payment", "repayment", "loan", "money", "amount", "fee", "interest",
        "refund", "transfer", "delete", "irreversible", "automatically", "automatic", "retry",
        "email", "sms", "notification", "message", "communicat", "customer contact",
    )
    if any(term in text for term in risk_terms):
        agents.append("risk")

    return agents


def _fallback_follow_up(requirement, specialist_results):
    """Choose a targeted follow-up specialist when the reviewer does not provide one."""
    focus = requirement.lower() + " " + " ".join(
        str(result.get("raw", "")) for result in specialist_results.values()
        if result.get("status") == "ok"
    ).lower()
    if any(term in focus for term in ("test", "acceptance", "validation", "scenario", "boundary")):
        preferred = "qa"
    elif any(term in focus for term in ("risk", "customer impact", "financial", "privacy", "security")):
        preferred = "risk"
    else:
        preferred = "ba"
    if preferred in specialist_results and specialist_results[preferred].get("status") == "ok":
        return preferred
    return next(key for key, result in specialist_results.items() if result.get("status") == "ok")
