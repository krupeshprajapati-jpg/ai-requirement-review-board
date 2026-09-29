"""Thin OpenRouter client (OpenAI-compatible SDK) with call counting and friendly errors."""
import json
import os
import re
import time

from dotenv import load_dotenv
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openrouter/free"


class LLMError(Exception):
    """Friendly error. fatal=True means the remaining calls are pointless (e.g. bad API key)."""

    def __init__(self, message: str, fatal: bool = False):
        super().__init__(message)
        self.fatal = fatal


class LLMClient:
    def __init__(self):
        load_dotenv(override=True)  # re-read .env so key changes are picked up
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not api_key or api_key.startswith("your_"):
            raise LLMError(
                "OPENROUTER_API_KEY is missing. Copy .env.example to .env, add your key, and restart Streamlit.",
                fatal=True,
            )
        self.model = os.getenv("OPENROUTER_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
        # max_retries=0 disables the SDK's hidden automatic retries; we control retries ourselves.
        self.client = OpenAI(base_url=BASE_URL, api_key=api_key, timeout=90.0, max_retries=0)
        self.total_requests = 0      # every HTTP request sent (including the one allowed retry)
        self.successful_calls = 0    # requests that returned usable text
        self.total_tokens = 0

    def chat(self, system_prompt: str, user_message: str, max_tokens: int) -> str:
        """One LLM call. Retries at most once, and only for transient network/server errors."""
        for attempt in range(2):
            self.total_requests += 1
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    max_tokens=max_tokens,
                    temperature=0.2,
                )
                choices = getattr(response, "choices", None)
                text = ((choices[0].message.content or "") if choices else "").strip()
                usage = getattr(response, "usage", None)
                if usage and getattr(usage, "total_tokens", None):
                    self.total_tokens += usage.total_tokens
                if not text:
                    raise LLMError("The model returned an empty response. Please try again.")
                self.successful_calls += 1
                return text
            except LLMError:
                raise
            except AuthenticationError:
                raise LLMError("OpenRouter rejected the API key. Check OPENROUTER_API_KEY in .env.", fatal=True)
            except RateLimitError:
                raise LLMError("Rate limit reached on the free tier. Wait a minute and try again.")
            except (APITimeoutError, APIConnectionError):
                if attempt == 0:
                    time.sleep(2)
                    continue
                raise LLMError("The request timed out or OpenRouter could not be reached. Try again shortly.")
            except APIStatusError as e:
                if e.status_code >= 500 and attempt == 0:
                    time.sleep(2)
                    continue
                if e.status_code in (402, 403, 404):
                    raise LLMError(
                        f"The free model is unavailable or not permitted for this key (HTTP {e.status_code})."
                    )
                raise LLMError(f"OpenRouter returned an error (HTTP {e.status_code}). Try again later.")
            except Exception as e:  # never crash the UI
                raise LLMError(f"Unexpected error while calling the LLM: {type(e).__name__}")
        raise LLMError("The LLM call failed.")  # not reachable, kept for safety


def parse_json(text: str):
    """Best-effort JSON parse. Returns a dict, or None if the text is not usable JSON."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    for candidate in (cleaned, cleaned[cleaned.find("{"): cleaned.rfind("}") + 1]):
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except (ValueError, TypeError):
            continue
    return None
