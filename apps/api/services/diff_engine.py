"""
TracePlay Data-Diff Engine.
Compares before/after observations, evaluates field-level mutations against
expected and forbidden change contracts, and assigns causality status.
"""
import json
from typing import Any, Dict, List, Optional
from apps.api.services.redaction import default_redactor


class DiffEngine:
    @staticmethod
    def compare_snapshots(
        before: Optional[Dict[str, Any]],
        after: Optional[Dict[str, Any]],
        entity_type: str,
        entity_key: str,
        expected_changes: Optional[Dict[str, Any]] = None,
        forbidden_fields: Optional[List[str]] = None,
        expected_unchanged: Optional[List[str]] = None,
        interaction_id: Optional[str] = None,
        has_trace_correlation: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Produce structured field diffs and classify expectation & causality status.
        """
        diffs = []
        expected_changes = expected_changes or {}
        forbidden_fields = forbidden_fields or []
        expected_unchanged = expected_unchanged or []

        all_keys = set((before or {}).keys()) | set((after or {}).keys())

        for key in sorted(all_keys):
            val_before = (before or {}).get(key)
            val_after = (after or {}).get(key)

            # Redact values for safe diff representation
            redacted_before = default_redactor.sanitize_payload(val_before)
            redacted_after = default_redactor.sanitize_payload(val_after)

            if key not in (before or {}):
                change_type = "ADDED"
            elif key not in (after or {}):
                change_type = "REMOVED"
            elif val_before != val_after:
                change_type = "CHANGED"
            else:
                change_type = "UNCHANGED"

            # Determine expectation status
            if change_type == "UNCHANGED":
                if key in expected_unchanged:
                    expectation_status = "UNCHANGED_AS_EXPECTED"
                elif key in expected_changes:
                    expectation_status = "EXPECTED_CHANGE_MISSING"  # expected to change but didn't!
                else:
                    expectation_status = "UNCHANGED"
            else:
                # Value changed, added, or removed
                if key in forbidden_fields or key in expected_unchanged:
                    expectation_status = "FORBIDDEN_CHANGE_DETECTED"
                elif key in expected_changes:
                    expected_target = expected_changes[key]
                    if expected_target is None or val_after == expected_target:
                        expectation_status = "EXPECTED_CHANGE"
                    else:
                        expectation_status = "UNEXPECTED_VALUE"
                else:
                    expectation_status = "UNEXPECTED_CHANGE"

            # Causality classification rule:
            # Mark confirmed only when strong linking evidence exists (trace context, interaction correlation).
            # Otherwise label temporally_correlated or causality_unconfirmed.
            if has_trace_correlation and interaction_id:
                causality = "confirmed"
            elif interaction_id:
                causality = "temporally_correlated"
            else:
                causality = "causality_unconfirmed"

            diffs.append({
                "entity_type": entity_type,
                "entity_key_hash": str(entity_key),
                "field_name": key,
                "change_type": change_type,
                "before_value_redacted": json.dumps(redacted_before) if redacted_before is not None else None,
                "after_value_redacted": json.dumps(redacted_after) if redacted_after is not None else None,
                "expectation_status": expectation_status,
                "causality_status": causality,
                "evidence_json": json.dumps({
                    "has_trace_correlation": has_trace_correlation,
                    "interaction_id": interaction_id,
                }),
            })

        return diffs
