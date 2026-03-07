from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Channel(str, Enum):
    EMAIL = "email"


class CustomerCohort(BaseModel):
    id: str = Field(..., description="Identifier of the customer cohort in the external system")
    name: Optional[str] = None
    description: Optional[str] = None
    size: Optional[int] = None
    filters: Optional[Dict[str, Any]] = None


class CampaignPlanRequest(BaseModel):
    brief: str = Field(..., description="Natural language description of the campaign goal and constraints")
    cohort_id: str = Field(..., description="External customer cohort identifier to target")


class CustomerSegment(BaseModel):
    id: str
    name: str
    description: str
    selection_criteria: Dict[str, Any]
    estimated_size: Optional[int] = None


class SendTimeDecision(BaseModel):
    segment_id: str
    strategy: str = Field(
        ...,
        description="High-level send time strategy for the segment (e.g., 'weekday mornings for working professionals')",
    )
    send_window_utc: Optional[str] = Field(
        None,
        description="Optional ISO 8601-like description of the send window, e.g. '2026-03-01T08:00:00Z/2026-03-01T11:00:00Z'",
    )


class ABTestVariantPlan(BaseModel):
    id: str
    name: str
    hypothesis: str
    target_segment_ids: List[str]
    traffic_split: float = Field(..., ge=0.0, le=1.0)


class CampaignStrategy(BaseModel):
    objective: str
    key_messages: List[str]
    customer_segments: List[CustomerSegment]
    send_time_decisions: List[SendTimeDecision]
    ab_test_plan: List[ABTestVariantPlan]
    risk_constraints: List[str] = Field(
        default_factory=list,
        description="Compliance and risk considerations, especially important for BFSI.",
    )
    explanation: str = Field(
        ...,
        description="Human-readable explanation of why this strategy was chosen.",
    )
    reasoning_log: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured reasoning used by the agent, for auditability.",
    )


class StrategyResponse(BaseModel):
    strategy: CampaignStrategy


class EmailVariant(BaseModel):
    id: str
    segment_id: str
    name: str
    subject: str
    body_html: str
    rationale: str


class ContentGenerationRequest(BaseModel):
    brief: str
    strategy: CampaignStrategy


class ContentGenerationResponse(BaseModel):
    channel: Channel = Channel.EMAIL
    variants: List[EmailVariant]
    explanation: str
    reasoning_log: Dict[str, Any] = Field(default_factory=dict)


class CampaignPreviewResponse(BaseModel):
    campaign_id: str
    cohort: CustomerCohort
    strategy: CampaignStrategy
    content: ContentGenerationResponse
    explanation: str
    audit_log: Dict[str, Any] = Field(default_factory=dict)


class ExternalScheduleResult(BaseModel):
    external_campaign_id: str
    status: str
    raw_response: Dict[str, Any] = Field(default_factory=dict)


class CampaignScheduleResponse(BaseModel):
    campaign_id: str
    phase: str
    schedule_result: ExternalScheduleResult
    explanation: str


class PerformanceMetrics(BaseModel):
    external_campaign_id: str
    open_rate: float = Field(..., ge=0.0, le=1.0)
    click_rate: float = Field(..., ge=0.0, le=1.0)
    delivered: Optional[int] = None
    bounced: Optional[int] = None
    micro_segments: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Optional raw micro-segmentation data from the external system.",
    )
    raw_response: Dict[str, Any] = Field(default_factory=dict)


class OptimizationResult(BaseModel):
    improved_strategy: CampaignStrategy
    improved_content: ContentGenerationResponse
    explanation: str
    reasoning_log: Dict[str, Any] = Field(default_factory=dict)


class CampaignOptimizationResponse(BaseModel):
    campaign_id: str
    metrics: PerformanceMetrics
    optimization: OptimizationResult


class CampaignPhase(str, Enum):
    DRAFT = "draft"
    INITIAL_SCHEDULED = "initial_scheduled"
    OPTIMIZED_DRAFT = "optimized_draft"
    OPTIMIZED_SCHEDULED = "optimized_scheduled"


class CampaignState(BaseModel):
    id: str
    brief: str
    cohort: CustomerCohort
    strategy: CampaignStrategy
    content: ContentGenerationResponse
    phase: CampaignPhase = CampaignPhase.DRAFT
    initial_schedule: Optional[ExternalScheduleResult] = None
    optimized_strategy: Optional[CampaignStrategy] = None
    optimized_content: Optional[ContentGenerationResponse] = None
    optimized_schedule: Optional[ExternalScheduleResult] = None
    latest_metrics: Optional[PerformanceMetrics] = None


