"""
Scenario B: Regression Detection Run.
Executes against an approved baseline with deliberately introduced regressions:
1. Latency Regression: simulates 650ms slow backend response.
2. Data Integrity Anomaly: mutates forbidden 'is_admin' field.
Detects LATENCY_REGRESSION and FORBIDDEN_CHANGE_DETECTED, reporting regression deltas.
"""
import asyncio
from playwright.async_api import async_playwright
from packages.traceplay_runner.runner import TracePlayRunner
from packages.graph_adapters.code_graph_analyzer import CodeGraphAdapter


async def run_regression_test(baseline_id: str, app_url: str = "http://localhost:5001", api_url: str = "http://localhost:8000"):
    print("▶ Starting Path B: Regression Test Run (Simulating Deliberate Flaws)...")
    import os
    db_abs = os.path.abspath(os.path.join(os.path.dirname(__file__), "../traceplay_sample.db"))
    runner = TracePlayRunner(
        api_base_url=api_url,
        db_connection_uri=f"sqlite:///{db_abs}",
        project_id="sample-project-1",
        test_mode="regression",
        baseline_run_id=baseline_id,
    )
    await runner.initialize_run("profile-update-regression")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Wire up network interception
        await runner.setup_page_instrumentation(page)

        # 1. Scoped Database Observation Before
        print("  [1/4] Capturing scoped database snapshot before interaction...")
        await runner.data.observe(
            snapshot_id="profile-before-regression",
            rule="user-profile-by-id",
            entity="users",
            key_field="id",
            key_value="user-1",
            fields=["display_name", "email", "role", "is_admin"],
        )

        # 2. UI Navigation Step
        print("  [2/4] Navigating to user profile page...")
        await runner.step(
            label="Navigate to Profile Form",
            action_fn=lambda: page.goto(app_url),
            page=page,
        )

        # 3. Form Fill & Check Deliberate Regression Flaws
        print("  [3/4] Enabling simulated slow backend & forbidden data write...")
        async def submit_regression_form():
            await page.fill("#display-name", "Alex Regressed Name")
            # Turn on simulated flaws
            await page.check("#sim-delay")
            await page.check("#sim-unexpected")
            await page.click("#save-button")
            # Wait for response and toast
            await page.wait_for_selector(".toast-success", timeout=6000)

        await runner.step(
            label="Save Profile Changes",
            action_fn=submit_regression_form,
            page=page,
        )

        # 4. Verify Expected and Forbidden Database Changes
        print("  [4/4] Verifying database state transitions (Expecting anomaly detection)...")
        diffs = await runner.data.expectChange(
            before_snapshot_id="profile-before-regression",
            entity="users",
            key_field="id",
            key_value="user-1",
            expected_fields={"display_name": "Alex Regressed Name"},
            forbidden_fields=["is_admin", "role"],
            expected_unchanged=["role", "is_admin"],
        )

        # Code Graph Analysis
        print("  Analyzing code graph with Graphify adapter...")
        adapter = CodeGraphAdapter(engine_name="graphify")
        try:
            await runner.client.post(
                f"/api/graph/analyze?run_id={runner.run_id}",
                json={"project_id": "sample-project-1", "engine": "graphify"},
            )
        except Exception:
            pass

        # Complete Run - RegressionEngine will automatically evaluate deltas against baseline!
        await runner.complete_run()
        await browser.close()

    print(f"⚠️ Regression run completed! Regressions logged against baseline {baseline_id[:8]}. Run ID: {runner.run_id}")
    return runner.run_id
