import logging
import os
import time
from typing import Any, Dict, Optional

import requests
from requests.exceptions import ChunkedEncodingError, ConnectionError, Timeout

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

logger = logging.getLogger("campaignx.campaign_api")

# HTTP status codes that should never be retried — the caller made a bad request.
_NO_RETRY_STATUSES = {401, 403, 404, 422}

_MAX_RETRIES  = 3
_RETRY_DELAY  = 2   # seconds between attempts
_TIMEOUT      = 30  # seconds per request


class CampaignAPIService:
    """
    Dynamic wrapper around the CampaignX external API.

    All callable operations are declared in a registry (_ops). Agents select
    operations by name — no agent ever hardcodes a URL or HTTP method.
    Transient failures (connection errors, timeouts, 5xx) are retried up to
    _MAX_RETRIES times with a fixed delay between attempts.
    """

    _ops: Dict[str, Dict[str, str]] = {
        "fetch_customer_cohort": {
            "method": "GET",
            "path":   "/api/v1/get_customer_cohort",
        },
        "send_campaign": {
            "method": "POST",
            "path":   "/api/v1/send_campaign",
        },
        "get_report": {
            "method": "GET",
            "path":   "/api/v1/get_report",
        },
    }

    def __init__(self) -> None:
        self.base_url = os.getenv("CAMPAIGN_API_BASE_URL", "").strip().rstrip("/")
        self.api_key  = os.getenv("CAMPAIGN_API_KEY", "").strip()

        logger.info(
            "CampaignAPIService ready — base_url=%s  key_present=%s",
            self.base_url, bool(self.api_key),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def call_operation(
        self,
        name: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a named operation from the registry.

        For GET operations *payload* is forwarded as query-string params.
        For POST operations *payload* is sent as a JSON body.
        Retries up to _MAX_RETRIES times on transient failures.
        """
        op = self._ops.get(name)
        if op is None:
            raise ValueError(f"Unknown operation: '{name}'. Known: {list(self._ops)}")

        if not self.base_url:
            logger.warning("CAMPAIGN_API_BASE_URL not set — returning mock for '%s'", name)
            return self._mock(name, payload)

        url    = f"{self.base_url}{op['path']}"
        method = op["method"].upper()

        logger.info("CampaignAPI  %s %s  payload=%s", method, url, payload)

        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = self._send(method, url, payload)
            except (ConnectionError, Timeout, ChunkedEncodingError) as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "CampaignAPI transient error on '%s' (attempt %d/%d): %s — retrying in %ds",
                        name, attempt, _MAX_RETRIES, exc, _RETRY_DELAY,
                    )
                    time.sleep(_RETRY_DELAY)
                    continue
                logger.error(
                    "CampaignAPI failed for '%s' after %d attempts: %s",
                    name, _MAX_RETRIES, exc,
                )
                raise

            logger.info(
                "CampaignAPI response status=%s for '%s' (attempt %d)",
                resp.status_code, name, attempt,
            )

            # Don't retry on client errors — surface immediately.
            if resp.status_code in _NO_RETRY_STATUSES:
                logger.error(
                    "CampaignAPI non-retryable error %s for '%s': %s",
                    resp.status_code, name, resp.text[:500],
                )
                resp.raise_for_status()

            # Retry on 5xx.
            if resp.status_code >= 500:
                last_exc = requests.HTTPError(
                    f"Server error {resp.status_code}", response=resp
                )
                if attempt < _MAX_RETRIES:
                    logger.warning(
                        "CampaignAPI server error %s for '%s' (attempt %d/%d) — retrying in %ds",
                        resp.status_code, name, attempt, _MAX_RETRIES, _RETRY_DELAY,
                    )
                    time.sleep(_RETRY_DELAY)
                    continue
                logger.error(
                    "CampaignAPI server error for '%s' after %d attempts. Last status=%s body=%s",
                    name, _MAX_RETRIES, resp.status_code, resp.text[:500],
                )
                resp.raise_for_status()

            # Any other non-2xx (e.g. 400) — raise immediately, no retry.
            if not resp.ok:
                logger.error(
                    "CampaignAPI error %s for '%s': %s",
                    resp.status_code, name, resp.text[:500],
                )
                resp.raise_for_status()

            return resp.json()

        # Should never reach here, but keeps type-checker happy.
        if last_exc:
            raise last_exc
        raise RuntimeError(f"CampaignAPI call_operation('{name}') exhausted retries with no result")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send(
        self,
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]],
    ) -> requests.Response:
        if method == "GET":
            return requests.get(
                url,
                headers=self._headers(),
                params=payload or {},
                timeout=_TIMEOUT,
            )
        return requests.post(
            url,
            headers=self._headers(),
            json=payload or {},
            timeout=_TIMEOUT,
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-API-Key":    self.api_key,
        }

    def _mock(self, name: str, payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Lightweight mock used when no base URL is configured."""
        if name == "fetch_customer_cohort":
            return {
                "data": [
                    {"customer_id": f"cust_{i:03d}", "name": f"Customer {i}",
                     "age": 30 + i, "city": "Mumbai", "status": "active"}
                    for i in range(1, 6)
                ],
                "total_count": 5,
                "message": "mock",
                "response_code": 200,
            }
        if name == "send_campaign":
            return {"campaign_id": "mock_campaign_001"}
        if name == "get_report":
            cid = (payload or {}).get("campaign_id", "mock_campaign_001")
            return {
                "campaign_id": cid,
                "data": [
                    {"customer_id": "cust_001", "opened": True,  "clicked": True},
                    {"customer_id": "cust_002", "opened": True,  "clicked": False},
                    {"customer_id": "cust_003", "opened": False, "clicked": False},
                ],
                "total_rows": 3,
                "message": "mock",
                "response_code": 200,
            }
        return {"status": "ok", "operation": name}
