"""
TracePlay Regression Engine.
Performs side-by-side comparison between current run and an approved baseline run.
Identifies regressions, latency spikes, unexpected mutations, and missing or extra calls.
"""
import json
from typing import Any, Dict, List, Optional


class RegressionEngine:
    @staticmethod
    def compare_runs(
        current_run: Dict[str, Any],
        baseline_run: Dict[str, Any],
        current_events: List[Dict[str, Any]],
        baseline_events: List[Dict[str, Any]],
        current_diffs: List[Dict[str, Any]],
        baseline_diffs: List[Dict[str, Any]],
        current_timings: List[Dict[str, Any]],
        baseline_timings: List[Dict[str, Any]],
        current_assertions: List[Dict[str, Any]],
        baseline_assertions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        differences = []

        # 1. Compare Assertions (NEW_FAILURE, FIXED_FAILURE)
        baseline_assert_map = {a.get("description"): a for a in baseline_assertions}
        for ca in current_assertions:
            desc = ca.get("description")
            c_status = ca.get("status")
            ba = baseline_assert_map.get(desc)
            b_status = ba.get("status") if ba else None

            if c_status == "failed" and b_status == "passed":
                differences.append({
                    "difference_type": "NEW_FAILURE",
                    "severity": "critical",
                    "classification_reason": f"Assertion '{desc}' failed in current run but passed in baseline",
                    "baseline_value_json": json.dumps({"status": b_status}),
                    "current_value_json": json.dumps({"status": c_status}),
                    "delta_json": json.dumps({"description": desc}),
                    "evidence_refs_json": json.dumps(ca.get("evidence_refs_json") or {}),
                })
            elif c_status == "passed" and b_status == "failed":
                differences.append({
                    "difference_type": "FIXED_FAILURE",
                    "severity": "info",
                    "classification_reason": f"Assertion '{desc}' passed in current run, was previously failing",
                    "baseline_value_json": json.dumps({"status": b_status}),
                    "current_value_json": json.dumps({"status": c_status}),
                    "delta_json": json.dumps({"description": desc}),
                })

        # 2. Compare Network Events (CALL_COUNT_CHANGED, missing or unexpected endpoints)
        baseline_route_counts: Dict[str, int] = {}
        for be in baseline_events:
            route_key = f"{be.get('method')} {be.get('route_template')}"
            baseline_route_counts[route_key] = baseline_route_counts.get(route_key, 0) + 1

        current_route_counts: Dict[str, int] = {}
        for ce in current_events:
            route_key = f"{ce.get('method')} {ce.get('route_template')}"
            current_route_counts[route_key] = current_route_counts.get(route_key, 0) + 1

        all_routes = set(baseline_route_counts.keys()) | set(current_route_counts.keys())
        for rk in all_routes:
            b_count = baseline_route_counts.get(rk, 0)
            c_count = current_route_counts.get(rk, 0)
            if b_count != c_count:
                severity = "critical" if (c_count == 0 or c_count > b_count * 2) else "warning"
                differences.append({
                    "difference_type": "CALL_COUNT_CHANGED",
                    "severity": severity,
                    "classification_reason": f"Endpoint '{rk}' call count changed from {b_count} (baseline) to {c_count} (current)",
                    "baseline_value_json": json.dumps({"count": b_count}),
                    "current_value_json": json.dumps({"count": c_count}),
                    "delta_json": json.dumps({"delta": c_count - b_count, "route": rk}),
                })

        # 3. Compare Timings (LATENCY_REGRESSION)
        baseline_timing_map = {t.get("metric_name"): t for t in baseline_timings}
        for ct in current_timings:
            m_name = ct.get("metric_name")
            bt = baseline_timing_map.get(m_name)
            if bt:
                b_dur = bt.get("duration_ms", 0)
                c_dur = ct.get("duration_ms", 0)
                delta = c_dur - b_dur
                delta_pct = (delta / b_dur * 100.0) if b_dur > 0 else 0
                if delta > 200.0 and delta_pct > 25.0:
                    differences.append({
                        "difference_type": "LATENCY_REGRESSION",
                        "severity": "warning",
                        "classification_reason": f"Metric '{m_name}' latency increased by {round(delta, 1)}ms ({round(delta_pct, 1)}%) compared to baseline",
                        "baseline_value_json": json.dumps({"duration_ms": b_dur}),
                        "current_value_json": json.dumps({"duration_ms": c_dur}),
                        "delta_json": json.dumps({"delta_ms": round(delta, 1), "delta_percent": round(delta_pct, 1)}),
                    })

        # 4. Compare Data Diffs (DATA_DIFF_CHANGED, UNEXPECTED_CHANGE)
        baseline_diff_keys = {f"{d.get('entity_type')}.{d.get('field_name')}": d for d in baseline_diffs}
        for cd in current_diffs:
            dk = f"{cd.get('entity_type')}.{cd.get('field_name')}"
            c_status = cd.get("expectation_status")
            if c_status in ("UNEXPECTED_CHANGE", "FORBIDDEN_CHANGE_DETECTED"):
                differences.append({
                    "difference_type": "DATA_DIFF_CHANGED",
                    "severity": "critical",
                    "classification_reason": f"Unexpected data change on '{dk}' detected (value: {cd.get('after_value_redacted')})",
                    "baseline_value_json": json.dumps(baseline_diff_keys.get(dk, {})),
                    "current_value_json": json.dumps(cd),
                    "delta_json": json.dumps({"field": dk, "status": c_status}),
                })

        return differences
