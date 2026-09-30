# AI Requirement Review Board

Multi-Agent Requirement Quality Analysis
A user enters a software/business requirement. A Guardrail checks whether it belongs in the workflow and
blocks clearly illegal, harmful, or unrelated requests. An LLM Orchestrator Planner chooses an ordered subset of
the Business Analyst, QA Engineer, and Risk Reviewer for each requirement. If the planner call fails or returns
invalid routing data, local fallback rules select reviewers. A Senior Reviewer consolidates the selected findings.
Major gaps or an inconsistent score/status trigger one targeted specialist follow-up.

> **Security / data privacy warning**
> This POC sends requirement text to a third-party LLM provider. Do not submit confidential company information, customer PII, credentials, production data, or other sensitive information unless use of the provider has been approved by your organization.
> The Guardrail is also an LLM call, so it does not prevent the submitted text from reaching that provider and is not a substitute for organizational policy or legal review.

## 1. Architecture

```
                  USER
                   |
             Requirement Input
                   |                   |
              Guardrail
                   |
           Guardrail allows?
             /         \
          no             yes
          |               |
        Stop        OrchestratorPlannerAgent
                       /           \
                    valid       failed/invalid
                     |                |
               PlannerSelection  FallbackRules
                     \                /
               OrderedSpecialistSelection
                    /       |       \
                   BA      QA      Risk
                    \       |       /
                     SeniorReviewer
                          |
       Major gaps OR score mismatch OR fallback?
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
|-- orchestrator.py   plans/falls back on specialist routing, retrieves context, consolidates findings, and conditionally follows up
|-- retriever.py      local TF-IDF retrieval over the synthetic knowledge base
|-- knowledge_base/   synthetic glossary, review guidance, risk patterns, and past reviews
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
- scikit-learn for local TF-IDF similarity search over reference snippets

This is a simple POC architecture: a Python app, a Streamlit front end, multiple prompt-driven AI agents, and local retrieval coordinated through a single orchestrator. Retrieval uses no external service or API.

## 3. Multi-agent explanation

Each agent has one narrow job and one concise system prompt, instead of one generic prompt doing everything.
The **orchestrator** uses a short planner LLM call to choose which specialists run and in what order, then the
Senior Reviewer consolidates their results. An allowed review uses **5 to 7 calls** (guardrail, planner, one to
three selected specialists, and Senior Reviewer), plus one call only when a targeted follow-up is triggered.
A blocked request uses one call and skips the remaining workflow. If the planner call fails or its JSON or agent
list is invalid, local fallback rules select the specialists instead; a planner failure never blocks a review.
The LLM is only called when you click
**Start AI Review**; results live in Streamlit `session_state`, so switching tabs never re-calls the LLM.

### Agents used in the demo

| Agent | Demo role | What it returns |
|---|---|---|
| **Guardrail** | Checks whether the submission belongs in the requirement-review workflow. It allows vague or high-risk requirements for further analysis, and blocks clearly unrelated or harmful requests. | An **ALLOW** or **BLOCK** decision with a short category and reason. |
| **Orchestrator Planner** | Selects the relevant reviewers for each requirement and determines their execution order. | An ordered list of specialist agent keys and a short explanation. |
| **Business Analyst** | Reviews the requirement from a business and scope perspective, calling out unclear actors, rules, inputs, permissions, failure behavior, and outcomes. | Summary, gaps, assumptions, clarification questions, and testable acceptance criteria. |
| **QA Engineer** | Examines whether the requirement can be tested, including normal behavior, negative paths, boundaries, and validation. | Test scenarios, edge cases, and testability gaps. |
| **Risk Reviewer** | Highlights general product and customer-impact risks, such as confusing communication, irreversible actions, or unclear financial impact. This is not a legal or compliance assessment. | Risk level, observations, customer impact, and recommendations. |
| **Senior Reviewer** | Synthesizes the specialist findings into a decision-oriented assessment rather than repeating every observation. | Quality score, readiness status, executive summary, top gaps, recommended clarifications and acceptance criteria, final recommendation, and a targeted follow-up decision. |

After the Guardrail allows a submission, the planner selects an ordered subset of the three specialists. They review the **original requirement independently** and run sequentially in that order. Specialists omitted by the planner are marked as skipped, and the Senior Reviewer receives both the selected specialists' findings and the orchestrator's reason for skipping the others. The Senior Reviewer decides whether a targeted follow-up is needed and selects the specialist based on the reported gaps. If the Senior Reviewer call fails or returns an unusable follow-up decision, the orchestrator falls back to one targeted specialist call based on the requirement and successful specialist findings. Follow-up findings appear alongside the consolidated assessment without a second Senior Reviewer call.

Before each BA, QA, or Risk prompt, the orchestrator retrieves up to two relevant snippets from that agent's local reference files. The Senior Reviewer receives up to two similar synthetic past-review examples for score calibration. A targeted follow-up receives context for its specialist as well. TF-IDF and cosine similarity run entirely in the app process; retrieval adds no LLM calls or external API calls, and irrelevant matches below the similarity threshold are omitted. Guardrail and planner prompts do not use retrieved context; the planner receives only the requirement text to keep its call small and inexpensive.

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

## 10. Local retrieval (RAG)

The demo includes a small synthetic knowledge base in `knowledge_base/`: a glossary, requirement-quality guidance, general product-risk patterns, and four past-review examples. `retriever.py` reads these files once at import time and uses scikit-learn's `TfidfVectorizer` and cosine similarity to select a small amount of context for relevant prompts. It makes no network calls and does not change the number of LLM calls. The examples are for demonstration and calibration only; replace them with approved, maintained reference material and evaluate retrieval quality before production use. Reviewers should verify retrieved context and recommendations because retrieval does not guarantee correctness.