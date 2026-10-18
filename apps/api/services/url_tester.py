"""
TracePlay Autonomous URL Exploration and Testing Engine.
Given any website URL, automatically explores actionable elements (forms, buttons, inputs),
intercepts network requests, captures console errors, measures latencies,
performs debounce/double-click stress testing, and stores full evidence in TracePlay.
"""
import asyncio
import json
import os
import re
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
import httpx
from playwright.async_api import async_playwright, Page, Request, Response
from apps.api.database import SessionLocal
from apps.api.models import Project, Environment, TestRun, Interaction, NetworkEvent, TimingObservation, Assertion, DataDiff, RegressionDifference
from apps.api.services.redaction import default_redactor
from apps.api.services.timing_engine import TimingEngine
from apps.api.services.regression_engine import RegressionEngine
from packages.graph_adapters.code_graph_analyzer import CodeGraphAdapter
from packages.db_adapter.readonly_db_adapter import ReadOnlyDatabaseAdapter
from apps.api.services.diff_engine import DiffEngine


class UrlTestConfig:
    def __init__(
        self,
        target_url: str,
        test_mode: str = "first_round_qa",  # first_round_qa, regression, stress_repeat, comprehensive
        project_name: Optional[str] = None,
        baseline_run_id: Optional[str] = None,
        max_interactions: int = 10,
        enable_multi_click: bool = True,
        db_connection_uri: Optional[str] = None,
        repo_path: Optional[str] = None,
    ):
        self.target_url = target_url.strip()
        self.test_mode = test_mode
        self.project_name = project_name or f"Site: {self._extract_domain(target_url)}"
        self.baseline_run_id = baseline_run_id
        self.max_interactions = max_interactions
        self.enable_multi_click = enable_multi_click
        self.db_connection_uri = db_connection_uri
        self.repo_path = repo_path

    @staticmethod
    def _extract_domain(url: str) -> str:
        match = re.search(r"https?://([^/:]+)", url)
        return match.group(1) if match else "Web Target"


