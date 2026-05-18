"""
src/utils/llm_client.py
=======================
Central LLM utility — every module calls llm_chat() from here.

Features
--------
* Singleton OpenAI client (created once, reused across calls)
* Tenacity retry on transient API errors:
    RateLimitError, APITimeoutError, APIConnectionError, InternalServerError
  — 5 attempts, exponential back-off 4 s -> 60 s
* Single place to change model, temperature defaults, or retry policy

Usage
-----
    from utils.llm_client import llm_chat, get_client

    # Basic call
    text = llm_chat(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        temperature=0.1,
    )

    # Pass an existing client (e.g. created by caller)
    text = llm_chat(messages, temperature=0.2, client=my_client)

    # With token limit
    text = llm_chat(messages, temperature=0.1, max_tokens=3000)

    # For llm_fallback which uses max_completion_tokens
    text = llm_chat(messages, temperature=0.1, max_completion_tokens=4500)
"""

import logging
import os

import openai
from openai import OpenAI
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# ── Singleton client ──────────────────────────────────────────────────────────
_client: OpenAI | None = None


def get_client() -> OpenAI:
    """Return the shared OpenAI client, creating it on first call."""
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.environ["TF_API_KEY"],
            base_url=os.environ["TF_BASE_URL"],
            timeout=120.0,  # 2 min per request; tenacity retries on APITimeoutError
        )
    return _client


# ── Retry-wrapped raw API call ────────────────────────────────────────────────
@retry(
    retry=retry_if_exception_type((
        openai.RateLimitError,
        openai.APITimeoutError,
        openai.APIConnectionError,
        openai.InternalServerError,
    )),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(5),
    reraise=True,
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
def _call_with_retry(client: OpenAI, **kwargs) -> str:
    response = client.chat.completions.create(**kwargs)
    content = response.choices[0].message.content
    if not content:
        raise ValueError(
            f"Empty LLM response (finish_reason={response.choices[0].finish_reason})"
        )
    return content


# ── Public interface ──────────────────────────────────────────────────────────
def llm_chat(
    messages: list[dict],
    *,
    temperature: float = 0.1,
    max_tokens: int | None = None,
    max_completion_tokens: int | None = None,
    client: OpenAI | None = None,
) -> str:
    """
    Make an LLM chat call with automatic retry on transient errors.

    Parameters
    ----------
    messages              : OpenAI messages list [{"role": ..., "content": ...}]
    temperature           : Sampling temperature (default 0.1)
    max_tokens            : Hard token limit for response (optional)
    max_completion_tokens : Alias used by some callers (optional, takes precedence)
    client                : OpenAI client to use; falls back to shared singleton

    Returns
    -------
    str — response content, stripped of leading/trailing whitespace

    Raises
    ------
    openai.RateLimitError / APITimeoutError / APIConnectionError / InternalServerError
        after 5 failed attempts (reraise=True).
    ValueError
        if the API returns an empty response.
    """
    c = client or get_client()
    model = os.environ.get("TF_MODEL", "internal-bedrock/sonnet-46")

    kwargs: dict = dict(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    if max_completion_tokens is not None:
        kwargs["max_completion_tokens"] = max_completion_tokens
    elif max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    return _call_with_retry(c, **kwargs).strip()
