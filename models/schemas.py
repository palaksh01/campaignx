from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CampaignPhase(str, Enum):
    DRAFT = "draft"
    INITIAL_SCHEDULED = "initial_scheduled"
    OPTIMIZED_DRAFT = "optimized_draft"
    OPTIMIZED_SCHEDULED = "optimized_scheduled"


# ---------------------------------------------------------------------------
# External API shapes
# ---------------------------------------------------------------------------

class CustomerCohort(BaseModel):
    """Raw response from GET /api/v1/get_customer_cohort."""
    data: List[Dict[str, Any]] = Field(default_factory=list)
    message: Optional[str] = None
    response_code: Optional[int] = None
    total_count: Optional[int] = None


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CampaignPlanRequest(BaseModel):
    brief: str = Field(..., description="Natural language campaign brief")


# ---------------------------------------------------------------------------
# Strategy models
# ---------------------------------------------------------------------------

class CustomerSegment(BaseModel):
    id: str
    name: str
    description: str
    selection_criteria: Union[Dict[str, Any], str] = Field(default_factory=dict)
    estimated_size: Optional[int] = None

    @field_validator("selection_criteria", mode="before")
    @classmethod
    def coerce_criteria_to_dict(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, str):
            return {"criteria": v}
        return v


class SendTimeDecision(BaseModel):
    segment_id: str
    strategy: str
    send_window_ist: Optional[str] = None


class ABTestVariant(BaseModel):
    id: str
    name: str
    hypothesis: str
    target_segment_ids: List[str] = Field(default_factory=list)
    traffic_split: float = Field(default=0.5, ge=0.0, le=1.0)


class CampaignStrategy(BaseModel):
    objective: str
    key_messages: List[str] = Field(default_factory=list)
    customer_segments: List[CustomerSegment] = Field(default_factory=list)
    send_time_decisions: List[SendTimeDecision] = Field(default_factory=list)
    ab_test_plan: List[ABTestVariant] = Field(default_factory=list)
    risk_constraints: List[str] = Field(default_factory=list)
    explanation: str = ""
    reasoning_log: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Content models
# ---------------------------------------------------------------------------

class EmailVariant(BaseModel):
    id: str
    segment_id: str
    name: str
    subject: str
    body_html: str
    rationale: str = ""


class EmailContent(BaseModel):
    variants: List[EmailVariant] = Field(default_factory=list)
    explanation: str = ""
    reasoning_log: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Performance / optimization models
# ---------------------------------------------------------------------------

class PerformanceMetrics(BaseModel):
    external_campaign_id: str
    raw_data: List[Dict[str, Any]] = Field(default_factory=list)
    total_rows: Optional[int] = None
    message: Optional[str] = None
    response_code: Optional[int] = None


class OptimizationResult(BaseModel):
    improved_strategy: CampaignStrategy
    improved_content: EmailContent
    explanation: str = ""
    reasoning_log: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Schedule result
# ---------------------------------------------------------------------------

class ScheduleResult(BaseModel):
    external_campaign_id: str
    send_time: str
    raw_response: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# In-memory campaign state
# ---------------------------------------------------------------------------

class CampaignState(BaseModel):
    id: str
    brief: str
    cohort: CustomerCohort
    strategy: CampaignStrategy
    content: EmailContent
    send_time: str
    phase: CampaignPhase = CampaignPhase.DRAFT
    initial_schedule: Optional[ScheduleResult] = None
    latest_metrics: Optional[PerformanceMetrics] = None
    optimized_strategy: Optional[CampaignStrategy] = None
    optimized_content: Optional[EmailContent] = None
    optimized_schedule: Optional[ScheduleResult] = None


# ---------------------------------------------------------------------------
# API response models
# ---------------------------------------------------------------------------

class CampaignPreviewResponse(BaseModel):
    campaign_id: str
    phase: str
    strategy: CampaignStrategy
    content: EmailContent
    cohort_total: Optional[int]
    send_time: str


class CampaignScheduleResponse(BaseModel):
    campaign_id: str
    phase: str
    external_campaign_id: str
    send_time: str


class CampaignOptimizationResponse(BaseModel):
    campaign_id: str
    phase: str
    metrics_summary: Dict[str, Any]
    optimization: OptimizationResult
