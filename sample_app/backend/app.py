"""
TracePlay Instrumented Sample Application Backend.
Emits OpenTelemetry spans, manages SQLite test database, and supports
deliberate flaw simulation for regression and multi-click testing.
"""
import os
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter, SpanExporter, SpanExportResult

class SilentSpanExporter(SpanExporter):
    def export(self, spans):
        return SpanExportResult.SUCCESS
    def shutdown(self):
        pass

# Configure tracer for sample application
tracer_provider = TracerProvider()
tracer_provider.add_span_processor(SimpleSpanProcessor(SilentSpanExporter()))
trace.set_tracer_provider(tracer_provider)
tracer = trace.get_tracer("sample-app", "1.0.0")

app = FastAPI(title="TracePlay Sample App")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.path.abspath(os.getenv("SAMPLE_DB_PATH", os.path.join(os.path.dirname(__file__), "../../traceplay_sample.db")))


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_sample_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        display_name TEXT NOT NULL,
        email TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user',
        is_admin INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        details TEXT,
        timestamp TEXT,
        trace_id TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        item TEXT NOT NULL,
        status TEXT NOT NULL,
        amount REAL NOT NULL
    )
    """)
    # Seed initial test user
    cursor.execute("SELECT id FROM users WHERE id = 'user-1'")
    if not cursor.fetchone():
        cursor.execute("""
        INSERT INTO users (id, username, display_name, email, role, is_admin, updated_at)
        VALUES ('user-1', 'alex_tester', 'Alex Baseline', 'alex@example.com', 'qa_member', 0, ?)
        """, (datetime.utcnow().isoformat(),))
    conn.commit()
    conn.close()


init_sample_db()


# ---------------- TracePlay Ingestion Forwarder ---------------- #
# Automatically forwards backend spans to TracePlay Control API if TRACEPLAY_API is set
TRACEPLAY_API_URL = os.getenv("TRACEPLAY_API_URL", "http://localhost:8000")


async def forward_span_to_traceplay(trace_id: str, span_id: str, parent_span_id: Optional[str], service: str, op: str, duration_ms: float, interaction_id: Optional[str], run_id: Optional[str]):
    import httpx
    try:
        async with httpx.AsyncClient(base_url=TRACEPLAY_API_URL, timeout=1.0) as client:
            await client.post(
                "/api/evidence/spans",
                json={
                    "run_id": run_id or "default-run",
                    "interaction_id": interaction_id,
                    "trace_id": trace_id,
                    "span_id": span_id,
                    "parent_span_id": parent_span_id,
                    "service_name": service,
                    "operation_name": op,
                    "status": "ok",
                    "duration_ms": duration_ms,
                },
            )
    except Exception:
        pass


class ProfileUpdateRequest(BaseModel):
    display_name: str
    email: Optional[str] = None
    simulate_delay_ms: Optional[int] = 0
    simulate_unexpected_write: Optional[bool] = False
    simulate_unprotected_double_click: Optional[bool] = False


@app.get("/api/profile")
def get_profile():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = 'user-1'")
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


@app.patch("/api/profile")
async def update_profile(
    data: ProfileUpdateRequest,
    traceparent: Optional[str] = Header(None),
    x_traceplay_interaction_id: Optional[str] = Header(None),
    x_traceplay_run_id: Optional[str] = Header(None),
):
    # Parse trace context or create fallback
    trace_id = traceparent.split("-")[1] if traceparent and len(traceparent.split("-")) >= 3 else uuid.uuid4().hex
    ctrl_span_id = uuid.uuid4().hex[:16]

    start_total = time.time()

    # 1. Controller Span: ProfileController.update
    with tracer.start_as_current_span("ProfileController.update") as ctrl_span:
        # Deliberate Latency Simulation
        if data.simulate_delay_ms and data.simulate_delay_ms > 0:
            time.sleep(data.simulate_delay_ms / 1000.0)

        # 2. Service Span: ProfileService.save
        srv_span_id = uuid.uuid4().hex[:16]
        with tracer.start_as_current_span("ProfileService.save") as srv_span:
            # 3. Repository Span: UserRepository.update
            repo_span_id = uuid.uuid4().hex[:16]
            with tracer.start_as_current_span("UserRepository.update") as repo_span:
                conn = get_db()
                cursor = conn.cursor()

                now_str = datetime.utcnow().isoformat()
                cursor.execute("""
                UPDATE users
                SET display_name = ?, email = COALESCE(?, email), updated_at = ?
                WHERE id = 'user-1'
                """, (data.display_name, data.email, now_str))

                # Deliberate Unexpected Write (Mutating forbidden is_admin field)
                if data.simulate_unexpected_write:
                    cursor.execute("UPDATE users SET is_admin = 1 WHERE id = 'user-1'")

                # Insert Audit Log
                audit_id = str(uuid.uuid4())
                cursor.execute("""
                INSERT INTO audit_logs (id, user_id, action, details, timestamp, trace_id)
                VALUES (?, 'user-1', 'UPDATE_PROFILE', ?, ?, ?)
                """, (audit_id, f"Changed display_name to {data.display_name}", now_str, trace_id))

                conn.commit()
                conn.close()

    total_duration_ms = (time.time() - start_total) * 1000.0

    # Forward spans to TracePlay Evidence API
    await forward_span_to_traceplay(trace_id, ctrl_span_id, None, "ProfileController", "ProfileController.update", total_duration_ms, x_traceplay_interaction_id, x_traceplay_run_id)
    await forward_span_to_traceplay(trace_id, srv_span_id, ctrl_span_id, "ProfileService", "ProfileService.save", total_duration_ms * 0.8, x_traceplay_interaction_id, x_traceplay_run_id)
    await forward_span_to_traceplay(trace_id, repo_span_id, srv_span_id, "UserRepository", "UserRepository.update", total_duration_ms * 0.5, x_traceplay_interaction_id, x_traceplay_run_id)

    return {
        "status": "success",
        "message": "Profile updated successfully",
        "updated_at": now_str,
        "trace_id": trace_id,
        "latency_ms": round(total_duration_ms, 2),
    }


@app.post("/api/reset")
def reset_database():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM audit_logs")
    cursor.execute("""
    UPDATE users
    SET display_name = 'Alex Baseline', email = 'alex@example.com', role = 'qa_member', is_admin = 0, updated_at = ?
    WHERE id = 'user-1'
    """, (datetime.utcnow().isoformat(),))
    conn.commit()
    conn.close()
    return {"status": "reset_complete"}


@app.get("/", response_class=HTMLResponse)
def serve_sample_ui():
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sample Application - User Profile</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; display: flex; justify-content: center; }
  .card { background: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 32px; width: 480px; box-shadow: 0 10px 25px rgba(0,0,0,0.5); }
  h1 { font-size: 1.5rem; margin-bottom: 8px; color: #38bdf8; }
  p { color: #94a3b8; font-size: 0.9rem; margin-bottom: 24px; }
  label { display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 6px; color: #cbd5e1; }
  input[type="text"], input[type="email"] { width: 100%; box-sizing: border-box; padding: 10px 14px; background: #0f172a; border: 1px solid #475569; border-radius: 8px; color: #fff; font-size: 0.95rem; margin-bottom: 18px; }
  .checkbox-group { background: #0b1120; border: 1px solid #334155; border-radius: 8px; padding: 14px; margin-bottom: 20px; }
  .checkbox-group label { display: flex; align-items: center; gap: 8px; font-weight: normal; margin-bottom: 8px; cursor: pointer; color: #e2e8f0; }
  .btn { width: 100%; background: #0284c7; color: #fff; border: none; padding: 12px; border-radius: 8px; font-weight: 700; font-size: 1rem; cursor: pointer; transition: background 0.2s; }
  .btn:hover { background: #0369a1; }
  .btn:disabled { background: #475569; cursor: not-allowed; }
  .toast { margin-top: 20px; padding: 12px; border-radius: 8px; font-size: 0.9rem; display: none; }
  .toast-success { background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; color: #34d399; }
</style>
</head>
<body>
<div class="card">
  <h1>User Profile Settings</h1>
  <p>Sample Web Application under test with TracePlay runtime observability.</p>

  <form id="profile-form">
    <label for="display-name">Display Name</label>
    <input type="text" id="display-name" name="displayName" value="Alex Baseline" required />

    <label for="email">Email Address</label>
    <input type="email" id="email" name="email" value="alex@example.com" required />

    <div class="checkbox-group">
      <div style="font-weight: 600; font-size: 0.8rem; text-transform: uppercase; color: #94a3b8; margin-bottom: 8px;">Deliberate Test Flaw Switches</div>
      <label>
        <input type="checkbox" id="sim-delay" /> Simulate Slow Backend (650ms delay)
      </label>
      <label>
        <input type="checkbox" id="sim-unexpected" /> Simulate Unexpected Write (Mutate is_admin)
      </label>
      <label>
        <input type="checkbox" id="disable-debounce" /> Disable Button Debounce
      </label>
    </div>

    <button type="submit" id="save-button" class="btn">Save changes</button>
  </form>

  <div id="toast" class="toast toast-success">Profile updated successfully!</div>
</div>

<script>
  let isSaving = false;
  const form = document.getElementById("profile-form");
  const saveBtn = document.getElementById("save-button");
  const toast = document.getElementById("toast");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const disableDebounce = document.getElementById("disable-debounce").checked;
    if (!disableDebounce) {
      if (isSaving) return;
      isSaving = true;
      saveBtn.disabled = true;
      saveBtn.innerText = "Saving...";
    }

    const payload = {
      display_name: document.getElementById("display-name").value,
      email: document.getElementById("email").value,
      simulate_delay_ms: document.getElementById("sim-delay").checked ? 650 : 0,
      simulate_unexpected_write: document.getElementById("sim-unexpected").checked,
    };

    try {
      const res = await fetch("/api/profile", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (res.ok) {
        toast.style.display = "block";
        setTimeout(() => toast.style.display = "none", 4000);
      }
    } catch (err) {
      console.error("Update failed", err);
    } finally {
      if (!disableDebounce) {
        isSaving = false;
        saveBtn.disabled = false;
        saveBtn.innerText = "Save changes";
      }
    }
  });
</script>
</body>
</html>
"""
