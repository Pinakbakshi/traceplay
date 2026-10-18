"""
TracePlay Core Database Models (SQLAlchemy).
Supports SQLite for seamless zero-dependency local execution, and PostgreSQL for enterprise deployments.
"""
import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    repository_url = Column(String(512), nullable=True)
    default_branch = Column(String(100), default="main")
    created_at = Column(DateTime, default=datetime.utcnow)

    environments = relationship("Environment", back_populates="project", cascade="all, delete-orphan")
    scenarios = relationship("TestScenario", back_populates="project", cascade="all, delete-orphan")
    runs = relationship("TestRun", back_populates="project", cascade="all, delete-orphan")


class Environment(Base):
    __tablename__ = "environments"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    name = Column(String(100), nullable=False)
    base_url = Column(String(512), nullable=False)
    environment_type = Column(String(50), default="local")  # local, test, staging, production
    config_json = Column(Text, default="{}")

    project = relationship("Project", back_populates="environments")
    runs = relationship("TestRun", back_populates="environment")


class TestScenario(Base):
    __tablename__ = "test_scenarios"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    file_path = Column(String(512), nullable=True)
    tags = Column(String(255), default="smoke")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="scenarios")
    interactions = relationship("Interaction", back_populates="scenario")


class TestRun(Base):
    __tablename__ = "test_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    environment_id = Column(String(36), ForeignKey("environments.id"), nullable=True)
    commit_sha = Column(String(100), default="head")
    application_build = Column(String(100), default="1.0.0")
    status = Column(String(50), default="running")  # queued, running, passed, failed, paused
    test_mode = Column(String(50), default="first_round_qa")  # first_round_qa, regression, step_by_step, stress_repeat
    baseline_run_id = Column(String(36), nullable=True)
    baseline_status = Column(String(50), default="none")  # none, candidate, approved, stale, not_comparable
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    playwright_version = Column(String(50), default="1.60.0")
    graph_engine_versions = Column(String(100), default="gitnexus:1.2.0,graphify:2.0.0")
    graph_index_commit = Column(String(100), default="head")
    config_snapshot_hash = Column(String(100), nullable=True)
    comparison_summary_json = Column(Text, default="{}")
    environment_fingerprint_json = Column(Text, default="{}")
    timing_policy_version = Column(String(50), default="1.0")

    project = relationship("Project", back_populates="runs")
    environment = relationship("Environment", back_populates="runs")
    interactions = relationship("Interaction", back_populates="run", cascade="all, delete-orphan")
    network_events = relationship("NetworkEvent", back_populates="run", cascade="all, delete-orphan")
    backend_spans = relationship("BackendSpan", back_populates="run", cascade="all, delete-orphan")
    data_observations = relationship("DataObservation", back_populates="run", cascade="all, delete-orphan")
    data_diffs = relationship("DataDiff", back_populates="run", cascade="all, delete-orphan")
    assertions = relationship("Assertion", back_populates="run", cascade="all, delete-orphan")
    graph_evidence = relationship("GraphEvidence", back_populates="run", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="run", cascade="all, delete-orphan")
    timings = relationship("TimingObservation", back_populates="run", cascade="all, delete-orphan")
    regression_differences = relationship("RegressionDifference", back_populates="run", cascade="all, delete-orphan")


class Interaction(Base):
    __tablename__ = "interactions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    scenario_id = Column(String(36), ForeignKey("test_scenarios.id"), nullable=True)
    step_index = Column(Integer, default=0)
    action_label = Column(String(255), nullable=False)
    action_type = Column(String(100), default="click")  # click, fill, navigate, assert, repeat_click
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    page_url_before = Column(String(512), nullable=True)
    page_url_after = Column(String(512), nullable=True)
    status = Column(String(50), default="passed")  # passed, failed, paused
    evidence_summary_json = Column(Text, default="{}")
    action_sequence_id = Column(String(100), nullable=True)
    parent_interaction_id = Column(String(36), nullable=True)
    pause_duration_ms = Column(Float, default=0.0)
    measurement_comparable = Column(Boolean, default=True)

    run = relationship("TestRun", back_populates="interactions")
    scenario = relationship("TestScenario", back_populates="interactions")
    network_events = relationship("NetworkEvent", back_populates="interaction")
    backend_spans = relationship("BackendSpan", back_populates="interaction")
    data_diffs = relationship("DataDiff", back_populates="interaction")
    assertions = relationship("Assertion", back_populates="interaction")


