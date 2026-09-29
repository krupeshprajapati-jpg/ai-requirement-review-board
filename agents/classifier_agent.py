NAME = "Requirement Classifier"
MAX_TOKENS = 160

SYSTEM_PROMPT = (
    "Classify the software or business requirement to route a review workflow. "
    "Choose complexity as low, medium, or high. Decide whether a QA review and a general product-risk review "
    "would add value; low complexity may still need either review when the requirement warrants it. "
    "Do not evaluate or rewrite the requirement. Return ONLY valid JSON (no markdown, no extra text) with exactly "
    'these keys: "complexity" (low, medium, or high), "run_qa" (boolean), '
    '"run_risk_review" (boolean).'
)


def build_user_message(requirement: str) -> str:
    return f"Classify this requirement for review routing:\n{requirement}"