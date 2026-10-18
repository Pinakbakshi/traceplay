"""
Unit tests for TracePlay Traceability Graph Builder.
Validates strict separation of evidence classes:
runtime_observed, verified, and static_extracted.
"""
from apps.api.services.traceability_graph import TraceabilityGraphBuilder, EvidenceClass


def test_strict_evidence_class_separation():
    builder = TraceabilityGraphBuilder(run_id="run-test-123", commit_sha="commit-abc")

    interactions = [{"id": "i1", "step_index": 1, "action_label": "Click Save", "action_type": "click"}]
    network = [{"id": "n1", "request_id": "r1", "interaction_id": "i1", "method": "PATCH", "route_template": "/api/profile", "status_code": 200}]
    spans = [{"span_id": "s1", "service_name": "ProfileService", "operation_name": "save", "trace_id": "t1"}]
    diffs = [{"id": "d1", "interaction_id": "i1", "entity_type": "users", "field_name": "display_name", "change_type": "CHANGED", "causality_status": "confirmed"}]
    assertions = [{"id": "a1", "interaction_id": "i1", "description": "Profile updated", "status": "passed"}]
    static_paths = [
        {
            "source_symbol": "ProfileService.save",
            "target_symbol": "NotificationService.send_alert",
            "relationship": "POTENTIALLY_AFFECTS",
            "provenance": "gitnexus_ast_index",
        }
    ]

    graph = builder.build_from_run(
        interactions=interactions,
        network_events=network,
        backend_spans=spans,
        data_diffs=diffs,
        assertions=assertions,
        static_graph_paths=static_paths,
    )

    edges = graph["edges"]
    edge_map = {(e["source"], e["target"]): e for e in edges}

    # Verify interaction -> request is runtime_observed
    assert edge_map[("interaction:i1", "request:n1")]["evidence_class"] == EvidenceClass.RUNTIME_OBSERVED

    # Verify interaction -> assertion is verified
    assert edge_map[("interaction:i1", "assertion:a1")]["evidence_class"] == EvidenceClass.VERIFIED

    # Verify static dependency is static_extracted and NEVER runtime_observed
    static_edge = edge_map[("symbol:ProfileService.save", "symbol:NotificationService.send_alert")]
    assert static_edge["evidence_class"] == EvidenceClass.STATIC_EXTRACTED
    assert static_edge["relationship"] == "POTENTIALLY_AFFECTS"
