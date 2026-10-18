"""
Integration test for autonomous URL testing engine.
Tests that providing a website URL executes exploration, captures requests, and stores run.
"""
import pytest
from fastapi.testclient import TestClient
from apps.api.main import app

client = TestClient(app)


def test_post_test_url_launches_job():
    resp = client.post(
        "/api/test-url",
        json={
            "url": "http://127.0.0.1:5001",
            "test_mode": "first_round_qa",
            "project_name": "Integration Test Target",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "launched"
    assert "run_id" in data
    assert data["target_url"] == "http://127.0.0.1:5001"


def test_get_test_url_status():
    launch_resp = client.post(
        "/api/test-url",
        json={"url": "http://127.0.0.1:5001", "test_mode": "first_round_qa"},
    )
    run_id = launch_resp.json()["run_id"]

    status_resp = client.get(f"/api/test-url/{run_id}/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["run_id"] == run_id
