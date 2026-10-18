"""
TracePlay Data Redaction and Sanitization Engine.
Ensures sensitive tokens, passwords, cookies, and private fields are redacted
both at the customer agent before sending and at ingestion before persistence.
"""
import re
from typing import Any, Dict, List, Set, Union

DEFAULT_SENSITIVE_KEYS: Set[str] = {
    "authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api_key",
    "apikey",
    "token",
    "access_token",
    "refresh_token",
    "password",
    "password_hash",
    "secret",
    "client_secret",
    "ssn",
    "credit_card",
    "cvv",
    "card_number",
    "auth_token",
    "session",
    "session_id",
}

REDACTED_PLACEHOLDER = "[REDACTED]"


class Redactor:
    def __init__(self, sensitive_keys: Set[str] = None):
        self.sensitive_keys = set(k.lower() for k in (sensitive_keys or DEFAULT_SENSITIVE_KEYS))

    def is_sensitive_key(self, key: str) -> bool:
        k = str(key).lower().replace("-", "_")
        if k in self.sensitive_keys:
            return True
        for sens in self.sensitive_keys:
            if sens in k and len(sens) > 3:
                return True
        return False

    def redact_value(self, val: Any) -> Any:
        if val is None:
            return None
        return REDACTED_PLACEHOLDER

    def sanitize_headers(self, headers: Dict[str, Any]) -> Dict[str, Any]:
        if not headers:
            return {}
        sanitized = {}
        for k, v in headers.items():
            if self.is_sensitive_key(k):
                sanitized[k] = REDACTED_PLACEHOLDER
            else:
                sanitized[k] = str(v)
        return sanitized

    def sanitize_payload(self, data: Any) -> Any:
        if isinstance(data, dict):
            clean = {}
            for k, v in data.items():
                if self.is_sensitive_key(k):
                    clean[k] = REDACTED_PLACEHOLDER
                else:
                    clean[k] = self.sanitize_payload(v)
            return clean
        elif isinstance(data, list):
            return [self.sanitize_payload(item) for item in data]
        elif isinstance(data, str):
            # Check for JWT / Bearer patterns in raw strings
            if re.match(r"^Bearer\s+[A-Za-z0-9\-_.]+", data, re.IGNORECASE):
                return "Bearer " + REDACTED_PLACEHOLDER
            return data
        return data

    def sanitize_snapshot(self, snapshot: Dict[str, Any], allowed_fields: List[str] = None) -> Dict[str, Any]:
        """
        Sanitize database field snapshot according to allowed fields and sensitive key suppression.
        """
        if not snapshot:
            return {}
        cleaned = {}
        for k, v in snapshot.items():
            if allowed_fields and k not in allowed_fields:
                continue
            if self.is_sensitive_key(k):
                cleaned[k] = REDACTED_PLACEHOLDER
            else:
                cleaned[k] = v
        return cleaned


default_redactor = Redactor()
