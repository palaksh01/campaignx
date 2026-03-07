import logging
from typing import Any, Dict

from models.schemas import (
    CampaignStrategy,
    CustomerCohort,
    CustomerSegment,
    SendTimeDecision,
    ABTestVariantPlan,
    StrategyResponse,
)
from services.llm_service import LLMService


logger = logging.getLogger("campaignx.strategy_agent")


class StrategyAgent:
    """
    Agent responsible for turning a natural language brief and a concrete
    customer cohort into a structured campaign strategy.
    """

    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    def generate_strategy(self, brief: str, cohort: CustomerCohort) -> StrategyResponse:
        """
        Accept a brief and customer cohort and return a structured strategy JSON.
        """
        system_prompt = (
            "You are an expert BFSI marketing strategist for a bank called SuperBFSI. "
            "You design safe, compliant email campaigns. "
            "You must respond with a single JSON object matching the described schema. "
            "Do not include any text outside the JSON."
        )

        user_prompt = (
            "Design an email campaign strategy for the following brief and customer cohort.\n\n"
            f"Brief:\n{brief}\n\n"
            f"Customer cohort (JSON):\n{cohort.json()}\n\n"
            "You MUST return JSON with keys: objective, key_messages, customer_segments, "
            "send_time_decisions, ab_test_plan, risk_constraints, explanation, reasoning_log.\n"
            "Each customer_segments item must have: id, name, description, selection_criteria, estimated_size.\n"
            "Each send_time_decisions item must have: segment_id, strategy, send_window_utc (can be null).\n"
            "Each ab_test_plan item must have: id, name, hypothesis, target_segment_ids, traffic_split (0-1).\n"
            "reasoning_log should contain a few short bullet-style strings grouped in a JSON object, "
            "e.g. {\"steps\": [\"step1\", \"step2\"]}."
        )

        logger.info("Generating strategy for cohort %s", cohort.id)

        raw = self.llm_service.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_schema_hint="CampaignStrategy JSON for email campaign.",
        )

        logger.debug("Raw strategy JSON: %s", raw)

        strategy = self._parse_strategy(raw)
        logger.info("Generated strategy with %d segments and %d variants", len(strategy.customer_segments), len(strategy.ab_test_plan))

        return StrategyResponse(strategy=strategy)

    def _parse_strategy(self, data: Dict[str, Any]) -> CampaignStrategy:
        segments = [
            CustomerSegment(
                id=seg["id"],
                name=seg["name"],
                description=seg.get("description", ""),
                selection_criteria=seg.get("selection_criteria", {}),
                estimated_size=seg.get("estimated_size"),
            )
            for seg in data.get("customer_segments", [])
        ]

        send_times = [
            SendTimeDecision(
                segment_id=item["segment_id"],
                strategy=item["strategy"],
                send_window_utc=item.get("send_window_utc"),
            )
            for item in data.get("send_time_decisions", [])
        ]

        ab_plan = [
            ABTestVariantPlan(
                id=item["id"],
                name=item["name"],
                hypothesis=item["hypothesis"],
                target_segment_ids=item.get("target_segment_ids", []),
                traffic_split=float(item.get("traffic_split", 0.5)),
            )
            for item in data.get("ab_test_plan", [])
        ]

        return CampaignStrategy(
            objective=data.get("objective", ""),
            key_messages=list(data.get("key_messages", [])),
            customer_segments=segments,
            send_time_decisions=send_times,
            ab_test_plan=ab_plan,
            risk_constraints=list(data.get("risk_constraints", [])),
            explanation=data.get("explanation", ""),
            reasoning_log=data.get("reasoning_log", {}),
        )


