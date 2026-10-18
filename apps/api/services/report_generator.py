"""
TracePlay Report Generator.
Produces navigable HTML, Markdown, and machine-readable JSON reports.
Embeds UI timeline, network requests, trace spans, verified data diffs,
timing regressions, and GitNexus/Graphify code impact paths.
"""
import json
from datetime import datetime
from typing import Any, Dict, List


class ReportGenerator:
    @staticmethod
    def generate_json_report(
        run: Dict[str, Any],
        interactions: List[Dict[str, Any]],
        network_events: List[Dict[str, Any]],
        backend_spans: List[Dict[str, Any]],
        data_diffs: List[Dict[str, Any]],
        assertions: List[Dict[str, Any]],
        timings: List[Dict[str, Any]],
        regressions: List[Dict[str, Any]],
        graph_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "traceplay_version": "1.0.0",
            "report_generated_at": datetime.utcnow().isoformat(),
            "run": run,
            "summary": {
                "total_interactions": len(interactions),
                "total_requests": len(network_events),
                "total_spans": len(backend_spans),
                "total_diffs": len(data_diffs),
                "total_assertions": len(assertions),
                "passed_assertions": sum(1 for a in assertions if a.get("status") == "passed"),
                "failed_assertions": sum(1 for a in assertions if a.get("status") == "failed"),
                "regressions_detected": len(regressions),
                "overall_status": run.get("status", "unknown"),
            },
            "timeline": interactions,
            "network": network_events,
            "traces": backend_spans,
            "data_diffs": data_diffs,
            "assertions": assertions,
            "timings": timings,
            "regressions": regressions,
            "traceability_graph": graph_data,
        }

    @staticmethod
    def generate_markdown_report(report_data: Dict[str, Any]) -> str:
        run = report_data["run"]
        summary = report_data["summary"]
        diffs = report_data["data_diffs"]
        timings = report_data["timings"]
        regressions = report_data["regressions"]
        assertions = report_data["assertions"]

        status_emoji = "✅ PASS" if summary["overall_status"] == "passed" else "❌ FAIL"

        lines = [
            f"# TracePlay Impact & Verification Report: {status_emoji}",
            "",
            f"- **Run ID:** `{run.get('id')}`",
            f"- **Test Mode:** `{run.get('test_mode')}`",
            f"- **Status:** **{summary['overall_status'].upper()}**",
            f"- **Commit SHA:** `{run.get('commit_sha')}` | **Build:** `{run.get('application_build')}`",
            f"- **Baseline Status:** `{run.get('baseline_status')}` (Baseline ID: `{run.get('baseline_run_id') or 'N/A'}`)",
            f"- **Total Interactions:** {summary['total_interactions']} | **Requests:** {summary['total_requests']} | **Spans:** {summary['total_spans']}",
            f"- **Assertions:** {summary['passed_assertions']} passed / {summary['failed_assertions']} failed",
            "",
            "---",
            "",
            "## 1. Verified Data Diffs (Database State)",
            "",
        ]

        if not diffs:
            lines.append("_No database mutations observed in configured scope._\n")
        else:
            lines.append("| Entity | Field | Change Type | Expectation Status | Causality | Before -> After |")
            lines.append("|---|---|---|---|---|---|")
            for d in diffs:
                b_val = d.get("before_value_redacted", "null")
                a_val = d.get("after_value_redacted", "null")
                exp = d.get("expectation_status")
                caus = d.get("causality_status")
                lines.append(f"| `{d.get('entity_type')}` | `{d.get('field_name')}` | `{d.get('change_type')}` | **{exp}** | `{caus}` | `{b_val}` → `{a_val}` |")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 2. Latency & Delay Measurements",
            "",
        ])

        if not timings:
            lines.append("_No timing observations recorded._\n")
        else:
            lines.append("| Metric | Duration | Baseline | Delta | Threshold Status | Source |")
            lines.append("|---|---|---|---|---|---|")
            for t in timings:
                b_dur = f"{t.get('baseline_duration_ms')}ms" if t.get('baseline_duration_ms') else "N/A"
                delta = f"{t.get('delta_ms')}ms ({t.get('delta_percent')}%)" if t.get('delta_ms') is not None else "N/A"
                lines.append(f"| `{t.get('metric_name')}` | **{t.get('duration_ms')}ms** | {b_dur} | {delta} | `{t.get('threshold_status')}` | `{t.get('measurement_source')}` |")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 3. Regression & Anomaly Findings",
            "",
        ])

        if not regressions:
            lines.append("🎉 **No regressions detected** compared to baseline.\n")
        else:
            lines.append("| Severity | Difference Type | Reason |")
            lines.append("|---|---|---|")
            for r in regressions:
                sev = f"**{r.get('severity').upper()}**"
                lines.append(f"| {sev} | `{r.get('difference_type')}` | {r.get('classification_reason')} |")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 4. UI Interaction Timeline & Correlation Trail",
            "",
        ])

        for inter in report_data.get("timeline", []):
            lines.append(f"### Step {inter.get('step_index')}: {inter.get('action_label')}")
            lines.append(f"- **Action:** `{inter.get('action_type')}` | **Status:** `{inter.get('status')}`")
            lines.append(f"- **Page URL:** `{inter.get('page_url_before')}` → `{inter.get('page_url_after')}`")
            lines.append("")

        lines.extend([
            "---",
            "",
            "## 5. Traceability Graph Provenance",
            "",
            "> **Core Evidence Principle:**",
            "> - **Runtime Observed:** Directly captured during browser/network/backend test execution.",
            "> - **Verified:** Validated by explicit data or UI assertions.",
            "> - **Static Extracted / Inferred:** Derived via GitNexus/Graphify AST code graph. _Not guaranteed to execute at runtime unless correlated with a backend span._",
            "",
        ])

        return "\n".join(lines)

    @staticmethod
    def generate_html_report(report_data: Dict[str, Any]) -> str:
        """
        Standalone, interactive HTML report with embedded styles and structured sections.
        Constructed cleanly for broad Python version compatibility.
        """
        run = report_data["run"]
        summary = report_data["summary"]
        diffs = report_data["data_diffs"]
        timings = report_data["timings"]
        regressions = report_data["regressions"]
        assertions = report_data["assertions"]
        graph = report_data["traceability_graph"]

        is_passed = summary["overall_status"] == "passed"
        badge_bg = "#10b981" if is_passed else "#ef4444"

        # Build regressions table HTML
        if not regressions:
            regressions_html = "<p style='color: var(--text-muted);'>No regressions or behavioral anomalies detected versus baseline.</p>"
        else:
            reg_rows = []
            for r in regressions:
                reg_rows.append(
                    f"<tr><td><span class='tag tag-fail'>{r.get('severity', '').upper()}</span></td>"
                    f"<td><span class='code'>{r.get('difference_type')}</span></td>"
                    f"<td>{r.get('classification_reason')}</td>"
                    f"<td><span class='code'>{r.get('delta_json')}</span></td></tr>"
                )
            regressions_html = (
                "<table><thead><tr><th>Severity</th><th>Difference Type</th><th>Reason</th><th>Baseline vs Current</th></tr></thead>"
                f"<tbody>{''.join(reg_rows)}</tbody></table>"
            )

        # Build diffs table HTML
        if not diffs:
            diffs_html = "<p style='color: var(--text-muted);'>No scoped mutations observed.</p>"
        else:
            diff_rows = []
            for d in diffs:
                exp_class = "tag-pass" if d.get("expectation_status") == "EXPECTED_CHANGE" else "tag-fail"
                diff_rows.append(
                    f"<tr><td><span class='code'>{d.get('entity_type')}</span></td>"
                    f"<td><b>{d.get('field_name')}</b></td>"
                    f"<td><span class='tag {exp_class}'>{d.get('change_type')}</span></td>"
                    f"<td><span class='tag {exp_class}'>{d.get('expectation_status')}</span></td>"
                    f"<td><span class='tag tag-purple'>{d.get('causality_status')}</span></td>"
                    f"<td><span class='code'>{d.get('before_value_redacted', 'null')}</span> → <span class='code'>{d.get('after_value_redacted', 'null')}</span></td></tr>"
                )
            diffs_html = (
                "<table><thead><tr><th>Entity</th><th>Field</th><th>Change Type</th><th>Expectation Status</th><th>Causality</th><th>Before -> After</th></tr></thead>"
                f"<tbody>{''.join(diff_rows)}</tbody></table>"
            )

        # Build timings table HTML
        if not timings:
            timings_html = "<p style='color: var(--text-muted);'>No timing observations recorded.</p>"
        else:
            timing_rows = []
            for t in timings:
                status_class = "tag-pass" if t.get("threshold_status") == "pass" else "tag-warn"
                b_str = f"{t.get('baseline_duration_ms')}ms" if t.get("baseline_duration_ms") else "N/A"
                d_str = f"{t.get('delta_ms')}ms ({t.get('delta_percent')}%)" if t.get("delta_ms") is not None else "N/A"
                timing_rows.append(
                    f"<tr><td><span class='code'>{t.get('metric_name')}</span></td>"
                    f"<td><b>{t.get('duration_ms')}ms</b></td>"
                    f"<td>{b_str}</td>"
                    f"<td>{d_str}</td>"
                    f"<td><span class='tag {status_class}'>{t.get('threshold_status')}</span></td>"
                    f"<td>{t.get('measurement_source')}</td></tr>"
                )
            timings_html = (
                "<table><thead><tr><th>Metric Name</th><th>Duration</th><th>Baseline</th><th>Delta</th><th>Status</th><th>Source</th></tr></thead>"
                f"<tbody>{''.join(timing_rows)}</tbody></table>"
            )

        # Build graph edges table HTML
        edge_rows = []
        for e in graph.get("edges", []):
            e_class = "tag-pass" if e.get("evidence_class") == "runtime_observed" else "tag-purple" if e.get("evidence_class") == "static_extracted" else "tag-warn"
            edge_rows.append(
                f"<tr><td><span class='code'>{e.get('relationship')}</span></td>"
                f"<td><span class='code'>{e.get('source')}</span></td>"
                f"<td><span class='code'>{e.get('target')}</span></td>"
                f"<td><span class='tag {e_class}'>{e.get('evidence_class')}</span></td>"
                f"<td>{e.get('provenance')}</td></tr>"
            )
        edges_html = (
            "<table><thead><tr><th>Relationship</th><th>Source</th><th>Target</th><th>Evidence Class</th><th>Provenance</th></tr></thead>"
            f"<tbody>{''.join(edge_rows)}</tbody></table>"
        )

        reg_count_color = "var(--danger)" if len(regressions) > 0 else "var(--success)"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TracePlay Report - Run {run.get('id', '')[:8]}</title>
