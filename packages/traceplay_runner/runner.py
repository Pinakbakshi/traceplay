"""
TracePlay Playwright Runner and Test Execution Fixture.
Provides interaction step tracking, correlation header injection (traceparent, X-TracePlay-Interaction-Id),
network & console capture, database state verification, timing measurements, and repeat-click testing.
"""
import asyncio
import json
import os
import time
import uuid
from typing import Any, Callable, Dict, List, Optional
import httpx
from playwright.async_api import async_playwright, Page, BrowserContext, Request, Response
from packages.db_adapter.readonly_db_adapter import ReadOnlyDatabaseAdapter
from apps.api.services.diff_engine import DiffEngine
from apps.api.services.timing_engine import TimingEngine


def generate_trace_id() -> str:
    return uuid.uuid4().hex


def generate_span_id() -> str:
    return uuid.uuid4().hex[:16]


class TracePlayDataContext:
    def __init__(self, runner: "TracePlayRunner"):
        self.runner = runner
        self.snapshots: Dict[str, Dict[str, Any]] = {}

    async def observe(self, snapshot_id: str, rule: str, entity: str, key_field: str, key_value: Any, fields: Optional[List[str]] = None):
        """Take a scoped read-only snapshot before or after an action."""
        if not self.runner.db_adapter:
            return None
        snapshot = self.runner.db_adapter.capture_snapshot(
            entity=entity,
            key_field=key_field,
            key_value=key_value,
            fields_to_include=fields,
        )
        self.snapshots[snapshot_id] = {
            "entity": entity,
            "key_field": key_field,
            "key_value": key_value,
            "snapshot": snapshot,
        }

        # Ingest observation to API
        await self.runner.ingest_observation(
            rule_id=rule,
            entity_type=entity,
            key=str(key_value),
            snapshot=snapshot or {},
        )
        return snapshot

    async def expectChange(
        self,
        before_snapshot_id: str,
        entity: str,
        key_field: str,
        key_value: Any,
        expected_fields: Dict[str, Any],
        forbidden_fields: Optional[List[str]] = None,
        expected_unchanged: Optional[List[str]] = None,
    ):
        """Assert that specific fields changed as expected and other fields did not change."""
        before_data = self.snapshots.get(before_snapshot_id, {}).get("snapshot", {})
        fields_to_include = list(before_data.keys()) if before_data else None
        after_data = self.runner.db_adapter.capture_snapshot(
            entity=entity,
            key_field=key_field,
            key_value=key_value,
            fields_to_include=fields_to_include,
        )

        diffs = DiffEngine.compare_snapshots(
            before=before_data,
            after=after_data,
            entity_type=entity,
            entity_key=str(key_value),
            expected_changes=expected_fields,
            forbidden_fields=forbidden_fields,
            expected_unchanged=expected_unchanged,
            interaction_id=self.runner.current_interaction_id,
            has_trace_correlation=True,
        )

        for diff in diffs:
            await self.runner.ingest_diff(diff)

            # Record assertion for expected changes
            is_valid = diff["expectation_status"] in ("EXPECTED_CHANGE", "UNCHANGED", "UNCHANGED_AS_EXPECTED")
            await self.runner.ingest_assertion(
                assertion_type="expected_change",
                description=f"Field {entity}.{diff['field_name']} state verification: {diff['expectation_status']}",
                expected=expected_fields.get(diff["field_name"], "[unchanged]"),
                actual=diff["after_value_redacted"],
                status="passed" if is_valid else "failed",
            )

        return diffs


