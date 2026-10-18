"""
Unit tests for TracePlay Redaction & Sanitization.
"""
from apps.api.services.redaction import default_redactor, REDACTED_PLACEHOLDER


def test_sanitize_headers():
    headers = {
        "Authorization": "Bearer secret_jwt_token_12345",
        "Cookie": "session_id=abcdef98765",
        "X-Api-Key": "my_top_secret_api_key",
        "Content-Type": "application/json",
        "Accept": "*/*",
    }
    sanitized = default_redactor.sanitize_headers(headers)

    assert sanitized["Authorization"] == REDACTED_PLACEHOLDER
    assert sanitized["Cookie"] == REDACTED_PLACEHOLDER
    assert sanitized["X-Api-Key"] == REDACTED_PLACEHOLDER
    assert sanitized["Content-Type"] == "application/json"
    assert sanitized["Accept"] == "*/*"


def test_sanitize_payload_nested():
    payload = {
        "user": {
            "name": "Alex",
            "password_hash": "$2b$12$e80yq9g",
            "credit_card": "4111-2222-3333-4444",
        },
        "role": "tester",
    }
    sanitized = default_redactor.sanitize_payload(payload)

    assert sanitized["user"]["name"] == "Alex"
    assert sanitized["user"]["password_hash"] == REDACTED_PLACEHOLDER
    assert sanitized["user"]["credit_card"] == REDACTED_PLACEHOLDER
    assert sanitized["role"] == "tester"
