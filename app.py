import html

import streamlit as st

from orchestrator import review

SAMPLES = {
    "Sample 1 - Ambiguous (part payment)": (
        "Customer should be allowed to make a part payment on their loan. After successful payment, "
        "the customer can choose one of the following options:\n\n"
        "1. Keep EMI same and reduce tenure\n"
        "2. Keep tenure same and reduce EMI"
    ),
    "Sample 2 - Loan account contact update": (
        "A loan customer should be able to update the email address on their loan account through the "
        "customer portal after verifying a one-time password sent to the new address."
    ),
    "Sample 3 - Incomplete/Risky (failed EMI payment)": (
        "If a customer's monthly loan repayment fails, automatically retry the payment."
    ),
    "Sample 4 - Low complexity (notification preference)": (
        "A customer should be able to turn loan payment reminder emails on or off from the notification "
        "settings page. The selected preference should be saved and shown when the page is reopened."
    ),
    "Sample 5 - QA focus (statement download)": (
        "A customer should be able to download a monthly loan statement from the customer portal. The "
        "statement should include transactions for the selected month and be available as a PDF."
    ),
    "Sample 6 - Service request (repayment dispute)": (
        "A loan customer should be able to raise a service request to dispute a repayment shown in their "
        "loan transaction history, describe the issue, and attach supporting documents. The customer should "
        "receive a case reference and be able to view status updates and the resolution."
    ),
    "Sample 7 - Risk focus (repayment account change)": (
        "A loan customer should be able to replace the bank account used for monthly repayments in the "
        "customer portal after entering an OTP. The new account should be used for the next repayment."
    ),
}
PLACEHOLDER = "-- Choose a sample requirement --"

AGENTS = [("guardrail", "Guardrail", "Checking request..."),
          ("classifier", "Classifier", "Choosing reviews..."),
          ("ba", "Business Analyst", "Analyzing..."),
          ("qa", "QA Engineer", "Analyzing..."),
          ("risk", "Risk Reviewer", "Analyzing..."),
          ("reviewer", "Senior Reviewer", "Consolidating..."),
          ("follow_up", "Targeted Follow-up", "Investigating gaps...")]

STATUS_COLORS = {"READY": "#1a7f37", "NEEDS CLARIFICATION": "#b7791f", "MAJOR GAPS": "#c62828"}

st.set_page_config(page_title="AI Requirement Review Board", page_icon="🧭", layout="wide")

for key, default in {"requirement_text": "", "sample_choice": PLACEHOLDER, "result": None}.items():
    st.session_state.setdefault(key, default)


def load_sample():
    choice = st.session_state.sample_choice
    if choice in SAMPLES:
        st.session_state.requirement_text = SAMPLES[choice]


def clear_review():
    st.session_state.result = None
    st.session_state.requirement_text = ""
    st.session_state.sample_choice = PLACEHOLDER


# ---------- helpers ----------
def as_list(value):
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def item_text(item):
    if isinstance(item, dict):
        return "; ".join(f"{k}: {v}" for k, v in item.items())
    return str(item)


def render_bullets(items):
    items = as_list(items)
    if not items:
        st.caption("None reported.")
    for item in items:
        st.markdown(f"- {item_text(item)}")


def render_data(data: dict):
    for key, value in data.items():
        st.markdown(f"**{key.replace('_', ' ').title()}**")
        if isinstance(value, dict):
            render_bullets([f"{k}: {v}" for k, v in value.items()])
        elif isinstance(value, list):
            render_bullets(value)
        else:
            st.write(value)


def to_score(value):
    try:
        return max(0.0, min(10.0, float(str(value).split("/")[0].strip())))
    except (ValueError, TypeError):
        return None


def render_agent_result(agent):
    if agent is None:
        st.info("Not run yet.")
        return
    if agent["status"] == "failed":
        st.error(f"{agent['name']} failed: {agent['error']}")
        return
    if agent["data"]:
        render_data(agent["data"])
    else:
        st.warning("The response was not valid JSON, so the raw output is shown below.")
        st.text(agent["raw"])
    with st.expander("Raw model output"):
        st.code(agent["raw"], language="json")


# ---------- header + input ----------
st.title("AI Requirement Review Board")
st.caption("Multi-Agent Requirement Quality Analysis")

st.selectbox("Sample Requirement", [PLACEHOLDER] + list(SAMPLES), key="sample_choice", on_change=load_sample)
st.text_area("Requirement", key="requirement_text", height=200,
             placeholder="Enter a software / business requirement (synthetic, non-confidential data only)...")

col_start, col_clear, _ = st.columns([1, 1, 4])
start_clicked = col_start.button("Start AI Review", type="primary", use_container_width=True)
col_clear.button("Clear Review", on_click=clear_review, use_container_width=True)

# ---------- status area ----------
st.markdown("#### Agent Status")
status_boxes = {}
for column, (key, label, _) in zip(st.columns(len(AGENTS)), AGENTS):
    status_boxes[key] = column.empty()

