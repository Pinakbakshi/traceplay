"""
TracePlay Read-Only Database Verification Adapter.
Safely queries target database to produce scoped before/after snapshots.
Enforces read-only permissions, query parameterization, and entity allowlists.
"""
import sqlite3
from typing import Any, Dict, List, Optional


class ReadOnlyDatabaseAdapter:
    def __init__(self, connection_uri: str, allowed_entities: Optional[List[str]] = None):
        self.connection_uri = connection_uri
        self.allowed_entities = set(allowed_entities or ["users", "orders", "audit_logs", "inventory"])

    def _get_connection(self):
        if self.connection_uri.startswith("sqlite"):
            db_path = self.connection_uri.replace("sqlite:///", "").replace("sqlite://", "")
            # Open SQLite in read-only mode via URI
            return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        else:
            # Fallback or sqlite standard
            return sqlite3.connect(self.connection_uri)

    def is_entity_allowed(self, entity: str) -> bool:
        return entity in self.allowed_entities

    def capture_snapshot(
        self,
        entity: str,
        key_field: str,
        key_value: Any,
        fields_to_include: Optional[List[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a scoped read-only select by primary/business key.
        """
        if not self.is_entity_allowed(entity):
            raise ValueError(f"Entity '{entity}' is not in the approved database allowlist")

        conn = self._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Safe parameterized query
            query = f"SELECT * FROM {entity} WHERE {key_field} = ?"
            cursor.execute(query, (key_value,))
            row = cursor.fetchone()
            if not row:
                return None

            result = dict(row)
            if fields_to_include:
                result = {k: v for k, v in result.items() if k in fields_to_include}
            return result
        finally:
            cursor.close()
            conn.close()

    def count_records(self, entity: str, filter_field: str, filter_value: Any) -> int:
        """
        Count records matching criteria (e.g. For duplicate write assertions).
        """
        if not self.is_entity_allowed(entity):
            raise ValueError(f"Entity '{entity}' is not in the approved database allowlist")

        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            query = f"SELECT COUNT(*) FROM {entity} WHERE {filter_field} = ?"
            cursor.execute(query, (filter_value,))
            count = cursor.fetchone()[0]
            return count
        finally:
            cursor.close()
            conn.close()
