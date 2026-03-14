import logging

import uvicorn
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from models.schemas import (
    CampaignOptimizationResponse,
    CampaignPreviewResponse,
    CampaignScheduleResponse,
)
from services.llm_service import LLMService
from services.campaign_api_service import CampaignAPIService
from agents.strategy_agent import StrategyAgent
from agents.content_agent import ContentAgent
from agents.optimization_agent import OptimizationAgent
from agents.execution_agent import ExecutionAgent


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("campaignx.main")


# ---------------------------------------------------------------------------
# Wire up services and agents
# ---------------------------------------------------------------------------

llm_svc        = LLMService()
campaign_api   = CampaignAPIService()
strategy_agent = StrategyAgent(llm_svc)
content_agent  = ContentAgent(llm_svc)
optim_agent    = OptimizationAgent(llm_svc)
execution      = ExecutionAgent(
    campaign_api=campaign_api,
    strategy_agent=strategy_agent,
    content_agent=content_agent,
    optimization_agent=optim_agent,
)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="CampaignX", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Frontend
# ---------------------------------------------------------------------------

# Mount the frontend folder so any assets (CSS, JS, images) are served at
# /frontend/<filename>. This must be registered AFTER the explicit routes
# to avoid shadowing them.
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")


@app.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse("frontend/index.html")


# ---------------------------------------------------------------------------
# Campaign routes
# ---------------------------------------------------------------------------

class PlanRequest(BaseModel):
    brief: str


@app.post("/campaigns/plan", response_model=CampaignPreviewResponse)
async def plan_campaign(body: PlanRequest):
    try:
        return await execution.plan_campaign(body.brief)
    except Exception as exc:
        logger.exception("plan_campaign failed")
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/campaigns/{campaign_id}/approve", response_model=CampaignScheduleResponse)
async def approve_campaign(campaign_id: str):
    try:
        return await execution.approve_and_schedule(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("approve_campaign failed")
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/campaigns/{campaign_id}/metrics", response_model=CampaignOptimizationResponse)
async def get_metrics(campaign_id: str):
    try:
        return await execution.fetch_metrics_and_optimize(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("get_metrics failed")
        raise HTTPException(status_code=502, detail=str(exc))


@app.post("/campaigns/{campaign_id}/approve-optimized", response_model=CampaignScheduleResponse)
async def approve_optimized(campaign_id: str):
    try:
        return await execution.approve_and_schedule_optimized(campaign_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("approve_optimized failed")
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# Debug routes
# ---------------------------------------------------------------------------

@app.get("/debug/llm_test")
async def debug_llm_test():
    try:
        result = llm_svc.chat_json([
            {"role": "user", "content": 'Reply with {"status": "ok"}'}
        ])
        return {"ok": True, "response": result, "model": llm_svc.model}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "model": llm_svc.model}


@app.get("/debug/api_test")
async def debug_api_test():
    try:
        result = campaign_api.call_operation("fetch_customer_cohort")
        return {
            "ok": True,
            "total_count": result.get("total_count"),
            "sample": result.get("data", [])[:2],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


if __name__ == "__main__":
    # Run with a 120-second timeout so slow LLM + API calls never get cut off.
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        timeout_keep_alive=120,
        timeout_graceful_shutdown=120,
    )