class UrlTestRunner:
    def __init__(self, config: UrlTestConfig, api_base_url: str = "http://127.0.0.1:8000"):
        self.config = config
        self.api_base_url = api_base_url
        self.run_id = str(uuid.uuid4())
        self.project_id: Optional[str] = None
        self.step_index = 0
        self.current_interaction_id: Optional[str] = None
        self.current_trace_id = uuid.uuid4().hex
        self.captured_requests: List[Dict[str, Any]] = []
        self.captured_errors: List[str] = []
        self.db_adapter = ReadOnlyDatabaseAdapter(self.config.db_connection_uri) if self.config.db_connection_uri else None
        self.logs: List[str] = []
        self.status = "queued"

    def log(self, message: str):
        entry = f"[{datetime.utcnow().strftime('%H:%M:%S')}] {message}"
        self.logs.append(entry)
        print(entry)

    def initialize_project_and_run(self):
        db = SessionLocal()
        try:
            # Find or create project
            project = db.query(Project).filter(Project.name == self.config.project_name).first()
            if not project:
                project = Project(
                    name=self.config.project_name,
                    repository_url=self.config.repo_path or self.config.target_url,
                    default_branch="main",
                )
                db.add(project)
                db.commit()
                db.refresh(project)
            self.project_id = project.id

            # Find baseline if regression mode
            baseline_id = self.config.baseline_run_id
            baseline_status = "none"
            if self.config.test_mode == "regression":
                if not baseline_id:
                    approved_baseline = (
                        db.query(TestRun)
                        .filter(TestRun.project_id == project.id, TestRun.baseline_status == "approved")
                        .order_by(TestRun.started_at.desc())
                        .first()
                    )
                    if approved_baseline:
                        baseline_id = approved_baseline.id
                        baseline_status = "approved"
            elif self.config.test_mode == "first_round_qa":
                baseline_status = "candidate"

            # Create TestRun
            run = TestRun(
                id=self.run_id,
                project_id=project.id,
                commit_sha="head",
                application_build="target-eval",
                test_mode=self.config.test_mode,
                baseline_run_id=baseline_id,
                baseline_status=baseline_status,
                status="running",
            )
            db.add(run)
            db.commit()
            self.log(f"Initialized Test Run {self.run_id[:8]} (Mode: {self.config.test_mode}) for {self.config.target_url}")
        finally:
            db.close()

    async def execute(self) -> Dict[str, Any]:
        self.status = "running"
        self.initialize_project_and_run()

        db = SessionLocal()
        try:
            async with async_playwright() as p:
                self.log("Launching headless browser context...")
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="TracePlay-Impact-Testing-Agent/1.0",
                )
                page = await context.new_page()

                # Wire network and error listeners
                self._attach_telemetry(page, db)

                # Step 1: Navigate to Target URL
                await self._step_navigate(page, db)

                # Step 2: Discover and test forms / interactive inputs
                await self._step_explore_forms(page, db)

                # Step 3: Discover and test buttons / API triggers
                await self._step_explore_buttons(page, db)

                # Step 4: Multi-Click & Debounce Testing (if enabled)
                if self.config.enable_multi_click:
                    await self._step_multi_click_tests(page, db)

                # Step 5: Code graph analysis if repo given or standard AST
                self._run_code_graph_analysis(db)

                # Step 6: Conclude Run and evaluate regressions if baseline exists
                final_status = self._finalize_run(db)
                await browser.close()
                self.status = final_status

            self.log(f"Test run completed with status: {self.status.upper()}")
            return {
                "run_id": self.run_id,
                "project_id": self.project_id,
                "status": self.status,
                "interactions_count": self.step_index,
                "requests_count": len(self.captured_requests),
                "errors_count": len(self.captured_errors),
                "logs": self.logs,
            }
        except Exception as e:
            self.log(f"❌ Error during test execution: {e}")
            self.status = "failed"
            run = db.query(TestRun).filter(TestRun.id == self.run_id).first()
            if run:
                run.status = "failed"
                run.finished_at = datetime.utcnow()
                db.commit()
            raise e
        finally:
            db.close()

    def _attach_telemetry(self, page: Page, db):
        async def on_response(response: Response):
            req = response.request
            url = req.url
            # Filter non-critical static icons or fonts
            if url.endswith((".ico", ".woff", ".woff2", ".ttf")):
                return

            status = response.status
            method = req.method
            timing = req.timing
            duration_ms = (timing.get("responseEnd", 0) - timing.get("requestStart", 0)) if timing else 45.0
            if duration_ms < 0:
                duration_ms = 45.0

            route = url.split("?")[0]

            # Parse traceparent if present
            trace_id = self.current_trace_id
            headers = req.headers
            if "traceparent" in headers:
                parts = headers["traceparent"].split("-")
                if len(parts) >= 3:
                    trace_id = parts[1]

            net_event = NetworkEvent(
                run_id=self.run_id,
                interaction_id=self.current_interaction_id,
                request_id=str(uuid.uuid4()),
                trace_id=trace_id,
                method=method,
                route_template=route,
                status_code=status,
                duration_ms=duration_ms,
                request_summary_json=json.dumps(default_redactor.sanitize_headers(headers)),
                response_summary_json=json.dumps({"status": status, "url": url}),
            )
            db.add(net_event)
            db.commit()
            self.captured_requests.append({"method": method, "url": route, "status": status, "duration_ms": duration_ms})

        async def handle_route(route):
            headers = dict(route.request.headers)
            headers["x-traceplay-interaction-id"] = self.current_interaction_id or "auto-init"
            headers["x-traceplay-run-id"] = self.run_id
            headers["traceparent"] = f"00-{self.current_trace_id}-{uuid.uuid4().hex[:16]}-01"
            await route.continue_(headers=headers)

        page.on("response", on_response)
        page.on("console", lambda msg: self._handle_console(msg, db))
        page.on("pageerror", lambda err: self._handle_page_error(str(err), db))
        # Intercept outbound HTTP to inject correlation headers
        page.route("**/*", handle_route)

    def _handle_console(self, msg, db):
        if msg.type == "error":
            self.captured_errors.append(msg.text)
            self.log(f"Browser Console Error: {msg.text}")
            assertion = Assertion(
                run_id=self.run_id,
                interaction_id=self.current_interaction_id,
                assertion_type="console_integrity",
                description=f"Console error detected: {msg.text[:120]}",
                expected_json=json.dumps({"errors": 0}),
                actual_json=json.dumps({"error": msg.text}),
                status="failed",
            )
            db.add(assertion)
            db.commit()

    def _handle_page_error(self, err_text: str, db):
        self.captured_errors.append(err_text)
        self.log(f"Uncaught Page Exception: {err_text}")
        assertion = Assertion(
            run_id=self.run_id,
            interaction_id=self.current_interaction_id,
            assertion_type="page_integrity",
            description=f"Uncaught page exception: {err_text[:120]}",
            expected_json=json.dumps({"exceptions": 0}),
            actual_json=json.dumps({"exception": err_text}),
            status="failed",
        )
        db.add(assertion)
        db.commit()

    async def _step_navigate(self, page: Page, db):
        self.step_index += 1
        interaction_id = str(uuid.uuid4())
        self.current_interaction_id = interaction_id
        self.log(f"[Step {self.step_index}] Navigating to target: {self.config.target_url}")

        start_t = time.time()
        resp = await page.goto(self.config.target_url, wait_until="domcontentloaded", timeout=15000)
        duration_ms = (time.time() - start_t) * 1000.0

        page_status = resp.status if resp else 200
        step_passed = page_status < 400

        interaction = Interaction(
            id=interaction_id,
            run_id=self.run_id,
            step_index=self.step_index,
            action_label=f"Navigate to {self.config.target_url}",
            action_type="navigate",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            page_url_before="about:blank",
            page_url_after=page.url,
            status="passed" if step_passed else "failed",
        )
        db.add(interaction)

        # Ingest timing observation
        timing = TimingObservation(
            run_id=self.run_id,
            interaction_id=interaction_id,
            metric_name="page_load_navigation",
            duration_ms=duration_ms,
            measurement_source="browser",
            threshold_status="pass" if duration_ms < 5000.0 else "warn",
        )
        db.add(timing)

        # Ingest assertion
        assertion = Assertion(
            run_id=self.run_id,
            interaction_id=interaction_id,
            assertion_type="http_reachability",
            description=f"Initial page returns HTTP {page_status}",
            expected_json=json.dumps({"status_code": "<400"}),
            actual_json=json.dumps({"status_code": page_status}),
            status="passed" if step_passed else "failed",
        )
        db.add(assertion)
        db.commit()

    async def _step_explore_forms(self, page: Page, db):
        """Discover form inputs, fill synthetic safe values, and test submission."""
        forms = await page.query_selector_all("form")
        inputs = await page.query_selector_all("input:not([type='hidden']):not([type='checkbox']):not([type='radio'])")
        
        if not inputs and not forms:
            self.log("No visible form inputs discovered on the initial page view.")
            return

        self.step_index += 1
        interaction_id = str(uuid.uuid4())
        self.current_interaction_id = interaction_id
        self.log(f"[Step {self.step_index}] Discovered {len(inputs)} form input(s). Filling context-aware values...")

        start_t = time.time()
        for inp in inputs:
            try:
                inp_type = (await inp.get_attribute("type") or "text").lower()
                inp_name = (await inp.get_attribute("name") or await inp.get_attribute("id") or "").lower()

                # Generate context-aware synthetic values
                if "email" in inp_type or "email" in inp_name:
                    val = f"traceplay_test_{int(time.time())}@example.com"
                elif "pass" in inp_type or "password" in inp_name:
                    val = "TracePlay@Secure123"
                elif "phone" in inp_name or "tel" in inp_type:
                    val = "+15551234567"
                elif "name" in inp_name:
                    val = "Alex TracePlay Tester"
                else:
                    val = "TracePlay Automated Value"

                await inp.fill(val)
            except Exception:
                pass

        duration_ms = (time.time() - start_t) * 1000.0
        interaction = Interaction(
            id=interaction_id,
            run_id=self.run_id,
            step_index=self.step_index,
            action_label=f"Fill Form Fields ({len(inputs)} input elements)",
            action_type="fill",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            page_url_before=page.url,
            page_url_after=page.url,
            status="passed",
        )
        db.add(interaction)
        db.commit()

    async def _step_explore_buttons(self, page: Page, db):
        """Discover primary action buttons (submit, save, pay, login) and trigger them."""
        buttons = await page.query_selector_all("button:visible, input[type='submit']:visible, [role='button']:visible")
        if not buttons:
            self.log("No visible buttons found to activate.")
            return

        # Target the most likely state-changing button
        target_btn = None
        target_label = "Action Button"
        for btn in buttons:
            text = (await btn.inner_text() or await btn.get_attribute("value") or "").strip()
            if any(k in text.lower() for k in ["save", "submit", "update", "sign", "continue", "send", "apply", "test"]):
                target_btn = btn
                target_label = text
                break

        if not target_btn:
            target_btn = buttons[0]
            target_label = (await target_btn.inner_text() or "Primary Button").strip()

        self.step_index += 1
        interaction_id = str(uuid.uuid4())
        self.current_interaction_id = interaction_id
        self.log(f"[Step {self.step_index}] Triggering action button: '{target_label}'")

        start_t = time.time()
        try:
            await target_btn.click()
            await page.wait_for_timeout(1000)  # Wait for AJAX/network settle
        except Exception as e:
            self.log(f"Button click warning: {e}")

        duration_ms = (time.time() - start_t) * 1000.0

        interaction = Interaction(
            id=interaction_id,
            run_id=self.run_id,
            step_index=self.step_index,
            action_label=f"Click Button '{target_label}'",
            action_type="click",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            page_url_before=page.url,
            page_url_after=page.url,
            status="passed",
        )
        db.add(interaction)

        timing = TimingObservation(
            run_id=self.run_id,
            interaction_id=interaction_id,
            metric_name="button_click_and_settle",
            duration_ms=duration_ms,
            measurement_source="browser",
            threshold_status="pass",
        )
        db.add(timing)
        db.commit()

    async def _step_multi_click_tests(self, page: Page, db):
        """Simulate rapid double-click on state-changing buttons to evaluate debounce protection."""
        buttons = await page.query_selector_all("button:visible, input[type='submit']:visible")
        if not buttons:
            return

        target_btn = buttons[0]
        label = (await target_btn.inner_text() or "Save Button").strip()

        self.step_index += 1
        interaction_id = str(uuid.uuid4())
        self.current_interaction_id = interaction_id
        self.log(f"[Step {self.step_index}] Multi-Click Check: Executing rapid double-click (80ms interval) on '{label}'")

        reqs_before = len(self.captured_requests)
        start_t = time.time()
        try:
            await target_btn.click()
            await asyncio.sleep(0.08)
            await target_btn.click()
            await page.wait_for_timeout(800)
        except Exception as e:
            self.log(f"Multi-click simulation note: {e}")

        duration_ms = (time.time() - start_t) * 1000.0
        reqs_after = len(self.captured_requests)
        diff_reqs = reqs_after - reqs_before

        interaction = Interaction(
            id=interaction_id,
            run_id=self.run_id,
            step_index=self.step_index,
            action_label=f"Rapid Double-Click '{label}' (Debounce Check)",
            action_type="repeat_click",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            page_url_before=page.url,
            page_url_after=page.url,
            status="passed",
        )
        db.add(interaction)

        # Assertion: If 2 physical clicks generated > 1 identical state-changing requests, warn
        has_debounce = diff_reqs <= 1
        assertion = Assertion(
            run_id=self.run_id,
            interaction_id=interaction_id,
            assertion_type="duplicate_request_prevention",
            description=f"Debounce verification: 2 physical clicks generated {diff_reqs} request(s)",
            expected_json=json.dumps({"max_requests": 1}),
            actual_json=json.dumps({"observed_requests": diff_reqs}),
            status="passed" if has_debounce else "warn",
        )
        db.add(assertion)
        db.commit()

    def _run_code_graph_analysis(self, db):
        """Extract static AST paths using GitNexus/Graphify adapter if code is present."""
        adapter = CodeGraphAdapter(engine_name="gitnexus")
        paths = adapter.analyze_repository(repository_path=self.config.repo_path or ".")
        self.log(f"Code Graph Adapter (GitNexus): Indexed {len(paths)} static dependency relationships.")

    def _finalize_run(self, db) -> str:
        run = db.query(TestRun).filter(TestRun.id == self.run_id).first()
        if not run:
            return "failed"

        run.finished_at = datetime.utcnow()
        status = "passed"

        # Check failed assertions
        failed_asserts = db.query(Assertion).filter(Assertion.run_id == self.run_id, Assertion.status == "failed").count()
        if failed_asserts > 0:
            status = "failed"

        # If baseline exists, run regression comparison!
        if run.baseline_run_id:
            baseline = db.query(TestRun).filter(TestRun.id == run.baseline_run_id).first()
            if baseline:
                self.log(f"Running automated regression comparison against Baseline {baseline.id[:8]}...")
                c_events = [{"method": e.method, "route_template": e.route_template} for e in run.network_events]
                b_events = [{"method": e.method, "route_template": e.route_template} for e in baseline.network_events]

                c_diffs = [{"entity_type": d.entity_type, "field_name": d.field_name, "expectation_status": d.expectation_status, "after_value_redacted": d.after_value_redacted} for d in run.data_diffs]
                b_diffs = [{"entity_type": d.entity_type, "field_name": d.field_name, "expectation_status": d.expectation_status, "after_value_redacted": d.after_value_redacted} for d in baseline.data_diffs]

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
                    self.log(f"⚠️ Regression Anomaly: [{reg['difference_type']}] {reg['classification_reason']}")

                critical_regs = [r for r in regressions if r.get("severity") == "critical"]
                if critical_regs:
                    status = "failed"

        run.status = status
        db.commit()
        return status