class TracePlayRunner:
    def __init__(
        self,
        api_base_url: str = "http://localhost:8000",
        db_connection_uri: str = "sqlite:///traceplay_sample.db",
        run_id: Optional[str] = None,
        project_id: Optional[str] = None,
        test_mode: str = "first_round_qa",
        baseline_run_id: Optional[str] = None,
    ):
        self.api_base_url = api_base_url
        self.db_adapter = ReadOnlyDatabaseAdapter(connection_uri=db_connection_uri)
        self.run_id = run_id or str(uuid.uuid4())
        self.project_id = project_id or "default-project"
        self.test_mode = test_mode
        self.baseline_run_id = baseline_run_id
        self.step_index = 0
        self.current_interaction_id: Optional[str] = None
        self.current_trace_id = generate_trace_id()
        self.client = httpx.AsyncClient(base_url=self.api_base_url, timeout=10.0)
        self.data = TracePlayDataContext(self)
        self.captured_network_events = []
        self.captured_errors = []

    async def initialize_run(self, scenario_name: str = "default_scenario"):
        # Register or retrieve run from API
        try:
            resp = await self.client.post(
                "/api/runs",
                json={
                    "project_id": self.project_id,
                    "test_mode": self.test_mode,
                    "baseline_run_id": self.baseline_run_id,
                    "commit_sha": "demo-commit-1",
                    "application_build": "1.0.0",
                },
            )
            if resp.status_code == 200:
                self.run_id = resp.json()["id"]
        except Exception:
            pass  # Standalone mode if API is launching simultaneously

    async def setup_page_instrumentation(self, page: Page):
        """
        Intercept requests to inject W3C traceparent and X-TracePlay-Interaction-Id headers.
        Record response timings, latency, status codes, and console errors.
        """
        async def on_request(request: Request):
            pass

        async def on_response(response: Response):
            req = response.request
            # Filter non-app static assets (favicon, fonts)
            url = req.url
            if not ("/api/" in url or url.endswith("/")):
                return

            status = response.status
            method = req.method
            timing = response.request.timing
            duration_ms = (timing.get("responseEnd", 0) - timing.get("requestStart", 0)) if timing else 50.0
            if duration_ms < 0:
                duration_ms = 50.0

            # Route template normalization
            route_template = url.split("?")[0]
            if "/api/" in route_template:
                route_template = "/api/" + route_template.split("/api/")[1]

            # Ingest network event to API
            await self.ingest_network_event(
                request_id=str(uuid.uuid4()),
                trace_id=self.current_trace_id,
                method=method,
                route_template=route_template,
                status_code=status,
                duration_ms=duration_ms,
            )

        page.on("response", on_response)
        page.on("console", lambda msg: self.captured_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: self.captured_errors.append(str(exc)))

        # Route interceptor to inject correlation headers
        async def handle_route(route):
            headers = dict(route.request.headers)
            headers["x-traceplay-interaction-id"] = self.current_interaction_id or "initial"
            headers["x-traceplay-run-id"] = self.run_id
            headers["traceparent"] = f"00-{self.current_trace_id}-{generate_span_id()}-01"
            await route.continue_(headers=headers)

        await page.route("**/api/**", handle_route)

    async def step(self, label: str, action_fn: Callable[[], Any], page: Optional[Page] = None, is_repeat_click: bool = False):
        """
        Execute an interaction step, measure timing, capture URL before/after, and record to timeline.
        """
        self.step_index += 1
        interaction_id = str(uuid.uuid4())
        self.current_interaction_id = interaction_id
        page_before = page.url if page else ""

        start_time = time.time()
        status = "passed"
        try:
            await action_fn()
        except Exception as e:
            status = "failed"
            raise e
        finally:
            duration_ms = (time.time() - start_time) * 1000.0
            page_after = page.url if page else ""

            # Ingest interaction
            await self.ingest_interaction(
                interaction_id=interaction_id,
                step_index=self.step_index,
                action_label=label,
                action_type="repeat_click" if is_repeat_click else "click",
                duration_ms=duration_ms,
                page_url_before=page_before,
                page_url_after=page_after,
                status=status,
            )

            # Ingest UI action timing observation
            await self.ingest_timing(
                metric_name=f"ui_action_{self.step_index}_{label.lower().replace(' ', '_')}",
                duration_ms=duration_ms,
                measurement_source="browser",
            )

    # ---------------- Repeat-Click and Concurrency Helpers ---------------- #

    async def rapid_double_click(self, page: Page, selector: str, interval_ms: int = 100):
        """Simulate rapid double-click before response settles."""
        button = page.locator(selector)
        await button.click()
        await asyncio.sleep(interval_ms / 1000.0)
        await button.click()

    async def click_while_pending(self, page: Page, selector: str, repetitions: int = 3, interval_ms: int = 120):
        """Click multiple times while request is in flight."""
        button = page.locator(selector)
        for _ in range(repetitions):
            await button.click()
            await asyncio.sleep(interval_ms / 1000.0)

    # ---------------- Ingestion Helpers ---------------- #

    async def ingest_interaction(self, interaction_id: str, step_index: int, action_label: str, action_type: str, duration_ms: float, page_url_before: str, page_url_after: str, status: str):
        try:
            await self.client.post(
                f"/api/evidence/interactions?run_id={self.run_id}",
                json={
                    "id": interaction_id,
                    "step_index": step_index,
                    "action_label": action_label,
                    "action_type": action_type,
                    "page_url_before": page_url_before,
                    "page_url_after": page_url_after,
                    "status": status,
                },
            )
        except Exception:
            pass

    async def ingest_network_event(self, request_id: str, trace_id: str, method: str, route_template: str, status_code: int, duration_ms: float):
        try:
            await self.client.post(
                "/api/evidence/network",
                json={
                    "run_id": self.run_id,
                    "interaction_id": self.current_interaction_id,
                    "request_id": request_id,
                    "trace_id": trace_id,
                    "method": method,
                    "route_template": route_template,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                },
            )
        except Exception:
            pass

    async def ingest_span(self, trace_id: str, span_id: str, parent_span_id: Optional[str], service_name: str, operation_name: str, duration_ms: float):
        try:
            await self.client.post(
                "/api/evidence/spans",
                json={
                    "run_id": self.run_id,
                    "interaction_id": self.current_interaction_id,
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "parent_span_id": parent_span_id,
                    "service_name": service_name,
                    "operation_name": operation_name,
                    "duration_ms": duration_ms,
                },
            )
        except Exception:
            pass

    async def ingest_observation(self, rule_id: str, entity_type: str, key: str, snapshot: Dict[str, Any]):
        try:
            await self.client.post(
                "/api/evidence/data-observations",
                json={
                    "run_id": self.run_id,
                    "interaction_id": self.current_interaction_id,
                    "verification_rule_id": rule_id,
                    "entity_type": entity_type,
                    "entity_key_hash": key,
                    "snapshot": snapshot,
                },
            )
        except Exception:
            pass

    async def ingest_diff(self, diff: Dict[str, Any]):
        try:
            resp = await self.client.post(
                "/api/evidence/diffs",
                json={
                    "run_id": self.run_id,
                    "interaction_id": self.current_interaction_id,
                    "entity_type": diff["entity_type"],
                    "entity_key_hash": diff["entity_key_hash"],
                    "field_name": diff["field_name"],
                    "change_type": diff["change_type"],
                    "before_value": diff["before_value_redacted"],
                    "after_value": diff["after_value_redacted"],
                    "expectation_status": diff["expectation_status"],
                    "causality_status": diff["causality_status"],
                    "evidence": json.loads(diff.get("evidence_json", "{}")),
                },
            )
            if resp.status_code != 200:
                print(f"⚠️ Ingest diff returned {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"❌ Ingest diff failed with exception: {e}")

    async def ingest_assertion(self, assertion_type: str, description: str, expected: Any, actual: Any, status: str):
        try:
            await self.client.post(
                "/api/evidence/assertions",
                json={
                    "run_id": self.run_id,
                    "interaction_id": self.current_interaction_id,
                    "assertion_type": assertion_type,
                    "description": description,
                    "expected": expected,
                    "actual": actual,
                    "status": status,
                },
            )
        except Exception:
            pass

    async def ingest_timing(self, metric_name: str, duration_ms: float, measurement_source: str = "browser"):
        try:
            await self.client.post(
                "/api/evidence/timings",
                json={
                    "run_id": self.run_id,
                    "interaction_id": self.current_interaction_id,
                    "metric_name": metric_name,
                    "duration_ms": duration_ms,
                    "measurement_source": measurement_source,
                },
            )
        except Exception:
            pass

    async def complete_run(self, status: str = "passed"):
        try:
            await self.client.post(f"/api/evidence/complete-run?run_id={self.run_id}&status={status}")
        except Exception:
            pass
        finally:
            await self.client.aclose()