RUNNING_TEXT = {key: text for key, _, text in AGENTS}
LABELS = {key: label for key, label, _ in AGENTS}
STATE_VIEW = {"waiting": "⚪ Waiting", "done": "✅ Completed", "failed": "❌ Failed", "skipped": "⏭️ Skipped"}


def show_status(key, state):
    text = f"⏳ {RUNNING_TEXT[key]}" if state == "running" else STATE_VIEW[state]
    status_boxes[key].markdown(f"**{LABELS[key]}**\n\n{text}")


def status_from_result(result):
    states = {}
    for key, _, _ in AGENTS:
        if key in {"reviewer", "follow_up"}:
            continue
        agent = result["agents"].get(key)
        states[key] = "skipped" if agent is None else ("done" if agent["status"] == "ok" else "failed")
    final = result["final"]
    states["reviewer"] = "skipped" if final is None else ("done" if final["status"] == "ok" else "failed")
    follow_up = result.get("follow_up")
    states["follow_up"] = "skipped" if follow_up is None else ("done" if follow_up["status"] == "ok" else "failed")
    return states


# ---------- run (only when the button is clicked) ----------
if start_clicked:
    requirement = st.session_state.requirement_text.strip()
    if not requirement:
        st.warning("Please enter a requirement or choose a sample before starting the review.")
    else:
        st.session_state.result = None
        for key, _, _ in AGENTS:
            show_status(key, "waiting")
        st.session_state.result = review(requirement, on_status=show_status)
elif st.session_state.result:
    for key, state in status_from_result(st.session_state.result).items():
        show_status(key, state)
else:
    for key, _, _ in AGENTS:
        show_status(key, "waiting")

# ---------- results (read from session_state, never triggers LLM calls) ----------
result = st.session_state.result
if result:
    if result["error"]:
        st.error(result["error"])

    tab_final, tab_guardrail, tab_classifier, tab_ba, tab_qa, tab_risk, tab_follow_up, tab_tech = st.tabs(
        ["Final Review", "Guardrail", "Routing", "Business Analyst", "QA Engineer", "Risk Analysis",
         "Targeted Follow-up", "Technical Details"])

    with tab_final:
        final = result["final"]
        if final is None:
            st.info("No final review is available for this run.")
        elif final["status"] == "failed":
            st.error(f"Senior Reviewer failed: {final['error']}")
        elif not final["data"]:
            st.warning("The Senior Reviewer's response was not valid JSON, so the raw output is shown below.")
            st.text(final["raw"])
        else:
            data = final["data"]
            score = to_score(data.get("quality_score"))
            status = str(data.get("status", "N/A")).strip().upper()
            color = STATUS_COLORS.get(status, "#455a64")
            st.markdown("**Requirement Quality Score**")
            score_text = f"{score:g} / 10" if score is not None else "N/A"
            st.markdown(f"<div style='font-size:3.2rem;font-weight:700;line-height:1.1'>{score_text}</div>",
                        unsafe_allow_html=True)
            st.markdown(
                f"Status: <span style='background:{color};color:white;padding:4px 12px;border-radius:14px;"
                f"font-weight:600'>{html.escape(status)}</span>", unsafe_allow_html=True)
            st.caption(f"LLM calls used for this analysis: {result['llm_calls']}")
            st.divider()
            st.subheader("Executive Summary")
            st.write(data.get("executive_summary", "N/A"))
            st.subheader("Top Requirement Gaps")
            render_bullets(data.get("top_gaps"))
            st.subheader("Recommended Clarifications")
            render_bullets(data.get("recommended_clarifications"))
            st.subheader("Suggested Acceptance Criteria")
            render_bullets(data.get("recommended_acceptance_criteria"))
            st.subheader("Final Recommendation")
            st.write(data.get("final_recommendation", "N/A"))
            if result.get("follow_up") and result["follow_up"]["status"] == "ok":
                st.divider()
                st.subheader("Targeted Follow-up Findings")
                st.caption(f"Additional review by {result['follow_up']['name']}; the consolidated score is unchanged.")
                render_agent_result(result["follow_up"])

    with tab_guardrail:
        render_agent_result(result["agents"].get("guardrail"))

    with tab_classifier:
        classifier = result["agents"].get("classifier")
        render_agent_result(classifier)
        if classifier and classifier["status"] == "failed" and not classifier["data"]:
            st.info("Routing output was unusable; all specialists were run as a fallback.")

    with tab_ba:
        render_agent_result(result["agents"].get("ba"))
    with tab_qa:
        render_agent_result(result["agents"].get("qa"))
    with tab_risk:
        render_agent_result(result["agents"].get("risk"))
    with tab_follow_up:
        if result.get("follow_up"):
            render_agent_result(result["follow_up"])
        else:
            st.info("No targeted follow-up was needed for this assessment.")

    with tab_tech:
        st.markdown(f"**Model:** {result['model'] or 'N/A'}")
        st.markdown(f"**LLM calls:** {result['llm_calls']} (successful: {result['successful_calls']})")
        st.markdown("**Agents:** 6, plus an optional targeted follow-up")
        st.markdown("**Architecture:** Multi-Agent Orchestration")
        if result["tokens"]:
            st.markdown(f"**Total tokens reported by provider:** {result['tokens']}")
