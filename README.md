# AI Requirement Review Board

Multi-Agent Requirement Quality Analysis
A user enters a software/business requirement. A Guardrail checks whether it belongs in the workflow and
blocks clearly illegal, harmful, or unrelated requests. Three specialist AI agents (Business Analyst, QA
Engineer, Risk Reviewer) review allowed requirements independently, then a Senior Reviewer consolidates
their findings into a quality score, top gaps and a final recommendation.

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
            +----------+----------+
                           |
                     Guardrail
                           |
            +----------+----------+
        |          |          |
     BA Agent   QA Agent   Risk Agent      (each sees the ORIGINAL requirement only)
        |          |          |
        +----------+----------+
                   |
            Senior Reviewer                (sees requirement + 3 findings)
                   |
             Final Report
```

```
ai-requirement-review-board/
|-- app.py            Streamlit UI
|-- orchestrator.py   runs the Guardrail, 3 specialists, then the Senior Reviewer
|-- llm_client.py     OpenRouter client, error handling, JSON parsing
|-- agents/           one file per agent (prompt + token limit)
|-- requirements.txt, .env.example, .gitignore, README.md
```

## 2. Multi-agent explanation

Each agent has one narrow job and one concise system prompt, instead of one generic prompt doing everything.
The **orchestrator** is plain Python: it calls the agents in order and collects the results. Each agent makes
exactly **one** LLM call, so an allowed review uses **5 calls**. A blocked request uses one call and skips
the specialists and Senior Reviewer. The LLM is only called when you click
**Start AI Review**; results live in Streamlit `session_state`, so switching tabs never re-calls the LLM.

### Agents used in the demo

| Agent | Demo role | What it returns |
|---|---|---|
| **Guardrail** | Checks whether the submission belongs in the requirement-review workflow. It allows vague or high-risk requirements for further analysis, and blocks clearly unrelated or harmful requests. | An **ALLOW** or **BLOCK** decision with a short category and reason. |
| **Business Analyst** | Reviews the requirement from a business and scope perspective, calling out unclear actors, rules, inputs, permissions, failure behavior, and outcomes. | Summary, gaps, assumptions, clarification questions, and testable acceptance criteria. |
| **QA Engineer** | Examines whether the requirement can be tested, including normal behavior, negative paths, boundaries, and validation. | Test scenarios, edge cases, and testability gaps. |
| **Risk Reviewer** | Highlights general product and customer-impact risks, such as confusing communication, irreversible actions, or unclear financial impact. This is not a legal or compliance assessment. | Risk level, observations, customer impact, and recommendations. |
| **Senior Reviewer** | Synthesizes the specialist findings into a decision-oriented assessment rather than repeating every observation. | Quality score, readiness status, executive summary, top gaps, recommended clarifications and acceptance criteria, and final recommendation. |

After the Guardrail allows a submission, the three specialists review the **original requirement independently** and run sequentially. The Senior Reviewer then sees the original requirement plus the specialist findings and creates the consolidated report.

## 3. Prerequisites

- Python 3.11+
- A free OpenRouter account and API key: https://openrouter.ai/keys

## 4. Setup

```
python -m venv venv
```
Windows: `venv\Scripts\activate`
macOS/Linux: `source venv/bin/activate`

```
pip install -r requirements.txt
```

## 5. OpenRouter configuration

Copy `.env.example` to `.env` (Windows: `copy .env.example .env`, macOS/Linux: `cp .env.example .env`)
and set:

```
OPENROUTER_API_KEY=sk-or-...your key...
```

The default model is `openrouter/free` (OpenRouter's free router). Never commit `.env`.

## 6. Run

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