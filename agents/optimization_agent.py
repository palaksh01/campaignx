import logging
from typing import Any, Dict

from models.schemas import (
    CampaignStrategy,
    ContentGenerationResponse,
    OptimizationResult,
    PerformanceMetrics,
)
from services.llm_service import LLMService


logger = logging.getLogger("campaignx.optimization_agent")


class OptimizationAgent:
    """
    Agent responsible for analyzing performance metrics and proposing an
    improved strategy and content.
    """

    def __init__(self, llm_service: LLMService) -> None:
        self.llm_service = llm_service

    def optimize(
        self,
        metrics: PerformanceMetrics,
        current_strategy: CampaignStrategy,
        current_content: ContentGenerationResponse,
    ) -> OptimizationResult:
        system_prompt = (
            "You are an AI campaign optimizer for SuperBFSI. "
            "You analyze performance metrics (open rate, click rate, micro-segments) "
            "and propose an improved email strategy and content. "
            "You must output JSON only, matching the described schema."
        )

        user_prompt = (
            "Analyze the current campaign and metrics and propose an improved strategy and content.\n\n"
            f"Current strategy JSON:\n{current_strategy.json()}\n\n"
            f"Current content JSON:\n{current_content.json()}\n\n"
            f"Performance metrics JSON:\n{metrics.json()}\n\n"
            "Return a JSON object with keys: improved_strategy, improved_content, explanation, reasoning_log.\n"
            "improved_strategy must match the CampaignStrategy-like structure with the same keys as before.\n"
            "improved_content must match the ContentGenerationResponse-like structure (variants, explanation, reasoning_log).\n"
            "Focus improvements on:\n"
            "- Micro-segments with strong engagement: double down with more relevant messages.\n"
            "- Micro-segments with weak engagement: adjust timing, simplify offers, clarify CTAs.\n"
            "Preserve BFSI compliance and avoid aggressive or misleading language."
        )

        logger.info(
            "Optimizing campaign with metrics open_rate=%.3f click_rate=%.3f",
            metrics.open_rate,
            metrics.click_rate,
        )

        raw = self.llm_service.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_schema_hint="OptimizationResult JSON with improved_strategy and improved_content.",
        )

        logger.debug("Raw optimization JSON: %s", raw)
        result = self._parse_optimization_result(raw)
        logger.info("Optimization produced %d improved variants", len(result.improved_content.variants))
        return result

    def _parse_optimization_result(self, data: Dict[str, Any]) -> OptimizationResult:
        strategy_data: Dict[str, Any] = data.get("improved_strategy", {})
        content_data: Dict[str, Any] = data.get("improved_content", {})

        # Reuse the same structure as CampaignStrategy and ContentGenerationResponse.
        # We use their .parse_obj methods for robust validation.
        improved_strategy = CampaignStrategy.parse_obj(strategy_data)
        improved_content = ContentGenerationResponse.parse_obj(content_data)

        return OptimizationResult(
            improved_strategy=improved_strategy,
            improved_content=improved_content,
            explanation=data.get("explanation", ""),
            reasoning_log=data.get("reasoning_log", {}),
        )


