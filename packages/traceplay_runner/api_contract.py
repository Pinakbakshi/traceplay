"""TracePlay API-contract probe for authenticated JSON/REST endpoints.

Secrets are supplied via environment variables (CLI header values may use @ENV_NAME)
and are never copied into the report. This module does not claim business correctness;
it verifies an HTTP contract and caller-selected response invariants.
"""
from __future__ import annotations

import time
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx


def json_path_value(payload: Any, path: str) -> Any:
    """Read a dot-separated JSON path, supporting numeric list indices."""
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(f"JSON path not found: {path}")
    return current


def evaluate_api_response(
    status_code: int,
    payload: Any,
    expected_status: int = 200,
    required_json_paths: Iterable[str] = (),
) -> dict[str, Any]:
    """Evaluate status and required JSON paths without exposing request headers."""
    checks: list[dict[str, Any]] = [
        {
            "name": "http_status",
            "passed": status_code == expected_status,
            "expected": expected_status,
            "actual": status_code,
        }
    ]
    for path in required_json_paths:
        try:
            value = json_path_value(payload, path)
            checks.append({"name": f"json_path:{path}", "passed": value is not None, "present": True})
        except KeyError:
            checks.append({"name": f"json_path:{path}", "passed": False, "present": False})
    return {
        "ok": all(item["passed"] for item in checks),
        "status_code": status_code,
        "checks": checks,
    }


def _redact_url(url: str) -> str:
    """Mask sensitive query parameter values before placing URLs in reports."""
    parts = urlsplit(url)
    safe_query = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if any(marker in key.lower() for marker in ("key", "token", "auth", "secret", "password", "signature")):
            value = "[REDACTED]"
        safe_query.append((key, value))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(safe_query), ""))


def probe_api_endpoint(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    json_body: Any = None,
    expected_status: int = 200,
    required_json_paths: Iterable[str] = (),
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Send one bounded HTTP request and return a credential-free contract report."""
    if not url.startswith(("http://", "https://")):
        raise ValueError("URL must use http:// or https://")
    started = time.perf_counter()
    with httpx.Client(timeout=timeout_seconds, follow_redirects=False) as client:
        response = client.request(
            method.upper(),
            url,
            headers=headers or {},
            params=params,
            json=json_body,
        )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    try:
        payload: Any = response.json()
        is_json = True
    except ValueError:
        payload = None
        is_json = False
    report = evaluate_api_response(
        response.status_code,
        payload,
        expected_status=expected_status,
        required_json_paths=required_json_paths,
    )
    report.update({
        "url": _redact_url(str(response.request.url)),
        "method": method.upper(),
        "elapsed_ms": elapsed_ms,
        "content_type": response.headers.get("content-type", ""),
        "json_response": is_json,
    })
    return report