class NetworkEvent(Base):
    __tablename__ = "network_events"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    interaction_id = Column(String(36), ForeignKey("interactions.id"), nullable=True)
    request_id = Column(String(100), nullable=False)
    trace_id = Column(String(100), nullable=True)
    method = Column(String(10), nullable=False)
    route_template = Column(String(512), nullable=False)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Float, default=0.0)
    request_summary_json = Column(Text, default="{}")
    response_summary_json = Column(Text, default="{}")
    attempt_number = Column(Integer, default=1)
    retry_reason = Column(String(255), nullable=True)
    queue_wait_ms = Column(Float, nullable=True)
    ttfb_ms = Column(Float, nullable=True)
    response_completion_ms = Column(Float, default=0.0)

    run = relationship("TestRun", back_populates="network_events")
    interaction = relationship("Interaction", back_populates="network_events")


class BackendSpan(Base):
    __tablename__ = "backend_spans"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    interaction_id = Column(String(36), ForeignKey("interactions.id"), nullable=True)
    trace_id = Column(String(100), nullable=False)
    span_id = Column(String(100), nullable=False)
    parent_span_id = Column(String(100), nullable=True)
    service_name = Column(String(100), nullable=False)
    operation_name = Column(String(255), nullable=False)
    status = Column(String(50), default="ok")  # ok, error
    duration_ms = Column(Float, default=0.0)
    attributes_json = Column(Text, default="{}")

    run = relationship("TestRun", back_populates="backend_spans")
    interaction = relationship("Interaction", back_populates="backend_spans")


class DataObservation(Base):
    __tablename__ = "data_observations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    interaction_id = Column(String(36), ForeignKey("interactions.id"), nullable=True)
    verification_rule_id = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_key_hash = Column(String(100), nullable=False)
    observed_at = Column(DateTime, default=datetime.utcnow)
    snapshot_json = Column(Text, default="{}")
    source_kind = Column(String(50), default="read_only_query")

    run = relationship("TestRun", back_populates="data_observations")


class DataDiff(Base):
    __tablename__ = "data_diffs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    interaction_id = Column(String(36), ForeignKey("interactions.id"), nullable=True)
    observation_before_id = Column(String(36), nullable=True)
    observation_after_id = Column(String(36), nullable=True)
    entity_type = Column(String(100), nullable=False)
    entity_key_hash = Column(String(100), nullable=False)
    field_name = Column(String(100), nullable=False)
    change_type = Column(String(50), nullable=False)  # ADDED, REMOVED, CHANGED, UNCHANGED, UNEXPECTED_CHANGE, EXPECTED_CHANGE, NOT_VERIFIABLE
    before_value_redacted = Column(Text, nullable=True)
    after_value_redacted = Column(Text, nullable=True)
    expectation_status = Column(String(50), default="EXPECTED_CHANGE")  # EXPECTED_CHANGE, UNEXPECTED_CHANGE, FORBIDDEN_CHANGE_DETECTED, UNCHANGED_AS_EXPECTED
    causality_status = Column(String(50), default="confirmed")  # confirmed, temporally_correlated, causality_unconfirmed
    evidence_json = Column(Text, default="{}")

    run = relationship("TestRun", back_populates="data_diffs")
    interaction = relationship("Interaction", back_populates="data_diffs")


