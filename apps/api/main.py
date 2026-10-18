"""
TracePlay Control and Ingestion API Main Application.
"""
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from apps.api.database import init_db
from apps.api.routes.projects import router as projects_router
from apps.api.routes.runs import router as runs_router
from apps.api.routes.evidence import router as evidence_router
from apps.api.routes.baseline import router as baseline_router
from apps.api.routes.graph import router as graph_router
from apps.api.routes.url_testing import router as url_testing_router

app = FastAPI(
    title="TracePlay Control & Ingestion API",
    description="UI-to-Backend Impact Testing Platform with Playwright, OpenTelemetry & Code Knowledge Graph",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API Routers
app.include_router(projects_router)
app.include_router(runs_router)
app.include_router(evidence_router)
app.include_router(baseline_router)
app.include_router(graph_router)
app.include_router(url_testing_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def serve_dashboard():
    dashboard_path = os.path.join(os.path.dirname(__file__), "../dashboard/index.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return f.read()
    return "<h1>TracePlay Dashboard</h1><p>Dashboard HTML not found.</p>"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("apps.api.main:app", host="0.0.0.0", port=8000, reload=True)
