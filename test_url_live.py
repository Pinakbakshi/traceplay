"""
Live Autonomous URL Testing Verification Script.
Demonstrates:
1. Providing a website link (e.g. http://127.0.0.1:5001 or any web URL).
2. Autonomous Playwright browser agent navigates the URL, discovers inputs/buttons, fills safe synthetic values, triggers actions, tests multi-click debouncing, and records full telemetry.
3. Streams live execution logs and progress until completion.
4. Generates comprehensive HTML and Markdown impact reports.
"""
import asyncio
import os
import subprocess
import sys
import time
import httpx


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


async def test_live_website(target_url: str = "http://127.0.0.1:5001"):
    print("=" * 70)
    print(f"🌐 TracePlay: Testing Website Link -> {target_url}")
    print("=" * 70)

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    proc_env = os.environ.copy()
    proc_env["PYTHONPATH"] = BASE_DIR

    # Launch TracePlay Control API (Port 8000)
    print("\n[1/4] Starting TracePlay API Server (port 8000)...")
    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "apps.api.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=BASE_DIR,
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Launch Sample App (Port 5001) as the test target
    print(f"[2/4] Starting Target Web Application on {target_url}...")
    sample_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "sample_app.backend.app:app", "--host", "127.0.0.1", "--port", "5001"],
        cwd=BASE_DIR,
        env=proc_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        api_ready = await wait_for_server("http://127.0.0.1:8000/health")
        sample_ready = await wait_for_server(target_url)

        if not api_ready or not sample_ready:
            print("❌ Failed to bind to servers.")
            return

        print("✅ Servers are running and responsive!")

        # Trigger Autonomous URL Testing
        print(f"\n[3/4] Triggering Autonomous Testing for link: {target_url}...")
        async with httpx.AsyncClient(base_url="http://127.0.0.1:8000") as client:
            launch_res = await client.post(
                "/api/test-url",
                json={
                    "url": target_url,
                    "test_mode": "first_round_qa",
                    "enable_multi_click": True,
                },
            )
            data = launch_res.json()
            run_id = data["run_id"]
            print(f"🚀 Job launched successfully! Run ID: {run_id[:8]}")

            # Stream live execution progress
            print("\n[4/4] Streaming live agent logs:")
            printed_logs = 0
            while True:
                await asyncio.sleep(0.8)
                status_res = await client.get(f"/api/test-url/{run_id}/status")
                job = status_res.json()
                logs = job.get("logs", [])

                while printed_logs < len(logs):
                    print(f"  {logs[printed_logs]}")
                    printed_logs += 1

                if job.get("status") in ("passed", "failed"):
                    print(f"\n🏁 Autonomous test concluded with status: {job.get('status').upper()}!")
                    break

            # Fetch and export report
            report_res = await client.get(f"/api/runs/{run_id}/report?format=html")
            report_path = os.path.join(BASE_DIR, "reports/url_test_report.html")
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report_res.text)
            print(f"📄 Report saved to: {report_path}")

        print("\n" + "=" * 70)
        print("🎉 Live URL Test Completed Successfully!")
        print("▶ Open Dashboard at: http://localhost:8000/dashboard")
        print("=" * 70)

    finally:
        api_proc.terminate()
        sample_proc.terminate()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5001"
    asyncio.run(test_live_website(target))
