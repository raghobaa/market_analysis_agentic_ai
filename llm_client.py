"""
Thin wrapper around the Groq API for the two LLM tasks in this pipeline:
  1. Selecting the pricing URL from a list of mapped URLs (Sub-Agent 1)
  2. Reasoning over pricing diffs / writing the final brief (Sub-Agent 2, Master Agent)

Includes basic retry logic since LLM calls can transiently fail (rate limits,
timeouts) and we don't want a single blip to kill the whole pipeline run.
"""

import json
import time
from typing import Optional

from groq import Groq, GroqError

import config
from logger_config import get_logger

logger = get_logger(__name__)

_client: Optional[Groq] = None

MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 2


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


def call_llm(system_prompt: str, user_prompt: str, json_mode: bool = False) -> dict:
    """
    Calls Groq's chat completion endpoint.

    Returns:
        {"status": "success", "text": "..."} always for non-json_mode,
        {"status": "success", "data": {...}} for json_mode on successful parse,
        {"status": "error", "error": "..."} on failure after retries.
    """
    client = _get_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    kwargs = {
        "model": config.GROQ_MODEL,
        "messages": messages,
        "temperature": 0.2,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.debug(f"LLM call attempt {attempt}/{MAX_RETRIES} (json_mode={json_mode})")
            response = client.chat.completions.create(**kwargs)
            text = response.choices[0].message.content

            if not text or not text.strip():
                raise ValueError("LLM returned empty content")

            if json_mode:
                try:
                    data = json.loads(text)
                    return {"status": "success", "data": data}
                except json.JSONDecodeError as e:
                    raise ValueError(f"LLM did not return valid JSON: {e}")

            return {"status": "success", "text": text}

        except (GroqError, ValueError) as e:
            last_error = str(e)
            logger.error(f"LLM call attempt {attempt} failed: {e}")
            # 404 model_not_found is a permanent error — retrying won't help
            if isinstance(e, GroqError) and getattr(e, 'status_code', None) == 404:
                logger.error("LLM model not found (404) — check GROQ_MODEL in .env. Not retrying.")
                break
            
            # 400 json_validate_failed: retry without response_format and parse JSON manually
            if json_mode and "json_validate_failed" in str(e).lower():
                logger.warning("Groq API json_validate_failed — attempting manual JSON mode fallback without response_format constraint.")
                try:
                    fallback_kwargs = dict(kwargs)
                    fallback_kwargs.pop("response_format", None)
                    res = client.chat.completions.create(**fallback_kwargs)
                    raw_text = res.choices[0].message.content or ""
                    import re
                    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    if match:
                        data = json.loads(match.group(0))
                        logger.info("Successfully extracted JSON via fallback parser.")
                        return {"status": "success", "data": data}
                except Exception as fallback_err:
                    logger.error(f"Manual JSON fallback failed: {fallback_err}")

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    logger.error(f"LLM call failed after {MAX_RETRIES} attempts: {last_error}", exc_info=True)
    return {"status": "error", "error": last_error}
