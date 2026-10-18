"""
TracePlay Evidence Ingestion API Routes.
Ingests network events, backend spans, data observations, and assertion records.
Applies redaction and sanitization before persistence.
"""
import json
from datetime import datetime
from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from apps.api.database import get_db
from apps.api.models import (
    TestRun,
    Interaction,
    NetworkEvent,
    BackendSpan,
    DataObservation,
    DataDiff,
    Assertion,
    TimingObservation,
    RegressionDifference,
)
from apps.api.schemas import (
    InteractionRecord,
    NetworkIngest,
    BackendSpanIngest,
    DataObservationIngest,
    DataDiffRecord,
    AssertionRecord,
    TimingRecord,
)
from apps.api.services.redaction import default_redactor
from apps.api.services.regression_engine import RegressionEngine

router = APIRouter(prefix="/api/evidence", tags=["evidence"])


@router.post("/interactions")
def ingest_interaction(run_id: str, data: InteractionRecord, db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    interaction = Interaction(
        id=data.id,
        run_id=run_id,
        step_index=data.step_index,
        action_label=data.action_label,
        action_type=data.action_type,
        started_at=data.started_at,
        finished_at=data.finished_at or datetime.utcnow(),
        page_url_before=data.page_url_before,
        page_url_after=data.page_url_after,
        status=data.status,
        pause_duration_ms=data.pause_duration_ms,
        measurement_comparable=data.measurement_comparable,
        evidence_summary_json=json.dumps(default_redactor.sanitize_payload(data.evidence_summary or {})),
    )
    db.add(interaction)
    db.commit()
    db.refresh(interaction)
    return {"status": "ok", "interaction_id": interaction.id}


@router.post("/network")
def ingest_network(data: NetworkIngest, db: Session = Depends(get_db)):
    clean_req = default_redactor.sanitize_payload(data.request_summary or {})
    clean_resp = default_redactor.sanitize_payload(data.response_summary or {})

    net = NetworkEvent(
        run_id=data.run_id,
        interaction_id=data.interaction_id,
        request_id=data.request_id,
        trace_id=data.trace_id,
        method=data.method,
        route_template=data.route_template,
        status_code=data.status_code,
        duration_ms=data.duration_ms,
        request_summary_json=json.dumps(clean_req),
        response_summary_json=json.dumps(clean_resp),
        attempt_number=data.attempt_number,
        ttfb_ms=data.ttfb_ms,
        response_completion_ms=data.response_completion_ms,
    )
    db.add(net)
    db.commit()
    return {"status": "ok", "network_event_id": net.id}


@router.post("/spans")
def ingest_spans(data: BackendSpanIngest, db: Session = Depends(get_db)):
    clean_attrs = default_redactor.sanitize_payload(data.attributes or {})

    span = BackendSpan(
        run_id=data.run_id,
        interaction_id=data.interaction_id,
        trace_id=data.trace_id,
        span_id=data.span_id,
        parent_span_id=data.parent_span_id,
        service_name=data.service_name,
        operation_name=data.operation_name,
        status=data.status,
        duration_ms=data.duration_ms,
        attributes_json=json.dumps(clean_attrs),
    )
    db.add(span)
    db.commit()
    return {"status": "ok", "span_id": span.id}


@router.post("/data-observations")
def ingest_observation(data: DataObservationIngest, db: Session = Depends(get_db)):
    clean_snapshot = default_redactor.sanitize_snapshot(data.snapshot)

    obs = DataObservation(
        run_id=data.run_id,
        interaction_id=data.interaction_id,
        verification_rule_id=data.verification_rule_id,
        entity_type=data.entity_type,
        entity_key_hash=data.entity_key_hash,
        snapshot_json=json.dumps(clean_snapshot),
        source_kind=data.source_kind,
    )
    db.add(obs)
    db.commit()
    return {"status": "ok", "observation_id": obs.id}


@router.post("/diffs")
def ingest_diff(data: DataDiffRecord, db: Session = Depends(get_db)):
    b_val = data.before_value
    a_val = data.after_value
    if isinstance(b_val, (dict, list)):
        b_val = json.dumps(default_redactor.sanitize_payload(b_val))
    elif b_val is not None:
        b_val = str(b_val).strip('"')
    if isinstance(a_val, (dict, list)):
        a_val = json.dumps(default_redactor.sanitize_payload(a_val))
    elif a_val is not None:
        a_val = str(a_val).strip('"')

    diff = DataDiff(
        run_id=data.run_id,
        interaction_id=data.interaction_id,
        entity_type=data.entity_type,
        entity_key_hash=data.entity_key_hash,
        field_name=data.field_name,
        change_type=data.change_type,
        before_value_redacted=b_val,
        after_value_redacted=a_val,
        expectation_status=data.expectation_status,
        causality_status=data.causality_status,
        evidence_json=json.dumps(data.evidence or {}),
    )
    db.add(diff)
    db.commit()
    return {"status": "ok", "diff_id": diff.id}


@router.post("/assertions")
def ingest_assertion(data: AssertionRecord, db: Session = Depends(get_db)):
    assertion = Assertion(
        run_id=data.run_id,
        interaction_id=data.interaction_id,
        assertion_type=data.assertion_type,
        description=data.description,
        expected_json=json.dumps(default_redactor.sanitize_payload(data.expected)),
        actual_json=json.dumps(default_redactor.sanitize_payload(data.actual)),
        status=data.status,
        evidence_refs_json=json.dumps(data.evidence_refs or {}),
    )
    db.add(assertion)
    db.commit()
    return {"status": "ok", "assertion_id": assertion.id}


@router.post("/timings")
def ingest_timing(data: TimingRecord, db: Session = Depends(get_db)):
    timing = TimingObservation(
        run_id=data.run_id,
        interaction_id=data.interaction_id,
        metric_name=data.metric_name,
        duration_ms=data.duration_ms,
        measurement_source=data.measurement_source,
        baseline_duration_ms=data.baseline_duration_ms,
        delta_ms=data.delta_ms,
        delta_percent=data.delta_percent,
        threshold_status=data.threshold_status,
        sample_count=data.sample_count,
        metadata_json=json.dumps(data.metadata or {}),
    )
    db.add(timing)
    db.commit()
    return {"status": "ok", "timing_id": timing.id}


@router.post("/complete-run")
def complete_run(run_id: str, status: str = "passed", db: Session = Depends(get_db)):
    run = db.query(TestRun).filter(TestRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    run.status = status
    run.finished_at = datetime.utcnow()

    # If this run has a baseline, execute regression analysis
    if run.baseline_run_id:
        baseline = db.query(TestRun).filter(TestRun.id == run.baseline_run_id).first()
        if baseline:
            c_events = [{"method": e.method, "route_template": e.route_template} for e in run.network_events]
            b_events = [{"method": e.method, "route_template": e.route_template} for e in baseline.network_events]

            c_diffs = [
                {"entity_type": d.entity_type, "field_name": d.field_name, "expectation_status": d.expectation_status, "after_value_redacted": d.after_value_redacted}
                for d in run.data_diffs
            ]
            b_diffs = [
                {"entity_type": d.entity_type, "field_name": d.field_name, "expectation_status": d.expectation_status, "after_value_redacted": d.after_value_redacted}
                for d in baseline.data_diffs
            ]

            c_timings = [{"metric_name": t.metric_name, "duration_ms": t.duration_ms} for t in run.timings]
            b_timings = [{"metric_name": t.metric_name, "duration_ms": t.duration_ms} for t in baseline.timings]

            c_assertions = [{"description": a.description, "status": a.status} for a in run.assertions]
            b_assertions = [{"description": a.description, "status": a.status} for a in baseline.assertions]

            regressions = RegressionEngine.compare_runs(
                current_run={"id": run.id},
                baseline_run={"id": baseline.id},
                current_events=c_events,
                baseline_events=b_events,
                current_diffs=c_diffs,
                baseline_diffs=b_diffs,
                current_timings=c_timings,
                baseline_timings=b_timings,
                current_assertions=c_assertions,
                baseline_assertions=b_assertions,
            )

            for reg in regressions:
                r_diff = RegressionDifference(
                    run_id=run.id,
                    baseline_run_id=baseline.id,
                    difference_type=reg["difference_type"],
                    severity=reg["severity"],
                    baseline_value_json=reg["baseline_value_json"],
                    current_value_json=reg["current_value_json"],
                    delta_json=reg["delta_json"],
                    evidence_refs_json=reg.get("evidence_refs_json", "{}"),
                    classification_reason=reg["classification_reason"],
                )
                db.add(r_diff)

            # If critical regression found, mark run as failed
            critical_regs = [r for r in regressions if r.get("severity") == "critical"]
            if critical_regs:
                run.status = "failed"

    db.commit()
    db.refresh(run)
    return {"status": run.status, "run_id": run.id}
