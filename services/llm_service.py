import json
import logging
import os
from typing import Any, Dict, List

import requests


logger = logging.getLogger("campaignx.llm")


# Best-effort load of .env so LLM_* variables are available even if the app
# did not explicitly call load_dotenv() elsewhere.
try:
    from dotenv import load_dotenv

    load_dotenv()  # type: ignore[func-returns-value]
    logger.info("Loaded environment variables from .env for LLMService.")
except Exception:  # ImportError or any unexpected issue
    logger.info("python-dotenv not available or .env load failed; relying on process env.")


class LLMService:
    """
    Thin wrapper around an OpenAI-compatible chat completion API.

    The service always requests JSON object responses and parses them into Python dicts.
    """

    def __init__(self) -> None:
        self.base_url = os.getenv("LLM_API_BASE_URL", "https://api.openai.com/v1")
        self.api_key = os.getenv("LLM_API_KEY", "")
        self.model = os.getenv("LLM_MODEL", "gpt-4.1-mini")

        logger.info(
            "LLMService configured: base_url=%s model=%s api_key_present=%s",
            self.base_url,
            self.model,
            bool(self.api_key),
        )

    def _headers(self) -> Dict[str, str]:
        auth_value = f"Bearer {self.api_key}" if self.api_key else "Bearer "
        # Log only a prefix of the key for safety.
        key_prefix = (self.api_key[:6] + "...") if self.api_key else "EMPTY"
        logger.info(
            "LLM request headers prepared: Authorization='Bearer %s', Content-Type='application/json'",
            key_prefix,
        )
        return {
            "Authorization": auth_value,
            "Content-Type": "application/json",
        }

    def chat_json(self, messages: List[Dict[str, str]], response_schema_hint: str) -> Dict[str, Any]:
        """
        Call the LLM and expect a strict JSON object in the response.

        response_schema_hint: short natural language description of the JSON structure we expect.
        """
        url = f"{self.base_url}/chat/completions"

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }

        logger.info("Calling LLM with schema hint: %s", response_schema_hint)
        logger.info("LLM request payload: model=%s body=%s", self.model, body)
        try:
            response = requests.post(url, headers=self._headers(), json=body, timeout=60)
        except requests.RequestException as exc:
            logger.error("HTTP request to LLM failed: %s", exc, exc_info=True)
            raise

        logger.info("LLM HTTP response status=%s", response.status_code)
        # Always log the upstream response body (truncated) for debugging.
        logger.info("LLM HTTP response body (first 1000 chars): %s", response.text[:1000])
        if not response.ok:
            # Log the raw body so we can see exact upstream error (e.g. 401 from OpenAI).
            logger.error("LLM error response body: %s", response.text)

        # Differentiate common OpenAI error classes and log them clearly.
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = response.status_code
            body_text = response.text
            if status == 401:
                logger.error("LLM authentication error (401). Check API key and organization. Body: %s", body_text)
            elif status == 400:
                logger.error(
                    "LLM bad request (400). Check request payload, model, and response_format. Body: %s",
                    body_text,
                )
            elif status == 404:
                logger.error("LLM model or endpoint not found (404). Verify model '%s' exists and URL is correct. Body: %s", self.model, body_text)
            elif status == 429:
                logger.error("LLM quota/billing/rate-limit issue (429). Body: %s", body_text)
            else:
                logger.error("LLM HTTP error status=%s body=%s", status, body_text)
            # Log full traceback for deep debugging.
            logger.exception("Traceback for LLM HTTPError: %s", exc)
            raise

        try:
            data = response.json()
        except ValueError as exc:
            logger.error(
                "Failed to decode LLM JSON body. status=%s text=%s error=%s",
                response.status_code,
                response.text,
                exc,
            )
            raise

        content = data["choices"][0]["message"]["content"]
        logger.debug("Raw LLM JSON content: %s", content)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("Failed to parse LLM JSON: %s", exc)
            raise

        return parsed


