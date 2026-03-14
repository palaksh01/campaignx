import json
import logging
import os
from typing import Any, Dict, List

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logger = logging.getLogger("campaignx.llm")


class LLMService:
    """
    Thin wrapper around an OpenAI-compatible /chat/completions endpoint.
    Always requests JSON-object responses.
    """

    def __init__(self) -> None:
        self.base_url = os.getenv("LLM_API_BASE_URL", "").strip().rstrip("/")
        self.api_key  = os.getenv("LLM_API_KEY", "").strip()
        self.model    = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile").strip()

        logger.info(
            "LLMService ready — base_url=%s  model=%s  key_present=%s",
            self.base_url, self.model, bool(self.api_key),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat_json(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Call the LLM with *messages* and return the parsed JSON dict.
        Raises on non-200 or unparseable response.
        """
        return self._call(self.model, messages)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type":  "application/json",
        }

    def _call(self, model: str, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        body = {
            "model": model,
            "messages": messages,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }

        print(f"[LLM] → model={model}  url={url}")
        logger.info("LLM request  model=%s", model)

        try:
            resp = requests.post(url, headers=self._headers(), json=body, timeout=200)
        except requests.RequestException as exc:
            logger.error("LLM network error: %s", exc)
            raise

        logger.info("LLM response status=%s", resp.status_code)

        if not resp.ok:
            logger.error("LLM error body: %s", resp.text[:500])
            resp.raise_for_status()

        try:
            data = resp.json()
        except ValueError:
            logger.error("LLM returned non-JSON body: %s", resp.text[:500])
            raise

        raw_content: str = data["choices"][0]["message"]["content"]
        logger.debug("LLM raw content: %s", raw_content[:300])

        try:
            return json.loads(raw_content)
        except json.JSONDecodeError as exc:
            logger.error("Could not parse LLM JSON content: %s\nContent: %s", exc, raw_content[:500])
            raise
