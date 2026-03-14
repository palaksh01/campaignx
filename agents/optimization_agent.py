import json
import logging
from typing import Any, Dict

from models.schemas import (
    CampaignStrategy,
    EmailContent,
    EmailVariant,
    OptimizationResult,
    PerformanceMetrics,
)
from services.llm_service import LLMService

logger = logging.getLogger("campaignx.optimization_agent")


class OptimizationAgent:
    """
    Analyses post-send performance metrics and produces an improved strategy
    and new email content for the follow-up campaign wave.
    """

    def __init__(self, llm_service: LLMService) -> None:
        self.llm = llm_service

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def optimize(
        self,
        metrics: PerformanceMetrics,
        strategy: CampaignStrategy,
        content: EmailContent,
    ) -> OptimizationResult:
        opened  = sum(1 for r in metrics.raw_data if r.get("opened"))
        clicked = sum(1 for r in metrics.raw_data if r.get("clicked"))
        total   = len(metrics.raw_data) or 1
        open_rate  = opened  / total
        click_rate = clicked / total

        logger.info(
            "OptimizationAgent: metrics  total=%d  open_rate=%.2f  click_rate=%.2f",
            total, open_rate, click_rate,
        )

        # Only send the 20 rows most useful for analysis; keep payload small
        sample_rows = [
            {"customer_id": r.get("customer_id", ""), "opened": r.get("opened", False), "clicked": r.get("clicked", False)}
            for r in metrics.raw_data[:20]
        ]

        metrics_summary = {
            "total": total,
            "open_rate":  round(open_rate, 4),
            "click_rate": round(click_rate, 4),
            "sample":     sample_rows,
        }

        strategy_summary = {
            "objective": strategy.objective,
            "segments": [
                {"id": s.id, "name": s.name, "description": s.description}
                for s in strategy.customer_segments
            ],
            "ab_variants": [
                {"id": v.id, "name": v.name, "hypothesis": v.hypothesis}
                for v in strategy.ab_test_plan
            ],
        }

        content_summary = [
            {"id": v.id, "segment_id": v.segment_id, "subject": v.subject}
            for v in content.variants
        ]

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an email campaign optimizer for SuperBFSI (Indian bank). "
                    "Given metrics, improve strategy and write better emails. "
                    "Reply with a single JSON object only — no markdown, no prose."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Metrics: {json.dumps(metrics_summary)}\n\n"
                    f"Strategy: {json.dumps(strategy_summary)}\n\n"
                    f"Current emails: {json.dumps(content_summary)}\n\n"
                    "Return JSON with exactly these keys:\n"
                    "  improved_strategy — same schema as strategy above (add key_messages, risk_constraints, send_time_decisions arrays)\n"
                    "  improved_content  — {variants, explanation, reasoning_log}\n"
                    "    Each variant: id, segment_id, name, subject (≤60 chars), body_html (full HTML ≤5000 chars), rationale\n"
                    "    CTA must link to https://superbfsi.com/xdeposit/explore/\n"
                    "  explanation   — what changed and why (1–2 sentences)\n"
                    "  reasoning_log — object\n\n"
                    "Improve subjects/framing for low-engagement segments. Keep RBI-compliant language."
                ),
            },
        ]

        raw = self.llm.chat_json(messages)
        result = self._parse(raw)
        logger.info(
            "OptimizationAgent: done  improved_variants=%d",
            len(result.improved_content.variants),
        )
        return result

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _parse(self, d: Dict[str, Any]) -> OptimizationResult:
        from agents.strategy_agent import StrategyAgent
        from agents.content_agent import ContentAgent

        strat_data    = d.get("improved_strategy", {})
        content_data  = d.get("improved_content", {})

        # Re-use the same robust parsers from the other agents
        improved_strategy = StrategyAgent(self.llm)._parse(strat_data)

        variants = [
            EmailVariant(
                id=v.get("id", ""),
                segment_id=v.get("segment_id", ""),
                name=v.get("name", ""),
                subject=str(v.get("subject", ""))[:200],
                body_html=str(v.get("body_html", ""))[:5000],
                rationale=v.get("rationale", ""),
            )
            for v in content_data.get("variants", [])
        ]
        improved_content = EmailContent(
            variants=variants,
            explanation=content_data.get("explanation", ""),
            reasoning_log=content_data.get("reasoning_log", {}),
        )

        return OptimizationResult(
            improved_strategy=improved_strategy,
            improved_content=improved_content,
            explanation=d.get("explanation", ""),
            reasoning_log=d.get("reasoning_log", {}),
        )
