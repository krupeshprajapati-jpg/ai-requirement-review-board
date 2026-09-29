# AI Requirement Review Board

Multi-Agent Requirement Quality Analysis
A user enters a software/business requirement. A Guardrail checks whether it belongs in the workflow and
blocks clearly illegal, harmful, or unrelated requests. An LLM classifier assesses complexity and chooses whether
QA and product-risk reviews add value; the Business Analyst always runs. A Senior Reviewer consolidates
the selected findings. Major gaps or an inconsistent score/status trigger one targeted specialist follow-up.

> **Security / data privacy warning**
> This POC sends requirement text to a third-party LLM provider. Do not submit confidential company information, customer PII, credentials, production data, or other sensitive information unless use of the provider has been approved by your organization.
> The Guardrail is also an LLM call, so it does not prevent the submitted text from reaching that provider and is not a substitute for organizational policy or legal review.

## 1. Architecture

```
                  USER
                   |
             Requirement Input
                   |
              Orchestrator
                   |
              Guardrail
                   |
          Requirement Classifier
                   |
     BA always; QA and Risk are conditional
                   |
            Senior Reviewer
                   |
       Major gaps OR score mismatch?
              /           \
            yes             no
             |               |
     One specialist       Final Report
       follow-up
             |
        Final Report
```

```
ai-requirement-review-board/
|-- app.py            Streamlit UI
|-- orchestrator.py   routes specialists, consolidates findings, and conditionally follows up
|-- llm_client.py     OpenRouter client, error handling, JSON parsing
|-- agents/           one file per agent (prompt + token limit)
|-- requirements.txt, .env.example, .gitignore, README.md
```

## 2. Technologies used

This project is built with a lightweight Python stack designed for rapid prototyping:

- Python 3.11+ as the core application language
- Streamlit for the web UI and interactive review workflow
- OpenAI Python SDK to call the LLM through an OpenAI-compatible API
- OpenRouter as the model gateway that provides access to hosted LLMs

This is a simple POC architecture: a Python app, a Streamlit front end, and multiple prompt-driven AI agents coordinated through a single orchestrator.

## 3. Multi-agent explanation

Each agent has one narrow job and one concise system prompt, instead of one generic prompt doing everything.
The **orchestrator** is plain Python: a classifier LLM call chooses which specialists run, then the Senior
Reviewer consolidates their results. An allowed review uses **4 to 6 calls** (guardrail, classifier, BA,
zero to two optional specialists, and Senior Reviewer), plus one call only when a targeted follow-up is triggered.
A blocked request uses one call and skips the remaining workflow. If classifier JSON is unusable, all three
specialists run as a conservative fallback. The LLM is only called when you click
**Start AI Review**; results live in Streamlit `session_state`, so switching tabs never re-calls the LLM.

### Agents used in the demo

| Agent | Demo role | What it returns |
|---|---|---|
| **Guardrail** | Checks whether the submission belongs in the requirement-review workflow. It allows vague or high-risk requirements for further analysis, and blocks clearly unrelated or harmful requests. | An **ALLOW** or **BLOCK** decision with a short category and reason. |
| **Requirement Classifier** | Estimates requirement complexity and chooses whether QA and risk reviews are useful. | Complexity and specialist-routing booleans. |
| **Business Analyst** | Reviews the requirement from a business and scope perspective, calling out unclear actors, rules, inputs, permissions, failure behavior, and outcomes. | Summary, gaps, assumptions, clarification questions, and testable acceptance criteria. |
| **QA Engineer** | Examines whether the requirement can be tested, including normal behavior, negative paths, boundaries, and validation. | Test scenarios, edge cases, and testability gaps. |
| **Risk Reviewer** | Highlights general product and customer-impact risks, such as confusing communication, irreversible actions, or unclear financial impact. This is not a legal or compliance assessment. | Risk level, observations, customer impact, and recommendations. |
| **Senior Reviewer** | Synthesizes the specialist findings into a decision-oriented assessment rather than repeating every observation. | Quality score, readiness status, executive summary, top gaps, recommended clarifications and acceptance criteria, and final recommendation. |

After the Guardrail allows a submission, the selected specialists review the **original requirement independently** and run sequentially. The Senior Reviewer sees the original requirement plus their findings. A `MAJOR GAPS` result, or a mismatch between score and status, triggers one targeted specialist call based on the reported gaps; its findings appear alongside the consolidated assessment without a second Senior Reviewer call.

## 4. Prerequisites

- Python 3.11+
- A free OpenRouter account and API key: https://openrouter.ai/keys

## 5. Setup

```
python -m venv venv
```
Windows: `venv\Scripts\activate`
macOS/Linux: `source venv/bin/activate`

```
pip install -r requirements.txt
```

## 6. OpenRouter configuration

Copy `.env.example` to `.env` (Windows: `copy .env.example .env`, macOS/Linux: `cp .env.example .env`)
and set:

```
OPENROUTER_API_KEY=sk-or-...your key...
```

The default model is `openrouter/free` (OpenRouter's free router). Never commit `.env`.

## 7. Run

```
streamlit run app.py
```

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| "OPENROUTER_API_KEY is missing" | Create `.env` from `.env.example`, add the key, restart Streamlit. |
| "Rate limit reached" | Free tier is limited. Wait a minute, then click Start AI Review again. |
| "Free model unavailable" / HTTP 404/402 | Try again later; optionally set `OPENROUTER_MODEL` in `.env`. Only choose models ending in `:free`. |
| Raw text shown instead of formatted results | The model returned malformed JSON. The app shows the raw output; re-run for cleaner output. |
| `ModuleNotFoundError` | Activate the venv and run `pip install -r requirements.txt`. |

## 9. POC limitations

- Free models vary in quality and may be slow, rate-limited or return malformed JSON.
- Specialists run one after another (not in parallel) to stay within free-tier rate limits.
- No persistence, authentication, or audit trail.
- The Risk Reviewer gives general product-risk observations only, not legal or compliance advice.
- AI output can be wrong; it supports, and does not replace, human review.

## 10. Next enhancement: Retrieval-Augmented Generation (RAG)

Implement RAG to retrieve relevant context from trusted sources such as product documentation, business rules, and approved policies, then provide cited excerpts to the review agents. Protect sensitive data and evaluate retrieval quality and review outcomes before production use. RAG can make findings more specific, but reviewers should verify sources and recommendations because it does not guarantee correctness.