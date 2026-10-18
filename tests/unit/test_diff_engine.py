"""
Unit tests for TracePlay Data-Diff Engine.
"""
import pytest
from apps.api.services.diff_engine import DiffEngine


def test_expected_change_detected():
    before = {"display_name": "Old Name", "role": "user"}
    after = {"display_name": "New Name", "role": "user"}

    diffs = DiffEngine.compare_snapshots(
        before=before,
        after=after,
        entity_type="users",
        entity_key="user-1",
        expected_changes={"display_name": "New Name"},
        expected_unchanged=["role"],
        interaction_id="inter-1",
    )

    diff_map = {d["field_name"]: d for d in diffs}

    assert diff_map["display_name"]["change_type"] == "CHANGED"
    assert diff_map["display_name"]["expectation_status"] == "EXPECTED_CHANGE"
    assert diff_map["display_name"]["causality_status"] == "confirmed"

    assert diff_map["role"]["change_type"] == "UNCHANGED"
    assert diff_map["role"]["expectation_status"] == "UNCHANGED_AS_EXPECTED"


def test_forbidden_change_detected():
    before = {"display_name": "Old Name", "is_admin": 0}
    after = {"display_name": "New Name", "is_admin": 1}

    diffs = DiffEngine.compare_snapshots(
        before=before,
        after=after,
        entity_type="users",
        entity_key="user-1",
        expected_changes={"display_name": "New Name"},
        forbidden_fields=["is_admin"],
        interaction_id="inter-2",
    )

    diff_map = {d["field_name"]: d for d in diffs}
    assert diff_map["is_admin"]["change_type"] == "CHANGED"
    assert diff_map["is_admin"]["expectation_status"] == "FORBIDDEN_CHANGE_DETECTED"


def test_unexpected_mutation_detected():
    before = {"display_name": "Old Name", "email": "old@example.com"}
    after = {"display_name": "New Name", "email": "new@example.com"}

    diffs = DiffEngine.compare_snapshots(
        before=before,
        after=after,
        entity_type="users",
        entity_key="user-1",
        expected_changes={"display_name": "New Name"},  # email is neither expected nor forbidden!
        interaction_id="inter-3",
    )

    diff_map = {d["field_name"]: d for d in diffs}
    assert diff_map["email"]["expectation_status"] == "UNEXPECTED_CHANGE"
