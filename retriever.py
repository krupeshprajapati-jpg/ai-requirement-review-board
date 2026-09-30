"""Small, local TF-IDF retriever for the synthetic review knowledge base."""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

KNOWLEDGE_BASE = Path(__file__).resolve().parent / "knowledge_base"
MIN_SIMILARITY = 0.08
AGENT_SOURCES = {
    "ba": {"glossary.md", "best_practices.md"},
    "qa": {"glossary.md", "best_practices.md"},
    "risk": {"glossary.md", "risk_patterns.md"},
}

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
except Exception as exc:  # Keep the review app usable if the optional local index is unavailable.
    logger.warning("Local retrieval is unavailable: %s", exc)
    TfidfVectorizer = None
    cosine_similarity = None


def _markdown_snippets(text):
    snippets = []
    heading = ""
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        if block.startswith("#"):
            heading = block.lstrip("# ").strip()
            continue
        snippet = f"{heading}: {block}" if heading else block
        snippets.append(" ".join(snippet.split()))
    return snippets


def _load_records():
    records = []
    for filename in ("glossary.md", "best_practices.md", "risk_patterns.md"):
        try:
            text = (KNOWLEDGE_BASE / filename).read_text(encoding="utf-8")
            records.extend(
                {"kind": "reference", "source": filename, "text": snippet}
                for snippet in _markdown_snippets(text)
            )
        except Exception as exc:
            logger.warning("Could not load knowledge-base file %s: %s", filename, exc)

    try:
        reviews = json.loads((KNOWLEDGE_BASE / "past_reviews.json").read_text(encoding="utf-8"))
        if not isinstance(reviews, list):
            raise ValueError("past_reviews.json must contain a list")
        for review in reviews:
            if not isinstance(review, dict):
                continue
            requirement = review.get("requirement")
            if not isinstance(requirement, str) or not requirement.strip():
                continue
            records.append({"kind": "review", "source": "past_reviews.json", "text": requirement,
                            "quality_score": review.get("quality_score"), "status": review.get("status"),
                            "reason": str(review.get("reason", "")).strip()})
    except Exception as exc:
        logger.warning("Could not load knowledge-base file past_reviews.json: %s", exc)
    return records


_RECORDS = _load_records()
_VECTORIZER = None
_MATRIX = None
if TfidfVectorizer is not None:
    try:
        if _RECORDS:
            _VECTORIZER = TfidfVectorizer(stop_words="english")
            _MATRIX = _VECTORIZER.fit_transform([record["text"] for record in _RECORDS])
    except Exception as exc:
        logger.warning("Could not build local TF-IDF index: %s", exc)
        _VECTORIZER = None
        _MATRIX = None


def get_context(agent_key: str, requirement_text: str, top_k: int = 2) -> str:
    """Return relevant local reference snippets, or an empty string when none qualify."""
    try:
        if agent_key not in {*AGENT_SOURCES, "reviewer"}:
            logger.warning("Unknown retrieval agent key: %s", agent_key)
            return ""
        if not isinstance(requirement_text, str) or not requirement_text.strip():
            return ""
        if _VECTORIZER is None or _MATRIX is None:
            return ""

        query = _VECTORIZER.transform([requirement_text])
        scores = cosine_similarity(query, _MATRIX).ravel()
        if agent_key == "reviewer":
            indexes = [i for i, record in enumerate(_RECORDS) if record["kind"] == "review"]
        else:
            sources = AGENT_SOURCES[agent_key]
            indexes = [i for i, record in enumerate(_RECORDS)
                       if record["kind"] == "reference" and record["source"] in sources]

        matches = sorted(((scores[index], index) for index in indexes), reverse=True)
        limit = min(2, max(1, int(top_k))) if agent_key == "reviewer" else max(1, int(top_k))
        lines = []
        for score, index in matches:
            if score < MIN_SIMILARITY or len(lines) >= limit:
                break
            record = _RECORDS[index]
            if agent_key == "reviewer":
                lines.append(
                    f"Similar past review (quality score {record['quality_score']}/10): {record['reason']}"
                )
            else:
                lines.append(record["text"])
        return "Reference context:\n" + "\n".join(f"- {line}" for line in lines) if lines else ""
    except Exception as exc:
        logger.warning("Local retrieval failed for %s: %s", agent_key, exc)
        return ""