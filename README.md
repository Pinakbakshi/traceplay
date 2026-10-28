# TracePlay — UI-to-Backend Impact Testing Platform

> **Project status (2026-10-29):** TracePlay now includes an authenticated REST API contract probe (`test_api_contract.py`) alongside browser-driven testing. Its CI workflow passed **6 unit tests**, including JSON-path checks and sensitive query-value redaction. A real endpoint still requires a reachable target URL and credentials supplied locally.


> **Platform Location:** `/Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay`

TracePlay is an autonomous testing platform that takes any website URL and automatically:
- Crawls the site with Playwright browser automation
- Captures every network request/response with W3C `traceparent` injection
- Evaluates timing observations (latency, SLA thresholds)
- Detects database state changes (before/after diff)
- Compares runs for regressions
- Generates HTML, Markdown, and JSON reports

---

## Table of Contents

- [Platform Path](#platform-path)
- [Architecture Overview](#architecture-overview)
- [Directory Structure](#directory-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage — Three Ways to Test a URL](#usage--three-ways-to-test-a-url)
  - [1. Dashboard (Browser UI)](#1-dashboard-browser-ui)
  - [2. CLI Script](#2-cli-script)
  - [3. REST API](#3-rest-api)
- [Running the Demo (3-Path)](#running-the-demo-3-path)
- [Running Tests](#running-tests)
- [API Reference](#api-reference)
- [Report Outputs](#report-outputs)
- [Sample App](#sample-app)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Troubleshooting](#troubleshooting)

---

## Platform Path

```
/Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay
```

Set this as your active workspace in Antigravity for the best experience.

---

## Architecture Overview

```
Browser (Playwright)
       │
       ▼
  TracePlay Runner ──► injects W3C traceparent + X-TracePlay-* headers
       │
       ▼
  FastAPI Backend  ──► SQLite (traceplay.db)
  ┌──────────────────────────────────────────┐
  │  /api/test-url         ← URL submission  │
  │  /api/projects         ← project CRUD    │
  │  /api/runs             ← run lifecycle   │
  │  /api/evidence/*       ← span/diff ingest│
  │  /api/graph            ← code graph      │
  │  /api/baseline         ← baseline mgmt   │
  └──────────────────────────────────────────┘
       │
       ▼
  Services Layer
  ┌──────────────────────────────────────────┐
  │  url_tester.py        ← autonomous crawl │
  │  diff_engine.py       ← field-level diffs│
  │  timing_engine.py     ← latency/SLA eval │
  │  regression_engine.py ← run comparison   │
  │  traceability_graph.py← evidence graph   │
  │  report_generator.py  ← HTML/MD/JSON     │
  │  redaction.py         ← PII sanitizer    │
  └──────────────────────────────────────────┘
       │
       ▼
  Dashboard (SPA) ──► apps/dashboard/index.html
  Reports         ──► reports/
```

---

## Directory Structure

```
traceplay/
├── README.md                          ← This file
│
├── apps/
│   ├── api/
│   │   ├── main.py                    ← FastAPI app entrypoint, all routers mounted
│   │   ├── models.py                  ← SQLAlchemy ORM models
│   │   ├── schemas.py                 ← Pydantic request/response schemas
│   │   ├── database.py                ← DB engine, session factory, auto-init
│   │   ├── routes/
│   │   │   ├── projects.py            ← CRUD: projects, environments, scenarios
│   │   │   ├── runs.py                ← Run lifecycle, timeline, diffs, reports
│   │   │   ├── evidence.py            ← Ingest: spans, interactions, network, diffs
│   │   │   ├── baseline.py            ← Baseline approval workflow
│   │   │   ├── graph.py               ← Code graph (GitNexus/Graphify) analysis
│   │   │   └── url_testing.py         ← POST /api/test-url, GET status
│   │   └── services/
│   │       ├── url_tester.py          ← Autonomous browser crawl engine
│   │       ├── diff_engine.py         ← Field-level diff: EXPECTED/UNEXPECTED/FORBIDDEN
│   │       ├── timing_engine.py       ← Latency evaluation, not_comparable support
│   │       ├── regression_engine.py   ← Side-by-side run regression comparator
│   │       ├── traceability_graph.py  ← Evidence graph builder
│   │       ├── report_generator.py    ← HTML / Markdown / JSON report generator
│   │       └── redaction.py           ← Header, payload, DB snapshot PII redactor
│   │
│   └── dashboard/
│       └── index.html                 ← Full SPA: URL bar, live polling, 5 tabs
│
├── packages/
│   ├── traceplay_runner/
│   │   └── runner.py                  ← Playwright runner with OTel traceparent injection
│   ├── db_adapter/
│   │   └── readonly_db_adapter.py     ← Read-only SQLite/PostgreSQL DB snapshotter
│   └── graph_adapters/
│       └── code_graph_analyzer.py     ← AST-based code graph (GitNexus/Graphify adapters)
│
├── sample_app/
│   └── backend/
│       └── app.py                     ← FastAPI sample app with OTel, deliberate flaw switches
│
├── scenarios/
│   ├── test_first_round_qa.py         ← Full first-run QA scenario
│   ├── test_regression.py             ← Regression comparison scenario
│   └── test_repeat_clicks.py          ← Idempotency / repeat-click scenario
│
├── tests/
│   ├── unit/
│   │   ├── test_diff_engine.py        ← Unit tests: diff classification
│   │   ├── test_redaction.py          ← Unit tests: PII redaction
│   │   ├── test_timing_engine.py      ← Unit tests: latency/SLA evaluation
│   │   ├── test_graph_builder.py      ← Unit tests: traceability graph edges
│   │   └── test_url_tester.py         ← Unit tests: URL tester service
│   └── integration/
│       └── test_url_testing_flow.py   ← Integration tests: full URL test flow
│
├── reports/                           ← Generated reports land here
│   ├── traceplay_regression_report.html
│   ├── traceplay_regression_report.md
│   ├── traceplay_regression_report.json
│   └── url_test_report.html
│
├── run_demo.py                        ← Master 3-path demo launcher
└── test_url_live.py                   ← CLI: test any URL from the command line
```

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | 3.9+ | `/usr/bin/python3` on macOS |
| Node.js | 18+ | Required for Playwright browsers; managed via NVM at `/Users/pinakpanibakshi/.nvm/versions/node/v24.14.1` |
| Playwright browsers | Latest | Install once after pip install |

---

## Installation

All dependencies are already installed in the project's virtual environment at `traceplay/.venv`.  
To reinstall from scratch:

```bash
cd /Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay

# Create virtual environment
python3 -m venv .venv

# Activate
source .venv/bin/activate

# Install Python dependencies
pip install fastapi uvicorn pydantic sqlalchemy httpx \
            opentelemetry-api opentelemetry-sdk \
            playwright pytest pytest-asyncio

# Install Playwright browser binaries
playwright install chromium
```

**Installed packages (already present in `.venv`):**

| Package | Purpose |
|---|---|
| `fastapi` | REST API framework |
| `uvicorn` | ASGI server |
| `pydantic` | Data validation / schemas |
| `sqlalchemy` | ORM + SQLite database |
| `httpx` | Async HTTP client |
| `playwright` | Browser automation |
| `opentelemetry-api` | OTel tracing API |
| `opentelemetry-sdk` | OTel SDK + exporters |
| `pytest` | Test runner |
| `pytest-asyncio` | Async test support |

---

## Quick Start

### 1. Start the TracePlay API server

```bash
cd /Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay

PYTHONPATH=. .venv/bin/python -m uvicorn apps.api.main:app \
    --host 0.0.0.0 --port 8000 --reload
```

API is now live at: `http://localhost:8000`  
Interactive API docs: `http://localhost:8000/docs`

### 2. Open the Dashboard

Open in your browser:
```
file:///Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay/apps/dashboard/index.html
```

Or serve it via any static server:
```bash
.venv/bin/python -m http.server 3000 --directory apps/dashboard
# → http://localhost:3000
```

### 3. Test a website

Paste any URL in the "Test Any Website Link" bar in the Dashboard, or use the CLI:
```bash
PYTHONPATH=. .venv/bin/python test_url_live.py https://example.com
```

---

## Usage — Three Ways to Test a URL

### 1. Dashboard (Browser UI)

1. Open `apps/dashboard/index.html` in your browser
2. Paste any URL (e.g. `https://news.ycombinator.com`) into the **"Test Any Website Link"** input at the top
3. Click **"Run Test"**
4. Live progress polls every 2 seconds — watch the status update
5. On completion, tabs appear for:
   - **Timeline** — every interaction captured (clicks, navigations, form fills)
   - **Diffs** — field-level database state changes (EXPECTED / UNEXPECTED / FORBIDDEN)
   - **Timing** — latency observations and SLA pass/fail
   - **Regression** — side-by-side comparison with previous runs
   - **Graph** — code traceability evidence graph

### 2. CLI Script

```bash
cd /Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay

# Basic usage
PYTHONPATH=. .venv/bin/python test_url_live.py https://example.com

# With custom depth and timeout
PYTHONPATH=. .venv/bin/python test_url_live.py https://example.com --depth 3 --timeout 60

# Output report to a specific file
PYTHONPATH=. .venv/bin/python test_url_live.py https://example.com --output reports/my_report.html
```

The CLI prints a summary to stdout and saves an HTML report to `reports/url_test_report.html`.

### 3. REST API

**Submit a URL test:**
```bash
curl -X POST http://localhost:8000/api/test-url \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "depth": 2, "timeout": 30}'
```

Response:
```json
{
  "run_id": "abc123",
  "status": "running",
  "message": "URL test started"
}
```

**Poll for status:**
```bash
curl http://localhost:8000/api/test-url/abc123/status
```

Response when complete:
```json
{
  "run_id": "abc123",
  "status": "complete",
  "interactions": 12,
  "network_events": 47,
  "diffs": 3,
  "timing_observations": 12,
  "report_url": "/reports/abc123.html"
}
```

**List all runs:**
```bash
curl http://localhost:8000/api/runs
```

---

## Running the Demo (3-Path)

The master demo exercises all three testing paths in sequence:

```bash
cd /Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay

PYTHONPATH=. .venv/bin/python run_demo.py
```

**What it runs:**

| Path | Description |
|---|---|
| **Path 1** | First-round QA — crawls sample app, captures baseline snapshot |
| **Path 2** | Regression run — re-crawls with deliberate flaw, compares to baseline |
| **Path 3** | Repeat-click idempotency — clicks same element multiple times, checks for state drift |

Outputs HTML, Markdown, and JSON reports to `reports/`.

### Start the Sample App (for Path 1–3 demo)

```bash
cd /Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay

# Terminal 1: start sample backend
PYTHONPATH=. .venv/bin/python -m uvicorn sample_app.backend.app:app \
    --host 0.0.0.0 --port 8080

# Terminal 2: run the demo against it
PYTHONPATH=. .venv/bin/python run_demo.py
```

---

## Running Tests

```bash
cd /Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay

# All tests (12 tests total, all passing)
PYTHONPATH=. .venv/bin/pytest tests/ -v

# Unit tests only
PYTHONPATH=. .venv/bin/pytest tests/unit/ -v

# Integration tests only
PYTHONPATH=. .venv/bin/pytest tests/integration/ -v

# Specific test file
PYTHONPATH=. .venv/bin/pytest tests/unit/test_diff_engine.py -v
```

**Test suite (12 tests, all passing):**

| Test File | Tests | Coverage |
|---|---|---|
| `test_diff_engine.py` | 3 | EXPECTED_CHANGE, UNEXPECTED_CHANGE, FORBIDDEN_CHANGE_DETECTED |
| `test_redaction.py` | 2 | Header redaction, payload PII scrub |
| `test_timing_engine.py` | 2 | SLA pass, SLA fail, not_comparable |
| `test_graph_builder.py` | 2 | Edge creation, node deduplication |
| `test_url_tester.py` | 1 | URL tester service construction |
| `test_url_testing_flow.py` | 2 | Full integration: submit + status poll |

---

## API Reference

All endpoints are available at `http://localhost:8000`. Interactive docs at `/docs`.

### URL Testing

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/test-url` | Submit a URL for autonomous testing |
| `GET` | `/api/test-url/{run_id}/status` | Poll the status of a test run |

### Projects

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/projects` | List all projects |
| `POST` | `/api/projects` | Create a new project |
| `GET` | `/api/projects/{id}` | Get a specific project |

### Runs

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/runs` | List all runs |
| `POST` | `/api/runs` | Create a new run |
| `GET` | `/api/runs/{id}` | Get run details |
| `GET` | `/api/runs/{id}/timeline` | Get all interactions in order |
| `GET` | `/api/runs/{id}/diffs` | Get field-level DB diffs |
| `GET` | `/api/runs/{id}/timing` | Get timing observations |
| `GET` | `/api/runs/{id}/regression` | Get regression comparison |
| `GET` | `/api/runs/{id}/graph` | Get traceability evidence graph |
| `GET` | `/api/runs/{id}/report` | Generate HTML/MD/JSON report |

### Evidence Ingestion

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/evidence/spans` | Ingest OTel backend spans |
| `POST` | `/api/evidence/interactions` | Ingest browser interactions |
| `POST` | `/api/evidence/network` | Ingest network events |
| `POST` | `/api/evidence/diffs` | Ingest DB state diffs |

### Baseline & Graph

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/baseline/approve` | Approve a run as baseline |
| `GET` | `/api/baseline/{project_id}` | Get current baseline |
| `POST` | `/api/graph/analyze` | Analyze code graph for a repo path |

---

## Report Outputs

All reports are saved to:
```
/Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay/reports/
```

| File | Format | Contents |
|---|---|---|
| `traceplay_regression_report.html` | HTML | Full interactive regression report |
| `traceplay_regression_report.md` | Markdown | Human-readable regression summary |
| `traceplay_regression_report.json` | JSON | Machine-readable full data export |
| `url_test_report.html` | HTML | URL test crawl + analysis report |

Reports include:
- **Run metadata** (URL, timestamp, duration)
- **Interaction timeline** (every click, navigation, form fill)
- **Network events** (requests, responses, timing)
- **DB diffs** (EXPECTED_CHANGE / UNEXPECTED_CHANGE / FORBIDDEN_CHANGE_DETECTED)
- **Timing analysis** (SLA pass/fail, latency histograms)
- **Regression comparison** (side-by-side with baseline)
- **Traceability graph** (UI action → network call → backend span → DB change)

---

## Sample App

A fully instrumented sample FastAPI application is included for local end-to-end demos.

**Location:** `sample_app/backend/app.py`

**Features:**
- OpenTelemetry tracing (reads `traceparent` from incoming headers)
- SQLite database for todo items
- Deliberate flaw switches (toggle via environment variables to simulate regressions):
  - `INTRODUCE_SLOW_QUERY=1` — adds artificial 2s delay to simulate SLA breach
  - `INTRODUCE_BAD_WRITE=1` — writes incorrect data to trigger UNEXPECTED_CHANGE diff
  - `INTRODUCE_FORBIDDEN_WRITE=1` — writes to forbidden field to trigger FORBIDDEN_CHANGE_DETECTED

**Start:**
```bash
cd /Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay

# Normal mode
PYTHONPATH=. .venv/bin/python -m uvicorn sample_app.backend.app:app --port 8080

# With regression flaw
INTRODUCE_BAD_WRITE=1 PYTHONPATH=. .venv/bin/python -m uvicorn sample_app.backend.app:app --port 8080
```

---

## Configuration & Environment Variables

| Variable | Default | Description |
|---|---|---|
| `TRACEPLAY_DB_PATH` | `<project_root>/traceplay.db` | SQLite database file path |
| `TRACEPLAY_REPORT_DIR` | `<project_root>/reports/` | Directory for generated reports |
| `TRACEPLAY_MAX_DEPTH` | `2` | Default crawl depth for URL testing |
| `TRACEPLAY_TIMEOUT` | `30` | Default per-page timeout (seconds) |
| `INTRODUCE_SLOW_QUERY` | `0` | Sample app: simulate slow DB query |
| `INTRODUCE_BAD_WRITE` | `0` | Sample app: simulate bad data write |
| `INTRODUCE_FORBIDDEN_WRITE` | `0` | Sample app: simulate forbidden field write |

---

## Troubleshooting

### API server doesn't start
Make sure to run from within the `traceplay/` directory with `PYTHONPATH=.`:
```bash
cd /Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay
PYTHONPATH=. .venv/bin/python -m uvicorn apps.api.main:app --port 8000
```

### Playwright browsers not found
```bash
cd /Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay
.venv/bin/python -m playwright install chromium
```

### Node.js / Playwright requires NVM
Node.js is managed via NVM. Make sure NVM is initialized in your shell:
```bash
source ~/.nvm/nvm.sh
nvm use 24   # or the installed version
```
Node is at: `/Users/pinakpanibakshi/.nvm/versions/node/v24.14.1`

### Tests import errors
Always set `PYTHONPATH=.` when running tests:
```bash
cd /Users/pinakpanibakshi/.gemini/antigravity/scratch/traceplay
PYTHONPATH=. .venv/bin/pytest tests/ -v
```

### Dashboard shows "Cannot connect to API"
The dashboard defaults to `http://localhost:8000`. Make sure the API server is running first.

### Database path errors
All components use absolute DB paths resolved relative to their own `__file__`. Do not move files without updating `database.py`.

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| SQLite (not PostgreSQL) | Zero-config local dev; swap the `DATABASE_URL` in `database.py` for PostgreSQL in production |
| Python 3.9 compatible | No f-string nesting; uses `str.join()` patterns in `report_generator.py` |
| W3C `traceparent` injection | Standard OTel propagation so any OTel-instrumented backend auto-correlates |
| PII redaction on all ingestion | `redaction.py` runs on every span, network event, and DB snapshot before storage |
| Diff classification | Three severity levels: EXPECTED_CHANGE (expected), UNEXPECTED_CHANGE (investigate), FORBIDDEN_CHANGE_DETECTED (alert) |
| Absolute SQLite paths | `os.path.abspath(os.path.join(os.path.dirname(__file__), ...))` prevents CWD-relative path bugs |

---

## REST API contract probing (new)

The browser crawler is useful for UI-driven flows, but it cannot reliably validate authenticated JSON APIs by itself. Use the TracePlay API contract CLI for endpoint-level checks with explicit status and response invariants.

```bash
# From the TracePlay repository root. Store the key in the environment; don't paste it into shell history.
export CRYPTO_API_KEY='your-real-api-key'
PYTHONPATH=. .venv/bin/python test_api_contract.py \
  --url 'https://your-deployed-api.example/analysis/technical-signal' \
  --header 'X-API-Key=@CRYPTO_API_KEY' \
  --param symbol=BTCUSDT \
  --param timeframe=1h \
  --require-json-path analysis.score \
  --require-json-path analysis.signal \
  --require-json-path analysis.components \
  --require-json-path analysis.drivers \
  --report reports/crypto-technical-signal-contract.json
```

- The CLI sends one request, validates the expected HTTP status and required dot-separated JSON paths, and returns a JSON report with latency and pass/fail checks.
- Header values using `@ENV_NAME` are resolved from the environment and are not written to the report.
- Use a reachable deployed URL or run the target API locally and point TracePlay at it. No live endpoint can be validated until a target URL and valid credential are configured.
- This validates the API contract and response structure, **not** forecast accuracy or profitability. Use chronological walk-forward backtesting for predictive claims.
- Run the offline tests with `PYTHONPATH=. .venv/bin/python -m unittest tests.unit.test_api_contract -v`.

---

*Generated by TracePlay autonomous testing platform.*
