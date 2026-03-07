import logging
import uuid
from typing import Dict

from models.schemas import (
    CampaignOptimizationResponse,
    CampaignPhase,
    CampaignPlanRequest,
    CampaignPreviewResponse,
    CampaignScheduleResponse,
    CampaignState,
    CampaignStrategy,
    ContentGenerationRequest,
    ContentGenerationResponse,
    CustomerCohort,
    ExternalScheduleResult,
    PerformanceMetrics,
)
from services.campaign_api_service import CampaignAPIService
from .strategy_agent import StrategyAgent
from .content_agent import ContentAgent
from .optimization_agent import OptimizationAgent


logger = logging.getLogger("campaignx.execution_agent")


class ExecutionAgent:
    """
    Orchestrates calls between agents and the external campaign API.

    It maintains a simple in-memory store of campaigns for the duration of the
    process. In a production system this would be replaced with a database.
    """

    def __init__(
        self,
        campaign_api_service: CampaignAPIService,
        strategy_agent: StrategyAgent,
        content_agent: ContentAgent,
        optimization_agent: OptimizationAgent,
    ) -> None:
        self.campaign_api_service = campaign_api_service
        self.strategy_agent = strategy_agent
        self.content_agent = content_agent
        self.optimization_agent = optimization_agent
        self._campaigns: Dict[str, CampaignState] = {}

    async def plan_campaign(self, request: CampaignPlanRequest) -> CampaignPreviewResponse:
        logger.info("Planning campaign for cohort_id=%s", request.cohort_id)

        cohort_raw = self.campaign_api_service.call_operation(
            "fetch_customer_cohort",
            path_params={"cohort_id": request.cohort_id},
        )
        cohort = CustomerCohort.parse_obj(cohort_raw)

        strategy_resp = self.strategy_agent.generate_strategy(
            brief=request.brief,
            cohort=cohort,
        )
        strategy: CampaignStrategy = strategy_resp.strategy

        content_req = ContentGenerationRequest(brief=request.brief, strategy=strategy)
        content: ContentGenerationResponse = self.content_agent.generate_email_content(content_req)

        campaign_id = str(uuid.uuid4())
        state = CampaignState(
            id=campaign_id,
            brief=request.brief,
            cohort=cohort,
            strategy=strategy,
            content=content,
        )
        self._campaigns[campaign_id] = state

        explanation = "Initial campaign plan generated. Awaiting human approval before scheduling."
        audit_log = {
            "cohort_source": "campaign_api_service.fetch_customer_cohort",
            "strategy_agent": "StrategyAgent.generate_strategy",
            "content_agent": "ContentAgent.generate_email_content",
        }

        logger.info("Planned campaign %s", campaign_id)

        return CampaignPreviewResponse(
            campaign_id=campaign_id,
            cohort=cohort,
            strategy=strategy,
            content=content,
            explanation=explanation,
            audit_log=audit_log,
        )

    async def approve_and_schedule_initial(self, campaign_id: str) -> CampaignScheduleResponse:
        state = self._require_campaign(campaign_id)
        logger.info("Approving and scheduling initial campaign %s", campaign_id)

        payload = {
            "name": f"SuperBFSI Campaign {campaign_id}",
            "cohort_id": state.cohort.id,
            "channel": "email",
            "strategy": state.strategy.dict(),
            "content": state.content.dict(),
        }
        raw = self.campaign_api_service.call_operation(
            "schedule_campaign",
            payload=payload,
        )

        schedule_result = ExternalScheduleResult(
            external_campaign_id=raw.get("campaign_id", f"mock-{campaign_id}"),
            status=raw.get("status", "scheduled"),
            raw_response=raw,
        )
        state.initial_schedule = schedule_result
        state.phase = CampaignPhase.INITIAL_SCHEDULED

        logger.info(
            "Initial campaign %s scheduled as external_campaign_id=%s",
            campaign_id,
            schedule_result.external_campaign_id,
        )

        return CampaignScheduleResponse(
            campaign_id=campaign_id,
            phase=state.phase.value,
            schedule_result=schedule_result,
            explanation="Initial campaign scheduled in external system.",
        )

    async def fetch_metrics_and_optimize(self, campaign_id: str) -> CampaignOptimizationResponse:
        state = self._require_campaign(campaign_id)
        if not state.initial_schedule:
            raise ValueError("Campaign must be scheduled before fetching metrics.")

        ext_id = state.initial_schedule.external_campaign_id
        logger.info("Fetching performance metrics for external_campaign_id=%s", ext_id)

        metrics_raw = self.campaign_api_service.call_operation(
            "fetch_performance_metrics",
            path_params={"campaign_id": ext_id},
        )

        metrics = PerformanceMetrics(
            external_campaign_id=metrics_raw.get("campaign_id", ext_id),
            open_rate=float(metrics_raw.get("open_rate", 0.0)),
            click_rate=float(metrics_raw.get("click_rate", 0.0)),
            delivered=metrics_raw.get("delivered"),
            bounced=metrics_raw.get("bounced"),
            micro_segments=metrics_raw.get("micro_segments"),
            raw_response=metrics_raw,
        )
        state.latest_metrics = metrics

        optimization = self.optimization_agent.optimize(
            metrics=metrics,
            current_strategy=state.strategy,
            current_content=state.content,
        )

        state.optimized_strategy = optimization.improved_strategy
        state.optimized_content = optimization.improved_content
        state.phase = CampaignPhase.OPTIMIZED_DRAFT

        logger.info(
            "Optimization complete for campaign %s; phase=%s",
            campaign_id,
            state.phase.value,
        )

        return CampaignOptimizationResponse(
            campaign_id=campaign_id,
            metrics=metrics,
            optimization=optimization,
        )

    async def approve_and_schedule_optimized(self, campaign_id: str) -> CampaignScheduleResponse:
        state = self._require_campaign(campaign_id)
        if not state.optimized_strategy or not state.optimized_content:
            raise ValueError("Campaign must be optimized before scheduling optimized version.")

        logger.info("Approving and scheduling optimized campaign %s", campaign_id)

        payload = {
            "name": f"SuperBFSI Optimized Campaign {campaign_id}",
            "cohort_id": state.cohort.id,
            "channel": "email",
            "strategy": state.optimized_strategy.dict(),
            "content": state.optimized_content.dict(),
            "previous_campaign_id": state.initial_schedule.external_campaign_id if state.initial_schedule else None,
        }
        raw = self.campaign_api_service.call_operation(
            "schedule_campaign",
            payload=payload,
        )

        schedule_result = ExternalScheduleResult(
            external_campaign_id=raw.get("campaign_id", f"mock-optimized-{campaign_id}"),
            status=raw.get("status", "scheduled"),
            raw_response=raw,
        )
        state.optimized_schedule = schedule_result
        state.phase = CampaignPhase.OPTIMIZED_SCHEDULED

        logger.info(
            "Optimized campaign %s scheduled as external_campaign_id=%s",
            campaign_id,
            schedule_result.external_campaign_id,
        )

        return CampaignScheduleResponse(
            campaign_id=campaign_id,
            phase=state.phase.value,
            schedule_result=schedule_result,
            explanation="Optimized campaign scheduled in external system.",
        )

    def _require_campaign(self, campaign_id: str) -> CampaignState:
        state = self._campaigns.get(campaign_id)
        if not state:
            raise ValueError(f"Unknown campaign_id: {campaign_id}")
        return state


