import json
import logging
import random
from typing import Any, Dict, List

from models.schemas import (
    ABTestVariant,
    CampaignStrategy,
    CustomerCohort,
    CustomerSegment,
    SendTimeDecision,
)
from services.llm_service import LLMService

logger = logging.getLogger("campaignx.strategy_agent")


class StrategyAgent:
    """
    Produces a structured CampaignStrategy from a plain-English brief
    and a sample of the customer cohort.
    """

    def __init__(self, llm_service: LLMService) -> None:
        self.llm = llm_service

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def generate(self, brief: str, cohort: CustomerCohort) -> CampaignStrategy:
        sample = random.sample(cohort.data, min(20, len(cohort.data)))
        cohort_summary = {
            "total_count":       cohort.total_count,
            "message":           cohort.message,
            "sample_customers":  sample,
        }

        logger.info(
            "StrategyAgent: generating strategy  total_customers=%s  sample=%d",
            cohort.total_count, len(sample),
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a senior BFSI marketing strategist at SuperBFSI, a leading Indian bank. "
                    "You have deep expertise in Indian consumer banking — fixed deposits, savings accounts, "
                    "credit cards, home loans — and understand how different Indian demographics behave. "
                    "You create precise, data-driven email campaign strategies that are RBI-compliant, "
                    "culturally relevant, and personalised by segment. "
                    "Respond with a single valid JSON object. No prose, no markdown, no code fences."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Campaign brief:\n{brief}\n\n"
                    f"Customer cohort (sample of {len(sample)} from {cohort.total_count} total):\n"
                    f"{json.dumps(cohort_summary, indent=2)}\n\n"

                    "Analyse the sample customers and create a strategy. "
                    "Return JSON with EXACTLY these top-level keys:\n\n"

                    "  objective  — one sharp sentence describing the campaign goal and target outcome.\n\n"

                    "  key_messages  — 4–5 specific, benefit-driven messages. Use real numbers where possible "
                    "(e.g. 'Earn up to 8.5% p.a. on SuperBFSI Fixed Deposits'). Avoid generic phrases.\n\n"

                    "  customer_segments  — array of 3–4 objects, each with:\n"
                    "    id                (string slug, e.g. 'senior_women_60plus')\n"
                    "    name              (short label, e.g. 'Senior Women 60+')\n"
                    "    description       (2–3 sentences: who they are, their financial goals, why this offer fits)\n"
                    "    selection_criteria (object — use actual field names visible in the cohort sample,\n"
                    "                        e.g. {\"age_min\": 60, \"gender\": \"Female\", \"status\": \"active\"})\n"
                    "    estimated_size    (integer — realistic estimate based on total_count proportions)\n\n"
                    "  Segment ideas to consider (use the actual cohort data to decide):\n"
                    "    • Senior citizens 60+ (prefer stability, trust, safety messaging)\n"
                    "    • Young urban professionals 25–35 (growth, returns, digital-first)\n"
                    "    • Tier-2 / Tier-3 city middle income (value, reliability, family security)\n"
                    "    • High-income women (preferential rates, long-term wealth building)\n"
                    "    • Retired / near-retirement 50–60 (capital preservation, regular income)\n\n"

                    "  send_time_decisions  — one object per segment:\n"
                    "    segment_id      (must match a segment id above)\n"
                    "    strategy        (explain WHY this time works for this segment)\n"
                    "    send_window_ist (specific IST window, e.g. '10:00–12:00 IST Tuesday–Thursday')\n"
                    "  Guidelines:\n"
                    "    • Seniors: weekday mornings 9–11am IST (free time, less distracted)\n"
                    "    • Young professionals: weekday evenings 7–9pm IST or weekend mornings\n"
                    "    • Tier-2 cities: afternoon 12–2pm IST (lunch break browsing)\n"
                    "    • High-income: early morning 7–9am IST (before work)\n\n"

                    "  ab_test_plan  — exactly 2 variants testing MEANINGFULLY DIFFERENT approaches:\n"
                    "    id                  (string, e.g. 'v_returns_focus')\n"
                    "    name                (short label)\n"
                    "    hypothesis          (one sentence: 'We believe [segment] will respond better to [approach] because [reason]')\n"
                    "    target_segment_ids  (array of segment ids this variant targets)\n"
                    "    traffic_split       (float — both variants must sum to exactly 1.0)\n"
                    "  A/B test ideas:\n"
                    "    • Variant A: Lead with returns/numbers ('Earn 8.5% p.a.') — rational appeal\n"
                    "    • Variant B: Lead with security/trust ('Your savings, fully protected') — emotional appeal\n"
                    "  Do NOT test minor wording differences — test fundamentally different value propositions.\n\n"

                    "  risk_constraints  — 4–6 specific RBI / SEBI compliance notes for this campaign "
                    "(e.g. 'All interest rates must be marked as indicative and subject to change', "
                    "'No guaranteed returns claims for market-linked products').\n\n"

                    "  explanation  — 3–4 sentences summarising the strategic rationale.\n\n"
                    "  reasoning_log  — object with keys: segmentation_rationale, timing_rationale, ab_rationale.\n\n"

                    "IMPORTANT: traffic_split values across ALL ab_test_plan items must sum to exactly 1.0."
                ),
            },
        ]

        raw = self.llm.chat_json(messages)
        strategy = self._parse(raw)
        logger.info(
            "StrategyAgent: done  segments=%d  ab_variants=%d",
            len(strategy.customer_segments), len(strategy.ab_test_plan),
        )
        return strategy

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _parse(self, d: Dict[str, Any]) -> CampaignStrategy:
        segments = [
            CustomerSegment(
                id=s.get("id", f"seg_{i}"),
                name=s.get("name", ""),
                description=s.get("description", ""),
                selection_criteria=s.get("selection_criteria", {}),
                estimated_size=s.get("estimated_size"),
            )
            for i, s in enumerate(d.get("customer_segments", []))
        ]

        send_times = [
            SendTimeDecision(
                segment_id=st.get("segment_id", ""),
                strategy=st.get("strategy", ""),
                send_window_ist=st.get("send_window_ist"),
            )
            for st in d.get("send_time_decisions", [])
        ]

        ab_plan = [
            ABTestVariant(
                id=v.get("id", f"v_{i}"),
                name=v.get("name", ""),
                hypothesis=v.get("hypothesis", ""),
                target_segment_ids=v.get("target_segment_ids", []),
                traffic_split=float(v.get("traffic_split", 0.5)),
            )
            for i, v in enumerate(d.get("ab_test_plan", []))
        ]

        return CampaignStrategy(
            objective=d.get("objective", ""),
            key_messages=list(d.get("key_messages", [])),
            customer_segments=segments,
            send_time_decisions=send_times,
            ab_test_plan=ab_plan,
            risk_constraints=list(d.get("risk_constraints", [])),
            explanation=d.get("explanation", ""),
            reasoning_log=d.get("reasoning_log", {}),
        )