class Assertion(Base):
    __tablename__ = "assertions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    interaction_id = Column(String(36), ForeignKey("interactions.id"), nullable=True)
    assertion_type = Column(String(100), nullable=False)  # ui_visibility, expected_change, forbidden_change, timing_threshold, request_contract
    description = Column(String(512), nullable=False)
    expected_json = Column(Text, default="{}")
    actual_json = Column(Text, default="{}")
    status = Column(String(50), default="passed")  # passed, failed, warn
    evidence_refs_json = Column(Text, default="{}")

    run = relationship("TestRun", back_populates="assertions")
    interaction = relationship("Interaction", back_populates="assertions")


class GraphEvidence(Base):
    __tablename__ = "graph_evidence"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    interaction_id = Column(String(36), ForeignKey("interactions.id"), nullable=True)
    engine = Column(String(50), default="gitnexus")  # gitnexus, graphify
    engine_version = Column(String(50), default="1.2.0")
    indexed_commit = Column(String(100), default="head")
    query_text = Column(Text, nullable=True)
    path_json = Column(Text, default="[]")
    provenance = Column(String(50), default="static_extracted")  # static_extracted, inferred, unresolved
    confidence = Column(Float, default=1.0)
    staleness_status = Column(String(50), default="fresh")  # fresh, stale

    run = relationship("TestRun", back_populates="graph_evidence")


class Artifact(Base):
    __tablename__ = "artifacts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    interaction_id = Column(String(36), ForeignKey("interactions.id"), nullable=True)
    artifact_type = Column(String(50), nullable=False)  # screenshot, playwright_trace, html_report, json_report, markdown_report
    storage_uri = Column(String(512), nullable=False)
    content_hash = Column(String(100), nullable=True)
    size_bytes = Column(Integer, default=0)
    redaction_status = Column(String(50), default="sanitized")
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("TestRun", back_populates="artifacts")


class TimingObservation(Base):
    __tablename__ = "timing_observations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    interaction_id = Column(String(36), ForeignKey("interactions.id"), nullable=True)
    metric_name = Column(String(100), nullable=False)  # ui_action_duration, request_latency, ttfb, backend_span_duration, db_operation_duration, async_completion_delay, end_to_end_duration
    duration_ms = Column(Float, nullable=False)
    measurement_source = Column(String(50), default="browser")  # browser, network, otel_trace, db_adapter
    baseline_duration_ms = Column(Float, nullable=True)
    delta_ms = Column(Float, nullable=True)
    delta_percent = Column(Float, nullable=True)
    threshold_status = Column(String(50), default="pass")  # pass, warn, fail, not_comparable
    sample_count = Column(Integer, default=1)
    metadata_json = Column(Text, default="{}")

    run = relationship("TestRun", back_populates="timings")


class InteractionPattern(Base):
    __tablename__ = "interaction_patterns"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    scenario_id = Column(String(36), ForeignKey("test_scenarios.id"), nullable=False)
    name = Column(String(100), nullable=False)
    pattern_type = Column(String(50), default="rapid_double_click")  # single_click, rapid_double_click, click_while_pending, retry_after_timeout
    repetition_count = Column(Integer, default=2)
    interval_ms = Column(Integer, default=100)
    concurrency_level = Column(Integer, default=1)
    expected_effects_json = Column(Text, default="{}")
    safety_policy_json = Column(Text, default="{}")


class RegressionDifference(Base):
    __tablename__ = "regression_differences"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    run_id = Column(String(36), ForeignKey("test_runs.id"), nullable=False)
    baseline_run_id = Column(String(36), nullable=False)
    difference_type = Column(String(50), nullable=False)  # NEW_FAILURE, FIXED_FAILURE, BEHAVIOR_CHANGED, LATENCY_REGRESSION, CALL_COUNT_CHANGED, DATA_DIFF_CHANGED, TRACE_PATH_CHANGED, NOT_COMPARABLE
    severity = Column(String(50), default="warning")  # info, warning, critical
    baseline_value_json = Column(Text, default="{}")
    current_value_json = Column(Text, default="{}")
    delta_json = Column(Text, default="{}")
    evidence_refs_json = Column(Text, default="{}")
    classification_reason = Column(Text, nullable=False)

    run = relationship("TestRun", back_populates="regression_differences")
