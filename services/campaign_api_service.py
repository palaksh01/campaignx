import logging
import os
from typing import Any, Dict

import requests


logger = logging.getLogger("campaignx.campaign_api")


class CampaignAPIService:
    """
    Dynamic wrapper around the external campaign management API.

    Endpoints are defined in a registry so that the execution agent can select
    operations by name instead of hardcoding URLs.
    """

    def __init__(self) -> None:
        self.base_url = os.getenv("CAMPAIGN_API_BASE_URL", "").rstrip("/")
        self.api_key = os.getenv("CAMPAIGN_API_KEY", "")
        # This registry is intentionally simple; it can be populated directly
        # from external API documentation or a config file.
        self._operations: Dict[str, Dict[str, Any]] = {
            "fetch_customer_cohort": {
                "method": "GET",
                "path": "/cohorts/{cohort_id}",
            },
            "schedule_campaign": {
                "method": "POST",
                "path": "/campaigns",
            },
            "fetch_performance_metrics": {
                "method": "GET",
                "path": "/campaigns/{campaign_id}/metrics",
            },
        }

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def call_operation(self, name: str, *, path_params: Dict[str, str] | None = None, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        if not self.base_url:
            # For hackathon/demo use, provide a lightweight mock when no base URL is configured.
            logger.warning("CAMPAIGN_API_BASE_URL not set; returning mock data for operation %s", name)
            return self._mock_operation(name, path_params=path_params, payload=payload)

        op = self._operations.get(name)
        if not op:
            raise ValueError(f"Unknown campaign API operation: {name}")

        path_template = op["path"]
        path_params = path_params or {}
        path = path_template.format(**path_params)

        url = f"{self.base_url}{path}"
        method = op["method"].upper()

        logger.info("Calling campaign API operation %s %s", method, url)
        if method == "GET":
            resp = requests.get(url, headers=self._headers(), params=payload or {}, timeout=30)
        else:
            resp = requests.post(url, headers=self._headers(), json=payload or {}, timeout=30)

        resp.raise_for_status()
        return resp.json()

    def _mock_operation(self, name: str, *, path_params: Dict[str, str] | None, payload: Dict[str, Any] | None) -> Dict[str, Any]:
        path_params = path_params or {}
        if name == "fetch_customer_cohort":
            cohort_id = path_params.get("cohort_id", "demo")
            return {
                "id": cohort_id,
                "name": "Retail Banking Customers - High Value",
                "description": "Demo cohort returned from mock API.",
                "size": 10000,
                "filters": {"product": "credit_card", "region": "urban"},
            }
        if name == "schedule_campaign":
            return {
                "campaign_id": "ext_demo_campaign",
                "status": "scheduled",
            }
        if name == "fetch_performance_metrics":
            campaign_id = path_params.get("campaign_id", "ext_demo_campaign")
            return {
                "campaign_id": campaign_id,
                "open_rate": 0.42,
                "click_rate": 0.11,
                "delivered": 9000,
                "bounced": 1000,
                "micro_segments": [
                    {"name": "Young professionals", "open_rate": 0.55, "click_rate": 0.18},
                    {"name": "Mass affluent", "open_rate": 0.38, "click_rate": 0.09},
                ],
            }
        return {"status": "ok", "operation": name, "payload": payload, "path_params": path_params}


