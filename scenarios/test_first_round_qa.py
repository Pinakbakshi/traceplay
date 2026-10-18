"""
Scenario A: First-Round QA Baseline Establishment.
Validates standard user profile update workflow, captures browser network events,
takes scoped before/after database snapshot, asserts expected mutations and unchanged security fields.
Establishes a candidate baseline and approves it for future regression comparisons.
"""
import asyncio
from playwright.async_api import async_playwright
from packages.traceplay_runner.runner import TracePlayRunner
from packages.graph_adapters.code_graph_analyzer import CodeGraphAdapter


async def run_first_round_qa(app_url: str = "http://localhost:5001", api_url: str = "http://localhost:8000"):
    print("▶ Starting Path A: First-Round QA Baseline Run...")
    import os
    db_abs = os.path.abspath(os.path.join(os.path.dirname(__file__), "../traceplay_sample.db"))
    runner = TracePlayRunner(
        api_base_url=api_url,
        db_connection_uri=f"sqlite:///{db_abs}",
        project_id="sample-project-1",
        test_mode="first_round_qa",
    )
    await runner.initialize_run("profile-update-qa")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # Wire up network interception and correlation injection
        await runner.setup_page_instrumentation(page)

        # 1. Scoped Database Observation Before
        print("  [1/4] Capturing scoped database snapshot before interaction...")
        await runner.data.observe(
            snapshot_id="profile-before",
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

        # 3. Form Fill & Submit Step
        print("  [3/4] Submitting profile form...")
        async def submit_form():
            await page.fill("#display-name", "Alex Baseline Approved")
            await page.click("#save-button")
            # Wait for response and toast
            await page.wait_for_selector(".toast-success", timeout=5000)

        await runner.step(
            label="Save Profile Changes",
            action_fn=submit_form,
            page=page,
        )

        # 4. Verify Expected and Forbidden Database Changes
        print("  [4/4] Verifying database state transitions...")
        diffs = await runner.data.expectChange(
            before_snapshot_id="profile-before",
            entity="users",
            key_field="id",
            key_value="user-1",
            expected_fields={"display_name": "Alex Baseline Approved"},
            forbidden_fields=["is_admin", "role"],
            expected_unchanged=["role", "is_admin"],
        )

        # Static Code Graph Analysis
        print("  Analyzing code graph with GitNexus adapter...")
        adapter = CodeGraphAdapter(engine_name="gitnexus")
        paths = adapter.analyze_repository(repository_path=".")
        try:
            await runner.client.post(
                f"/api/graph/analyze?run_id={runner.run_id}",
                json={"project_id": "sample-project-1", "engine": "gitnexus"},
            )
        except Exception:
            pass

        # Mark Run Completed as Passed
        await runner.complete_run(status="passed")
        await browser.close()

    print(f"✅ First-Round QA completed successfully! Run ID: {runner.run_id}")
    return runner.run_id
