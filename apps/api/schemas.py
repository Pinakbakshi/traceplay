"""
TracePlay Pydantic Schemas for API Requests, Ingestion, and Reporting.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------- Project & Environment Schemas ---------------- #

class ProjectCreate(BaseModel):
    name: str
    repository_url: Optional[str] = None
    default_branch: str = "main"


class ProjectResponse(BaseModel):
    id: str
    name: str
    repository_url: Optional[str] = None
    default_branch: str
    created_at: datetime

    class Config:
        from_attributes = True


class EnvironmentCreate(BaseModel):
    name: str
    base_url: str
    environment_type: str = "local"
    config_json: Optional[Dict[str, Any]] = None


class EnvironmentResponse(BaseModel):
    id: str
    project_id: str
    name: str
    base_url: str
    environment_type: str
    config_json: str

    class Config:
        from_attributes = True


class ScenarioCreate(BaseModel):
    name: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    tags: str = "smoke"
    enabled: bool = True


class ScenarioResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: Optional[str] = None
    file_path: Optional[str] = None
    tags: str
    enabled: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------- Test Run Schemas ---------------- #

class TestRunCreate(BaseModel):
    project_id: str
    environment_id: Optional[str] = None
    commit_sha: str = "head"
    application_build: str = "1.0.0"
    test_mode: str = "first_round_qa"  # first_round_qa, regression, step_by_step, stress_repeat
    baseline_run_id: Optional[str] = None
    scenario_names: Optional[List[str]] = None


class TestRunResponse(BaseModel):
    id: str
    project_id: str
    environment_id: Optional[str] = None
    commit_sha: str
    application_build: str
    status: str
    test_mode: str
    baseline_run_id: Optional[str] = None
    baseline_status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    comparison_summary_json: Optional[str] = "{}"

    class Config:
        from_attributes = True


# ---------------- Ingestion Schemas ---------------- #

class InteractionRecord(BaseModel):
    id: Optional[str] = None
    step_index: int
    action_label: str
    action_type: str = "click"
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    page_url_before: Optional[str] = None
    page_url_after: Optional[str] = None
    status: str = "passed"
    pause_duration_ms: float = 0.0
    measurement_comparable: bool = True
    evidence_summary: Optional[Dict[str, Any]] = None


class NetworkIngest(BaseModel):
    run_id: str
    interaction_id: Optional[str] = None
    request_id: str
    trace_id: Optional[str] = None
    method: str
    route_template: str
    status_code: int
    duration_ms: float
    request_summary: Optional[Dict[str, Any]] = None
    response_summary: Optional[Dict[str, Any]] = None
    attempt_number: int = 1
    ttfb_ms: Optional[float] = None
    response_completion_ms: float = 0.0


class BackendSpanIngest(BaseModel):
    run_id: str
    interaction_id: Optional[str] = None
    trace_id: str
    span_id: str
    parent_span_id: Optional[str] = None
    service_name: str
    operation_name: str
    status: str = "ok"
    duration_ms: float
    attributes: Optional[Dict[str, Any]] = None


class DataObservationIngest(BaseModel):
    run_id: str
    interaction_id: Optional[str] = None
    verification_rule_id: str
    entity_type: str
    entity_key_hash: str
    snapshot: Dict[str, Any]
    source_kind: str = "read_only_query"


class DataDiffRecord(BaseModel):
    run_id: str
    interaction_id: Optional[str] = None
    entity_type: str
    entity_key_hash: str
    field_name: str
    change_type: str
    before_value: Optional[Any] = None
    after_value: Optional[Any] = None
    expectation_status: str = "EXPECTED_CHANGE"
    causality_status: str = "confirmed"
    evidence: Optional[Dict[str, Any]] = None


class AssertionRecord(BaseModel):
    run_id: str
    interaction_id: Optional[str] = None
    assertion_type: str
    description: str
    expected: Any
    actual: Any
    status: str
    evidence_refs: Optional[Dict[str, Any]] = None


class TimingRecord(BaseModel):
    run_id: str
    interaction_id: Optional[str] = None
    metric_name: str
    duration_ms: float
    measurement_source: str = "browser"
    baseline_duration_ms: Optional[float] = None
    delta_ms: Optional[float] = None
    delta_percent: Optional[float] = None
    threshold_status: str = "pass"
    sample_count: int = 1
    metadata: Optional[Dict[str, Any]] = None


class GraphAnalyzeRequest(BaseModel):
    project_id: str
    commit_sha: str = "head"
    engine: str = "gitnexus"  # gitnexus or graphify
    endpoints: Optional[List[str]] = None
