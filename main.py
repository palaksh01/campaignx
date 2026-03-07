import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import requests

try:
    # Load .env early so LLM_* variables are available before services initialize.
    from dotenv import load_dotenv

    load_dotenv()  # type: ignore[func-returns-value]
    logging.info("Loaded environment variables from .env in main.py.")
except Exception:
    logging.info("python-dotenv not available or .env load failed in main.py; relying on process env.")

from models.schemas import (
    CampaignPlanRequest,
    CampaignPreviewResponse,
    CampaignScheduleResponse,
    CampaignOptimizationResponse,
)
from agents.strategy_agent import StrategyAgent
from agents.content_agent import ContentAgent
from agents.execution_agent import ExecutionAgent
from agents.optimization_agent import OptimizationAgent
from services.llm_service import LLMService
from services.campaign_api_service import CampaignAPIService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(title="CampaignX API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")


llm_service = LLMService()
campaign_api_service = CampaignAPIService()
strategy_agent = StrategyAgent(llm_service=llm_service)
content_agent = ContentAgent(llm_service=llm_service)
optimization_agent = OptimizationAgent(llm_service=llm_service)
execution_agent = ExecutionAgent(
    campaign_api_service=campaign_api_service,
    strategy_agent=strategy_agent,
    content_agent=content_agent,
    optimization_agent=optimization_agent,
)


@app.get("/")
async def root():
    return {"message": "CampaignX backend is running"}


@app.get("/debug/llm_test")
async def debug_llm_test():
    """
    Minimal upstream LLM connectivity test.

    This bypasses the full campaign flow and hits the configured chat completion
    endpoint with a trivial 'ping' request, returning the status code and a
    truncated copy of the response body for inspection.
    """
    url = f"{llm_service.base_url}/chat/completions"
    body = {
        "model": llm_service.model,
        "messages": [{"role": "user", "content": "ping"}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }

    try:
        resp = requests.post(url, headers=llm_service._headers(), json=body, timeout=30)
        text = resp.text or ""
        return {
            "ok": resp.ok,
            "status": resp.status_code,
            "body": text[:1000],
        }
    except requests.RequestException as exc:
        # In case of network or other issues, surface as much detail as possible.
        status = getattr(exc.response, "status_code", 0) if hasattr(exc, "response") else 0
        text = getattr(exc.response, "text", str(exc)) if hasattr(exc, "response") else str(exc)
        logging.exception("Error during /debug/llm_test LLM call: %s", exc)
        return {
            "ok": False,
            "status": status,
            "body": text[:1000],
        }


@app.post("/campaigns/plan", response_model=CampaignPreviewResponse)
async def plan_campaign(request: CampaignPlanRequest) -> CampaignPreviewResponse:
    """
    Orchestrate initial campaign planning:
    - Fetch cohort from external API
    - Generate strategy
    - Generate content
    - Return preview (not yet scheduled)
    """
    try:
        return await execution_agent.plan_campaign(request)
    except Exception as exc:
        logging.exception("Error while planning campaign.")
        # Return a structured JSON error instead of a generic 500.
        raise HTTPException(
            status_code=502,
            detail={
                "error": "plan_failed",
                "message": "Failed to generate campaign plan. See server logs for upstream error details.",
                "exception_type": exc.__class__.__name__,
            },
        )


@app.post(
    "/campaigns/{campaign_id}/approve-initial",
    response_model=CampaignScheduleResponse,
)
async def approve_initial_campaign(campaign_id: str) -> CampaignScheduleResponse:
    """
    Approve and schedule the initial campaign.
    """
    return await execution_agent.approve_and_schedule_initial(campaign_id)


@app.get(
    "/campaigns/{campaign_id}/metrics",
    response_model=CampaignOptimizationResponse,
)
async def get_campaign_metrics_and_optimize(campaign_id: str) -> CampaignOptimizationResponse:
    """
    Fetch performance metrics and generate an optimized campaign proposal.
    """
    return await execution_agent.fetch_metrics_and_optimize(campaign_id)


@app.post(
    "/campaigns/{campaign_id}/approve-optimized",
    response_model=CampaignScheduleResponse,
)
async def approve_optimized_campaign(campaign_id: str) -> CampaignScheduleResponse:
    """
    Approve and relaunch the optimized campaign.
    """
    return await execution_agent.approve_and_schedule_optimized(campaign_id)


