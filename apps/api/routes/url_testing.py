"""
TracePlay URL-Based Automated Testing API Routes.
Allows users to submit any website link and immediately run First-Round QA,
Regression Analysis, or Multi-Click Stress Testing.
"""
import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, Field
from apps.api.database import SessionLocal
from apps.api.models import TestRun
from apps.api.services.url_tester import UrlTestConfig, UrlTestRunner

router = APIRouter(prefix="/api/test-url", tags=["url-testing"])

# In-memory store for active job runners and live log feeds
ACTIVE_JOBS: Dict[str, UrlTestRunner] = {}


class UrlTestRequest(BaseModel):
    url: str = Field(..., example="http://localhost:5001")
    test_mode: str = Field("first_round_qa", example="first_round_qa")  # first_round_qa, regression, stress_repeat
    project_name: Optional[str] = None
    baseline_run_id: Optional[str] = None
    enable_multi_click: bool = True
    db_connection_uri: Optional[str] = None
    repo_path: Optional[str] = None


async def run_url_test_task(runner: UrlTestRunner):
    try:
        await runner.execute()
    except Exception as e:
        print(f"Error executing URL test task: {e}")


@router.post("")
async def start_url_test(data: UrlTestRequest, background_tasks: BackgroundTasks):
    url = data.url.strip()
    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    config = UrlTestConfig(
        target_url=url,
        test_mode=data.test_mode,
        project_name=data.project_name,
        baseline_run_id=data.baseline_run_id,
        enable_multi_click=data.enable_multi_click,
        db_connection_uri=data.db_connection_uri,
        repo_path=data.repo_path,
    )

    runner = UrlTestRunner(config)
    ACTIVE_JOBS[runner.run_id] = runner

    # Launch exploration task in background
    background_tasks.add_task(run_url_test_task, runner)

    return {
        "status": "launched",
        "run_id": runner.run_id,
        "target_url": url,
        "test_mode": data.test_mode,
        "message": f"Autonomous test initiated for {url}. Monitoring live interactions...",
    }


@router.get("/{run_id}/status")
def get_url_test_status(run_id: str):
    runner = ACTIVE_JOBS.get(run_id)
    if runner:
        return {
            "run_id": runner.run_id,
            "target_url": runner.config.target_url,
            "status": runner.status,
            "step_index": runner.step_index,
            "logs": runner.logs,
            "captured_requests_count": len(runner.captured_requests),
            "captured_errors_count": len(runner.captured_errors),
        }

    # Query from DB if completed
    db = SessionLocal()
    try:
        run = db.query(TestRun).filter(TestRun.id == run_id).first()
        if not run:
            raise HTTPException(status_code=404, detail="Test run not found")
        return {
            "run_id": run.id,
            "status": run.status,
            "test_mode": run.test_mode,
            "baseline_status": run.baseline_status,
            "started_at": run.started_at,
            "finished_at": run.finished_at,
            "logs": ["Run completed and stored in database."],
        }
    finally:
        db.close()
