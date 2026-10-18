"""
Unit tests for TracePlay Latency and Delay Detection Engine.
"""
from apps.api.services.timing_engine import TimingEngine


def test_timing_within_baseline():
    res = TimingEngine.evaluate_timing(
        metric_name="ui_action_save",
        duration_ms=120.0,
        baseline_duration_ms=115.0,
        warn_ms=500.0,
        fail_ms=1500.0,
    )
    assert res["threshold_status"] == "pass"
    assert res["delta_ms"] == 5.0


def test_latency_regression_detected():
    res = TimingEngine.evaluate_timing(
        metric_name="request_latency_patch_profile",
        duration_ms=750.0,
        baseline_duration_ms=120.0,
        warn_ms=500.0,
        fail_ms=1500.0,
    )
    assert res["threshold_status"] in ("warn", "fail")
    assert res["delta_ms"] == 630.0
    assert res["delta_percent"] > 100.0


def test_step_by_step_pause_marked_not_comparable():
    res = TimingEngine.evaluate_timing(
        metric_name="ui_action_step",
        duration_ms=25000.0,  # 25 seconds paused in debug mode
        baseline_duration_ms=100.0,
        is_paused_debug_step=True,
    )
    assert res["threshold_status"] == "not_comparable"
    assert res["delta_ms"] is None
