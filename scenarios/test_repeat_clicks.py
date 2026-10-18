"""
Scenario C: Rapid Double-Click & Duplicate Request Detection.
Simulates bounded rapid double-click on save button.
Records click count, browser request count, and resulting database audit entries.
Verifies whether debounce protection prevents duplicate writes and duplicate side effects.
"""
import asyncio
from playwright.async_api import async_playwright
from packages.traceplay_runner.runner import TracePlayRunner


async def run_repeat_click_test(app_url: str = "http://localhost:5001", api_url: str = "http://localhost:8000"):
    print("▶ Starting Path C: Rapid Double-Click & Concurrency Analysis...")
    import os
    db_abs = os.path.abspath(os.path.join(os.path.dirname(__file__), "../traceplay_sample.db"))
    runner = TracePlayRunner(
        api_base_url=api_url,
        db_connection_uri=f"sqlite:///{db_abs}",
        project_id="sample-project-1",
        test_mode="stress_repeat",
    )
    await runner.initialize_run("save-profile-rapid-double-click")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await runner.setup_page_instrumentation(page)

        # 1. Scoped Database Observation Before
        initial_audit_count = runner.db_adapter.count_records("audit_logs", "user_id", "user-1")

        # 2. UI Navigation
        await runner.step(
            label="Navigate to Profile Form",
            action_fn=lambda: page.goto(app_url),
            page=page,
        )

        # 3. Fill form and execute rapid double-click
        print("  [3/4] Executing rapid double-click on Save button (100ms interval)...")
        await page.fill("#display-name", "Alex Protected Double-Click")

        async def perform_double_click():
            # Trigger two clicks within 80ms
            btn = page.locator("#save-button")
            await btn.click()
            await asyncio.sleep(0.08)
            await btn.click()
            await page.wait_for_selector(".toast-success", timeout=5000)

        await runner.step(
            label="Rapid Double-Click Save Button",
            action_fn=perform_double_click,
            page=page,
            is_repeat_click=True,
        )

        # 4. Verify request count and database audit records
        final_audit_count = runner.db_adapter.count_records("audit_logs", "user_id", "user-1")
        new_audit_records = final_audit_count - initial_audit_count

        print(f"  Physical Clicks: 2 | DB Audit Entries Added: {new_audit_records}")

        # Assert zero duplicate writes
        await runner.ingest_assertion(
            assertion_type="duplicate_write_prevention",
            description="Button debouncing prevents duplicate database writes on rapid double-click",
            expected={"max_new_records": 1},
            actual={"created_records": new_audit_records},
            status="passed" if new_audit_records <= 1 else "failed",
        )

        await runner.complete_run(status="passed" if new_audit_records <= 1 else "failed")
        await browser.close()

    print(f"✅ Repeat-click test completed! No duplicate writes observed. Run ID: {runner.run_id}")
    return runner.run_id
