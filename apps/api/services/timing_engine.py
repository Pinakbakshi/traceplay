"""
TracePlay Latency and Delay Detection Engine.
Computes timings across UI actions, network requests, backend spans, and async completion.
Evaluates against baseline and configured thresholds.
"""
from typing import Any, Dict, List, Optional


class TimingPolicy:
    DEFAULT_INTERACTION_TIMEOUT_MS = 8000.0
    DEFAULT_REQUEST_WARN_MS = 500.0
    DEFAULT_REQUEST_FAIL_MS = 1500.0
    DEFAULT_ABSOLUTE_DELTA_WARN_MS = 200.0
    DEFAULT_RELATIVE_DELTA_WARN_PERCENT = 25.0


class TimingEngine:
    @staticmethod
    def evaluate_timing(
        metric_name: str,
        duration_ms: float,
        baseline_duration_ms: Optional[float] = None,
        warn_ms: Optional[float] = None,
        fail_ms: Optional[float] = None,
        absolute_delta_warn_ms: float = TimingPolicy.DEFAULT_ABSOLUTE_DELTA_WARN_MS,
        relative_delta_warn_percent: float = TimingPolicy.DEFAULT_RELATIVE_DELTA_WARN_PERCENT,
        is_paused_debug_step: bool = False,
    ) -> Dict[str, Any]:
        """
        Evaluate a single timing observation against thresholds and baseline.
        If paused in step-by-step debug, wall-clock time is marked not_comparable!
        """
        if is_paused_debug_step and "ui_action" in metric_name:
            return {
                "metric_name": metric_name,
                "duration_ms": duration_ms,
                "baseline_duration_ms": baseline_duration_ms,
                "delta_ms": None,
                "delta_percent": None,
                "threshold_status": "not_comparable",
                "reason": "Step paused during step-by-step debug mode",
            }

        delta_ms = None
        delta_percent = None
        threshold_status = "pass"
        reason = "Within normal thresholds"

        # Compare with baseline if present
        if baseline_duration_ms is not None and baseline_duration_ms > 0:
            delta_ms = round(duration_ms - baseline_duration_ms, 2)
            delta_percent = round((delta_ms / baseline_duration_ms) * 100.0, 2)

            if delta_ms > absolute_delta_warn_ms and delta_percent > relative_delta_warn_percent:
                threshold_status = "warn"
                reason = f"Latency increased by {delta_ms}ms ({delta_percent}%) vs baseline"

        # Check hard threshold limits
        if fail_ms is not None and duration_ms > fail_ms:
            threshold_status = "fail"
            reason = f"Duration {duration_ms}ms exceeded fail threshold of {fail_ms}ms"
        elif warn_ms is not None and duration_ms > warn_ms and threshold_status != "fail":
            threshold_status = "warn"
            reason = f"Duration {duration_ms}ms exceeded warning threshold of {warn_ms}ms"

        return {
            "metric_name": metric_name,
            "duration_ms": round(duration_ms, 2),
            "baseline_duration_ms": round(baseline_duration_ms, 2) if baseline_duration_ms else None,
            "delta_ms": delta_ms,
            "delta_percent": delta_percent,
            "threshold_status": threshold_status,
            "reason": reason,
        }
