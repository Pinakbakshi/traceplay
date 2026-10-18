"""
TracePlay Internal Traceability Graph Builder.
Constructs a unified, navigable evidence graph connecting UI actions to
requests, backend spans, code symbols, database diffs, and static dependencies.
Maintains strict separation between runtime-observed, verified, and static/inferred evidence.
"""
from typing import Any, Dict, List, Optional


class EvidenceClass:
    RUNTIME_OBSERVED = "runtime_observed"
    VERIFIED = "verified"
    STATIC_EXTRACTED = "static_extracted"
    INFERRED = "inferred"
    UNRESOLVED = "unresolved"


class TraceabilityGraphBuilder:
    def __init__(self, run_id: str, commit_sha: str = "head"):
        self.run_id = run_id
        self.commit_sha = commit_sha
        self.nodes: Dict[str, Dict[str, Any]] = {}
        self.edges: List[Dict[str, Any]] = []

    def add_node(self, node_id: str, node_type: str, label: str, metadata: Optional[Dict[str, Any]] = None):
        if node_id not in self.nodes:
            self.nodes[node_id] = {
                "id": node_id,
                "type": node_type,
                "label": label,
                "metadata": metadata or {},
            }

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        evidence_class: str,
        provenance: str = "traceplay_engine",
        confidence: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.edges.append({
            "source": source_id,
            "target": target_id,
            "relationship": relationship,
            "evidence_class": evidence_class,
            "provenance": provenance,
            "confidence": confidence,
            "run_id": self.run_id,
            "commit_sha": self.commit_sha,
            "metadata": metadata or {},
        })

    def build_from_run(
        self,
        interactions: List[Dict[str, Any]],
        network_events: List[Dict[str, Any]],
        backend_spans: List[Dict[str, Any]],
        data_diffs: List[Dict[str, Any]],
        assertions: List[Dict[str, Any]],
        static_graph_paths: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Assemble the complete graph for a run.
        """
        run_node_id = f"run:{self.run_id}"
        self.add_node(run_node_id, "TestRun", f"Run {self.run_id[:8]}", {"commit_sha": self.commit_sha})

        # Add interactions
        for inter in interactions:
            i_id = inter.get("id")
            node_id = f"interaction:{i_id}"
            label = f"Step {inter.get('step_index')}: {inter.get('action_label')}"
            self.add_node(node_id, "UIInteraction", label, inter)
            self.add_edge(run_node_id, node_id, "CONTAINS", EvidenceClass.RUNTIME_OBSERVED)

        # Add network requests
        for net in network_events:
            req_id = net.get("id") or net.get("request_id")
            node_id = f"request:{req_id}"
            label = f"{net.get('method')} {net.get('route_template')} [{net.get('status_code')}]"
            self.add_node(node_id, "NetworkRequest", label, net)

            inter_id = net.get("interaction_id")
            if inter_id:
                self.add_edge(
                    f"interaction:{inter_id}",
                    node_id,
                    "TRIGGERED_REQUEST",
                    EvidenceClass.RUNTIME_OBSERVED,
                    provenance="playwright_network_interception",
                )

            # Endpoint node
            endpoint_id = f"endpoint:{net.get('method')}_{net.get('route_template')}"
            self.add_node(endpoint_id, "Endpoint", f"{net.get('method')} {net.get('route_template')}", {})
            self.add_edge(node_id, endpoint_id, "TARGETS_ENDPOINT", EvidenceClass.RUNTIME_OBSERVED)

        # Add backend spans and trace correlation
        for span in backend_spans:
            s_id = span.get("span_id")
            node_id = f"span:{s_id}"
            label = f"{span.get('service_name')}::{span.get('operation_name')}"
            self.add_node(node_id, "BackendSpan", label, span)

            # Correlate with request via trace_id
            trace_id = span.get("trace_id")
            for net in network_events:
                if net.get("trace_id") == trace_id:
                    self.add_edge(
                        f"request:{net.get('id') or net.get('request_id')}",
                        node_id,
                        "CORRELATED_WITH",
                        EvidenceClass.RUNTIME_OBSERVED,
                        provenance="w3c_traceparent",
                    )
                    break

            # Parent span relationship
            p_id = span.get("parent_span_id")
            if p_id:
                self.add_edge(node_id, f"span:{p_id}", "HAS_PARENT_SPAN", EvidenceClass.RUNTIME_OBSERVED)

            # Code symbol mapped to span operation
            symbol_id = f"symbol:{span.get('service_name')}.{span.get('operation_name')}"
            self.add_node(symbol_id, "CodeSymbol", span.get("operation_name"), {"service": span.get("service_name")})
            self.add_edge(node_id, symbol_id, "EXECUTED_CODE", EvidenceClass.RUNTIME_OBSERVED, provenance="otel_instrumentation")

        # Add data diffs
        for diff in data_diffs:
            d_id = diff.get("id")
            node_id = f"diff:{d_id}"
            label = f"Diff: {diff.get('entity_type')}.{diff.get('field_name')} ({diff.get('change_type')})"
            self.add_node(node_id, "DataDiff", label, diff)

            inter_id = diff.get("interaction_id")
            if inter_id:
                causality = diff.get("causality_status", "confirmed")
                e_class = EvidenceClass.VERIFIED if causality == "confirmed" else EvidenceClass.RUNTIME_OBSERVED
                self.add_edge(
                    f"interaction:{inter_id}",
                    node_id,
                    "OBSERVED_CHANGE",
                    e_class,
                    provenance="db_verification_adapter",
                )

            # Entity node
            entity_id = f"entity:{diff.get('entity_type')}"
            self.add_node(entity_id, "DatabaseEntity", diff.get("entity_type"), {})
            self.add_edge(node_id, entity_id, "MODIFIES_ENTITY", EvidenceClass.RUNTIME_OBSERVED)

        # Add assertions
        for assert_item in assertions:
            a_id = assert_item.get("id")
            node_id = f"assertion:{a_id}"
            label = f"Assertion: {assert_item.get('description')} [{assert_item.get('status')}]"
            self.add_node(node_id, "Assertion", label, assert_item)

            inter_id = assert_item.get("interaction_id")
            if inter_id:
                self.add_edge(
                    f"interaction:{inter_id}",
                    node_id,
                    "ASSERTED_BY",
                    EvidenceClass.VERIFIED,
                    provenance="traceplay_assertion_engine",
                )

        # Add static graph paths (GitNexus / Graphify)
        if static_graph_paths:
            for path in static_graph_paths:
                src_sym = path.get("source_symbol")
                tgt_sym = path.get("target_symbol")
                rel = path.get("relationship", "POTENTIALLY_AFFECTS")
                prov = path.get("provenance", "gitnexus_ast_index")

                src_id = f"symbol:{src_sym}"
                tgt_id = f"symbol:{tgt_sym}"

                self.add_node(src_id, "CodeSymbol", src_sym, {"provenance": prov})
                self.add_node(tgt_id, "CodeSymbol", tgt_sym, {"provenance": prov})

                # Static dependency must NEVER be labeled runtime_observed
                self.add_edge(
                    src_id,
                    tgt_id,
                    rel,
                    EvidenceClass.STATIC_EXTRACTED,
                    provenance=prov,
                    confidence=path.get("confidence", 0.9),
                    metadata={"note": "Static dependency; not observed during runtime execution unless active span exists"},
                )

        return {
            "run_id": self.run_id,
            "commit_sha": self.commit_sha,
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
        }
