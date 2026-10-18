"""
TracePlay Master Demonstration Script.
Executes the full end-to-end MVP workflow across all three paths:
Path A: First-Round QA establishing candidate baseline & approving it.
Path B: Regression detecting simulated latency and forbidden data mutation.
Path C: Rapid double-click scenario validating duplicate-write prevention.
Exports comprehensive HTML, Markdown, and JSON impact reports.
"""
import asyncio
import os
import subprocess
import sys
import time
import httpx
from scenarios.test_first_round_qa import run_first_round_qa
from scenarios.test_regression import run_regression_test
from scenarios.test_repeat_clicks import run_repeat_click_test


async def wait_for_server(url: str, timeout: float = 10.0):
    start = time.time()
    async with httpx.AsyncClient() as client:
        while time.time() - start < timeout:
            try:
                resp = await client.get(url)
                if resp.status_code in (200, 404):
                    return True
            except Exception:
                await asyncio.sleep(0.3)
    return False


async def main():
    print("=" * 70)
    print("🚀 TracePlay: UI-to-Backend Impact Testing Platform MVP Demo")
    print("=" * 70)

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    if BASE_DIR not in sys.path:
        sys.path.insert(0, BASE_DIR)

    proc_env = os.environ.copy()
    proc_env["PYTHONPATH"] = BASE_DIR

    # 1. Start TracePlay Control API Server (Port 8000)
    print("\n[Step 1/6] Launching TracePlay Control API on http://localhost:8000...")
    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BASE_DIR,
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # 2. Start Sample Instrumented Application (Port 5001)
    print("[Step 2/6] Launching Instrumented Sample App on http://localhost:5001...")
    sample_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "sample_app.backend.app:app", "--host", "127.0.0.1", "--port", "5001"],
        cwd=BASE_DIR,
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        # Wait for both servers to be responsive
        api_ready = await wait_for_server("http://127.0.0.1:8000/health")
        sample_ready = await wait_for_server("http://127.0.0.1:5001/api/profile")

        if not api_ready or not sample_ready:
            print("❌ Failed to bind to servers. Checking logs...")
            return

        print("✅ Both servers are online and ready!")

        # 3. Register Project & Environment via API
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
            proj_resp = await client.post(
                "/api/projects",
                json={
                    "name": "User Account Service",
                    "repository_url": "https://github.com/example/sample-account-service",
                    "default_branch": "main",
                },
            )
            project_id = proj_resp.json()["id"]

            await client.post(
                f"/api/projects/{project_id}/environments",
                json={
                    "name": "local-test",
                    "base_url": "http://127.0.0.1:5001",
                    "environment_type": "local",
                },
            )
            print(f"✅ Registered Project '{proj_resp.json()['name']}' (ID: {project_id[:8]})")

        # 4. Path A: Run First-Round QA & Approve Baseline
        print("\n" + "-" * 70)
        run_a_id = await run_first_round_qa(app_url="http://127.0.0.1:5001", api_url="http://127.0.0.1:8000")

        # Approve baseline
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
            approve_resp = await client.post(f"/api/runs/{run_a_id}/approve-baseline")
            print(f"⭐ Approved Run {run_a_id[:8]} as the project baseline: {approve_resp.json()['status']}")

        # Reset Sample App DB to clean state before regression
        async with httpx.AsyncClient() as client:
            await client.post("http://127.0.0.1:5001/api/reset")

        # 5. Path B: Run Regression Test (Simulating Deliberate Delay & Mutation)
        print("\n" + "-" * 70)
        run_b_id = await run_regression_test(
            baseline_id=run_a_id,
            app_url="http://127.0.0.1:5001",
            api_url="http://127.0.0.1:8000",
        )

        # Reset Sample App DB
        async with httpx.AsyncClient() as client:
            await client.post("http://127.0.0.1:5001/api/reset")

        # 6. Path C: Run Rapid Double-Click & Duplicate Write Check
        print("\n" + "-" * 70)
        run_c_id = await run_repeat_click_test(
            app_url="http://127.0.0.1:5001",
            api_url="http://127.0.0.1:8000",
        )

        # 7. Generate & Persist Reports (HTML, Markdown, JSON)
        print("\n" + "-" * 70)
        print("[Step 6/6] Generating and exporting multi-format reports...")
        reports_dir = os.path.join(BASE_DIR, "reports")
        os.makedirs(reports_dir, exist_ok=True)

        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
            # HTML Report for Regression Run
            html_resp = await client.get(f"/api/runs/{run_b_id}/report?format=html")
            with open(os.path.join(reports_dir, "traceplay_regression_report.html"), "w", encoding="utf-8") as f:
                f.write(html_resp.text)

            # Markdown Report
            md_resp = await client.get(f"/api/runs/{run_b_id}/report?format=markdown")
            with open(os.path.join(reports_dir, "traceplay_regression_report.md"), "w", encoding="utf-8") as f:
                f.write(md_resp.text)

            # JSON Report
            json_resp = await client.get(f"/api/runs/{run_b_id}/report?format=json")
            with open(os.path.join(reports_dir, "traceplay_regression_report.json"), "w", encoding="utf-8") as f:
                f.write(json_resp.text)

        print(f"✅ Reports exported to '{reports_dir}' directory:")
        print("   - traceplay_regression_report.html")
        print("   - traceplay_regression_report.md")
        print("   - traceplay_regression_report.json")

        print("\n" + "=" * 70)
        print("🎉 ALL THREE DEMO PATHS COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        print("▶ TracePlay Control Dashboard: http://localhost:8000/dashboard")
        print("▶ Sample App UI:              http://localhost:5001/")
        print("=" * 70)

    finally:
        # Cleanup child processes
        api_proc.terminate()
        sample_proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