<style>
  :root {{
    --bg: #0f172a;
    --card: #1e293b;
    --border: #334155;
    --text: #f8fafc;
    --text-muted: #94a3b8;
    --primary: #38bdf8;
    --success: #10b981;
    --danger: #ef4444;
    --warning: #f59e0b;
    --purple: #a855f7;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); padding: 24px; line-height: 1.5; }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 20px; margin-bottom: 24px; }}
  .badge {{ background: {badge_bg}; color: #fff; padding: 6px 14px; border-radius: 9999px; font-weight: 700; font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 18px; }}
  .card-title {{ color: var(--text-muted); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 6px; }}
  .card-value {{ font-size: 1.5rem; font-weight: 700; color: var(--text); }}
  .section {{ background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 24px; }}
  .section h2 {{ font-size: 1.25rem; margin-bottom: 16px; color: var(--primary); display: flex; align-items: center; gap: 8px; }}
  table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9rem; }}
  th, td {{ padding: 10px 12px; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--text-muted); font-weight: 600; text-transform: uppercase; font-size: 0.75rem; }}
  .tag {{ display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 0.75rem; font-weight: 600; }}
  .tag-pass {{ background: rgba(16, 185, 129, 0.2); color: var(--success); }}
  .tag-fail {{ background: rgba(239, 68, 68, 0.2); color: var(--danger); }}
  .tag-warn {{ background: rgba(245, 158, 11, 0.2); color: var(--warning); }}
  .tag-purple {{ background: rgba(168, 85, 247, 0.2); color: var(--purple); }}
  .code {{ font-family: monospace; background: #090d16; padding: 2px 6px; border-radius: 4px; font-size: 0.85rem; color: #38bdf8; }}
  .node-box {{ display: inline-block; padding: 4px 10px; margin: 4px; border-radius: 6px; font-size: 0.8rem; font-family: monospace; }}
  .observed-node {{ border: 1px solid var(--success); background: rgba(16, 185, 129, 0.1); color: var(--success); }}
  .verified-node {{ border: 1px solid var(--primary); background: rgba(56, 189, 248, 0.1); color: var(--primary); }}
  .static-node {{ border: 1px solid var(--purple); background: rgba(168, 85, 247, 0.1); color: var(--purple); }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1 style="font-size: 1.8rem; font-weight: 800;">TracePlay Impact & Verification Report</h1>
      <p style="color: var(--text-muted); font-size: 0.9rem;">Run ID: <span class="code">{run.get('id', '')}</span> | Commit: <span class="code">{run.get('commit_sha', '')}</span> | Mode: <span class="code">{run.get('test_mode', '')}</span></p>
    </div>
    <div class="badge">{summary['overall_status']}</div>
  </div>

  <div class="grid">
    <div class="card">
      <div class="card-title">Interactions</div>
      <div class="card-value">{summary['total_interactions']}</div>
    </div>
    <div class="card">
      <div class="card-title">Network Requests</div>
      <div class="card-value">{summary['total_requests']}</div>
    </div>
    <div class="card">
      <div class="card-title">Backend Spans</div>
      <div class="card-value">{summary['total_spans']}</div>
    </div>
    <div class="card">
      <div class="card-title">Data Diffs</div>
      <div class="card-value">{summary['total_diffs']}</div>
    </div>
    <div class="card">
      <div class="card-title">Regressions / Anomalies</div>
      <div class="card-value" style="color: {reg_count_color};">{len(regressions)}</div>
    </div>
  </div>

  <!-- Regressions & Anomalies Section -->
  <div class="section">
    <h2>⚠️ Regressions & Anomalies Detected ({len(regressions)})</h2>
    {regressions_html}
  </div>

  <!-- Database Diffs Section -->
  <div class="section">
    <h2>🗄️ Database State Diffs ({len(diffs)})</h2>
    {diffs_html}
  </div>

  <!-- Timing Section -->
  <div class="section">
    <h2>⏱️ Latency & Timing Measurements</h2>
    {timings_html}
  </div>

  <!-- Traceability Chain -->
  <div class="section">
    <h2>🔗 Internal Traceability Chain & Code Impact</h2>
    <div style="margin-bottom: 12px; display: flex; gap: 8px;">
      <span class="node-box observed-node">● Runtime Observed</span>
      <span class="node-box verified-node">● Verified Business Effect</span>
      <span class="node-box static-node">● Static Extracted (GitNexus/Graphify)</span>
    </div>
    {edges_html}
  </div>
</div>
</body>
</html>
"""
        return html
