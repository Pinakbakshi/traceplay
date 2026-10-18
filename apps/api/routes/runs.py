"""
TracePlay Test Run Lifecycle and Inspection API Routes.
"""
import json
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from apps.api.database import get_db
from apps.api.models import (
    TestRun,
    Interaction,
    NetworkEvent,
    BackendSpan,
    DataDiff,
    Assertion,
    TimingObservation,
    RegressionDifference,
    GraphEvidence,
)
from apps.api.schemas import TestRunCreate, TestRunResponse
from apps.api.services.traceability_graph import TraceabilityGraphBuilder
from apps.api.services.report_generator import ReportGenerator

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.post("", response_model=TestRunResponse)
def create_run(data: TestRunCreate, db: Session = Depends(get_db)):
    baseline_status = "none"
    baseline_id = data.baseline_run_id

    # If in regression mode, ensure a baseline exists
    if data.test_mode == "regression" and not baseline_id:
        approved_baseline = (
            db.query(TestRun)
            .filter(TestRun.project_id == data.project_id, TestRun.baseline_status == "approved")
            .order_by(TestRun.started_at.desc())
            .first()
        )
        if approved_baseline:
            baseline_id = approved_baseline.id
            baseline_status = "approved"
        else:
            # Cannot run regression without approved baseline! Spec Section 21
            raise HTTPException(
                status_code=400,
                detail="No approved baseline found for this project. Run First-Round QA first and approve a baseline.",
            )
    elif data.test_mode == "first_round_qa":
        baseline_status = "candidate"

    run = TestRun(
        project_id=data.project_id,
        environment_id=data.environment_id,
        commit_sha=data.commit_sha,
        application_build=data.application_build,
        test_mode=data.test_mode,
        baseline_run_id=baseline_id,
        baseline_status=baseline_status,
        status="running",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


@router.get("", response_model=List[TestRunResponse])
def list_runs(project_id: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(TestRun)
    if project_id:
        query = query.filter(TestRun.project_id == project_id)
    return query.order_by(TestRun.started_at.desc()).all()


@router.get("/{run_id}", response_model=TestRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/timeline")
def get_run_timeline(run_id: str, db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    interactions = (
        db.query(Interaction)
        .filter(Interaction.run_id == run_id)
        .order_by(Interaction.step_index.asc())
        .all()
    )
    return [
        {
            "id": i.id,
            "step_index": i.step_index,
            "action_label": i.action_label,
            "action_type": i.action_type,
            "started_at": i.started_at,
            "finished_at": i.finished_at,
            "page_url_before": i.page_url_before,
            "page_url_after": i.page_url_after,
            "status": i.status,
            "pause_duration_ms": i.pause_duration_ms,
            "measurement_comparable": i.measurement_comparable,
            "network_events_count": len(i.network_events),
            "backend_spans_count": len(i.backend_spans),
            "data_diffs_count": len(i.data_diffs),
            "assertions_count": len(i.assertions),
        }
        for i in interactions
    ]


@router.get("/{run_id}/diffs")
def get_run_diffs(run_id: str, db: Session = Depends(get_db)):
    diffs = db.query(DataDiff).filter(DataDiff.run_id == run_id).all()
    return [
        {
            "id": d.id,
            "interaction_id": d.interaction_id,
            "entity_type": d.entity_type,
            "entity_key_hash": d.entity_key_hash,
            "field_name": d.field_name,
            "change_type": d.change_type,
            "before_value_redacted": d.before_value_redacted,
            "after_value_redacted": d.after_value_redacted,
            "expectation_status": d.expectation_status,
            "causality_status": d.causality_status,
            "evidence": json.loads(d.evidence_json or "{}"),
        }
        for d in diffs
    ]


@router.get("/{run_id}/timings")
def get_run_timings(run_id: str, db: Session = Depends(get_db)):
    timings = db.query(TimingObservation).filter(TimingObservation.run_id == run_id).all()
    return [
        {
            "id": t.id,
            "interaction_id": t.interaction_id,
            "metric_name": t.metric_name,
            "duration_ms": t.duration_ms,
            "baseline_duration_ms": t.baseline_duration_ms,
            "delta_ms": t.delta_ms,
            "delta_percent": t.delta_percent,
            "threshold_status": t.threshold_status,
            "measurement_source": t.measurement_source,
        }
        for t in timings
    ]


@router.get("/{run_id}/comparison")
def get_run_comparison(run_id: str, db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    differences = (
        db.query(RegressionDifference)
        .filter(RegressionDifference.run_id == run_id)
        .all()
    )
    return {
        "run_id": run.id,
        "baseline_run_id": run.baseline_run_id,
        "baseline_status": run.baseline_status,
        "differences_count": len(differences),
        "differences": [
            {
                "id": diff.id,
                "difference_type": diff.difference_type,
                "severity": diff.severity,
                "classification_reason": diff.classification_reason,
                "baseline_value": json.loads(diff.baseline_value_json or "{}"),
                "current_value": json.loads(diff.current_value_json or "{}"),
                "delta": json.loads(diff.delta_json or "{}"),
            }
            for diff in differences
        ],
    }


@router.get("/{run_id}/graph")
def get_run_graph(run_id: str, db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    interactions = [
        {"id": i.id, "step_index": i.step_index, "action_label": i.action_label, "action_type": i.action_type}
        for i in db.query(Interaction).filter(Interaction.run_id == run_id).all()
    ]
    network_events = [
        {
            "id": n.id,
            "request_id": n.request_id,
            "interaction_id": n.interaction_id,
            "trace_id": n.trace_id,
            "method": n.method,
            "route_template": n.route_template,
            "status_code": n.status_code,
        }
        for n in db.query(NetworkEvent).filter(NetworkEvent.run_id == run_id).all()
    ]
    backend_spans = [
        {
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "trace_id": s.trace_id,
            "service_name": s.service_name,
            "operation_name": s.operation_name,
        }
        for s in db.query(BackendSpan).filter(BackendSpan.run_id == run_id).all()
    ]
    data_diffs = [
        {
            "id": d.id,
            "interaction_id": d.interaction_id,
            "entity_type": d.entity_type,
            "field_name": d.field_name,
            "change_type": d.change_type,
            "causality_status": d.causality_status,
        }
        for d in db.query(DataDiff).filter(DataDiff.run_id == run_id).all()
    ]
    assertions = [
        {"id": a.id, "interaction_id": a.interaction_id, "description": a.description, "status": a.status}
        for a in db.query(Assertion).filter(Assertion.run_id == run_id).all()
    ]

    graph_evidence_records = db.query(GraphEvidence).filter(GraphEvidence.run_id == run_id).all()
    static_paths = []
    for g in graph_evidence_records:
        try:
            static_paths.extend(json.loads(g.path_json or "[]"))
        except Exception:
            pass

    builder = TraceabilityGraphBuilder(run_id=run.id, commit_sha=run.commit_sha)
    return builder.build_from_run(
        interactions=interactions,
        network_events=network_events,
        backend_spans=backend_spans,
        data_diffs=data_diffs,
        assertions=assertions,
        static_graph_paths=static_paths,
    )


@router.get("/{run_id}/report")
def get_run_report(run_id: str, format: str = Query("json", enum=["json", "html", "markdown"]), db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    interactions = [
        {"id": i.id, "step_index": i.step_index, "action_label": i.action_label, "action_type": i.action_type, "status": i.status, "page_url_before": i.page_url_before, "page_url_after": i.page_url_after}
        for i in db.query(Interaction).filter(Interaction.run_id == run_id).all()
    ]
    network_events = [
        {"id": n.id, "method": n.method, "route_template": n.route_template, "status_code": n.status_code, "duration_ms": n.duration_ms, "trace_id": n.trace_id}
        for n in db.query(NetworkEvent).filter(NetworkEvent.run_id == run_id).all()
    ]
    backend_spans = [
        {"span_id": s.span_id, "service_name": s.service_name, "operation_name": s.operation_name, "duration_ms": s.duration_ms, "status": s.status}
        for s in db.query(BackendSpan).filter(BackendSpan.run_id == run_id).all()
    ]
    data_diffs = [
        {"id": d.id, "entity_type": d.entity_type, "field_name": d.field_name, "change_type": d.change_type, "expectation_status": d.expectation_status, "causality_status": d.causality_status, "before_value_redacted": d.before_value_redacted, "after_value_redacted": d.after_value_redacted}
        for d in db.query(DataDiff).filter(DataDiff.run_id == run_id).all()
    ]
    assertions = [
        {"id": a.id, "description": a.description, "status": a.status, "assertion_type": a.assertion_type}
        for a in db.query(Assertion).filter(Assertion.run_id == run_id).all()
    ]
    timings = [
        {"metric_name": t.metric_name, "duration_ms": t.duration_ms, "baseline_duration_ms": t.baseline_duration_ms, "delta_ms": t.delta_ms, "delta_percent": t.delta_percent, "threshold_status": t.threshold_status, "measurement_source": t.measurement_source}
        for t in db.query(TimingObservation).filter(TimingObservation.run_id == run_id).all()
    ]
    regressions = [
        {"difference_type": r.difference_type, "severity": r.severity, "classification_reason": r.classification_reason, "delta_json": r.delta_json}
        for r in db.query(RegressionDifference).filter(RegressionDifference.run_id == run_id).all()
    ]

    graph_data = get_run_graph(run_id, db)

    report_dict = ReportGenerator.generate_json_report(
        run={"id": run.id, "status": run.status, "test_mode": run.test_mode, "commit_sha": run.commit_sha, "application_build": run.application_build, "baseline_status": run.baseline_status, "baseline_run_id": run.baseline_run_id},
        interactions=interactions,
        network_events=network_events,
        backend_spans=backend_spans,
        data_diffs=data_diffs,
        assertions=assertions,
        timings=timings,
        regressions=regressions,
        graph_data=graph_data,
    )

    if format == "html":
        html_content = ReportGenerator.generate_html_report(report_dict)
        return Response(content=html_content, media_type="text/html")
    elif format == "markdown":
        md_content = ReportGenerator.generate_markdown_report(report_dict)
        return Response(content=md_content, media_type="text/markdown")
    else:
        return report_dict


@router.post("/{run_id}/pause")
def pause_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run.status = "paused"
    db.commit()
    return {"status": "paused", "run_id": run.id}


@router.post("/{run_id}/resume")
def resume_run(run_id: str, db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    run.status = "running"
    db.commit()
    return {"status": "resumed", "run_id": run.id}


@router.post("/{run_id}/retry-step")
def retry_step(run_id: str, step_index: int = Query(...), db: Session = Depends(get_db)):
    inter = (
        db.query(Interaction)
        .filter(Interaction.run_id == run_id, Interaction.step_index == step_index)
        .first()
    )
    if not inter:
        raise HTTPException(status_code=404, detail="Interaction step not found")
    return {
        "status": "ready_for_retry",
        "step_index": step_index,
        "run_id": run_id,
        "new_attempt_id": f"attempt_{int(datetime.utcnow().timestamp())}",
    }
