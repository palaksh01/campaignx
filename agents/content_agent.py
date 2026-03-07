import logging
from typing import Any, Dict, List

from models.schemas import (
    CampaignStrategy,
    ContentGenerationRequest,
    ContentGenerationResponse,
    EmailVariant,
)
from services.llm_service import LLMService


logger = logging.getLogger("campaignx.content_agent")


class ContentAgent:
    """
    Agent responsible for generating concrete email subject/body variants for
    each segment and A/B test variant in the strategy.
    """

    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    def generate_email_content(self, request: ContentGenerationRequest) -> ContentGenerationResponse:
        strategy: CampaignStrategy = request.strategy

        system_prompt = (
            "You are a senior email copywriter for SuperBFSI, a BFSI company. "
            "You must generate strictly JSON output matching the specified schema. "
            "Do not include any non-JSON text."
        )

        user_prompt = (
            "Generate email subject lines and HTML body content for the campaign strategy below.\n\n"
            f"Brief:\n{request.brief}\n\n"
            f"Strategy JSON:\n{strategy.json()}\n\n"
            "Return a JSON object with keys: variants, explanation, reasoning_log.\n"
            "variants must be a list. Each item must have fields: id, segment_id, name, subject, body_html, rationale.\n"
            "The copy must be compliant and conservative (no misleading promises), and tailored to BFSI customers.\n"
            "Reasoning_log should summarize key choices, e.g. tone, personalization, compliance considerations."
        )

        logger.info("Generating email content for strategy with %d segments", len(strategy.customer_segments))

        raw = self.llm_service.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_schema_hint="ContentGenerationResponse JSON with variants and explanation.",
        )

        logger.debug("Raw content JSON: %s", raw)
        response = self._parse_content_response(raw)
        logger.info("Generated %d email variants", len(response.variants))
        return response

    def _parse_content_response(self, data: Dict[str, Any]) -> ContentGenerationResponse:
        variants_data: List[Dict[str, Any]] = data.get("variants", [])
        variants: List[EmailVariant] = []
        for item in variants_data:
            variants.append(
                EmailVariant(
                    id=item["id"],
                    segment_id=item["segment_id"],
                    name=item.get("name", ""),
                    subject=item["subject"],
                    body_html=item["body_html"],
                    rationale=item.get("rationale", ""),
                )
            )

        return ContentGenerationResponse(
            variants=variants,
            explanation=data.get("explanation", ""),
            reasoning_log=data.get("reasoning_log", {}),
        )


