"""
TracePlay Baseline Management API Routes.
Manages candidate baseline review and approval workflow.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from apps.api.database import get_db
from apps.api.models import TestRun

router = APIRouter(prefix="/api/runs", tags=["baseline"])


@router.post("/{run_id}/approve-baseline")
def approve_baseline(run_id: str, db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status != "passed":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot approve a non-passing run (status: '{run.status}') as baseline",
        )

    # Retire previous approved baselines for this project
    previous_baselines = (
        db.query(TestRun)
        .filter(TestRun.project_id == run.project_id, TestRun.baseline_status == "approved")
        .all()
    )
    for prev in previous_baselines:
        prev.baseline_status = "stale"

    run.baseline_status = "approved"
    db.commit()
    db.refresh(run)

    return {
        "status": "approved",
        "run_id": run.id,
        "project_id": run.project_id,
        "commit_sha": run.commit_sha,
        "message": f"Run {run.id[:8]} approved as official baseline for regression comparisons.",
    }
