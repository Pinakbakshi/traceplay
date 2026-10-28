"""CLI for probing REST API contracts from the TracePlay workspace.

Example:
  python test_api_contract.py \
    --url https://your-api.example/analysis/technical-signal \
    --header 'X-API-Key=@CRYPTO_API_KEY' \
    --param symbol=BTCUSDT --param timeframe=1h \
    --require-json-path analysis.score \
    --require-json-path analysis.signal \
    --require-json-path analysis.components
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from packages.traceplay_runner.api_contract import probe_api_endpoint


def parse_pairs(items: list[str], *, headers: bool = False) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Expected NAME=VALUE, received: {item.split('=', 1)[0]}")
        key, value = item.split("=", 1)
        if headers and value.startswith("@"):
            env_name = value[1:]
            value = os.environ.get(env_name, "")
            if not value:
                raise ValueError(f"Required environment variable is missing: {env_name}")
        result[key] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a TracePlay REST API contract probe.")
    parser.add_argument("--url", required=True, help="Full endpoint URL")
    parser.add_argument("--method", default="GET", help="HTTP method (default: GET)")
    parser.add_argument("--header", action="append", default=[], help="Header NAME=VALUE; use NAME=@ENV_VAR for secrets")
    parser.add_argument("--param", action="append", default=[], help="Query parameter NAME=VALUE")
    parser.add_argument("--json-body", help="Optional JSON request body")
    parser.add_argument("--expect-status", type=int, default=200)
    parser.add_argument("--require-json-path", action="append", default=[], help="Required dot path, e.g. analysis.score")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--report", help="Optional path for JSON report output")
    args = parser.parse_args()

    try:
        body = json.loads(args.json_body) if args.json_body else None
        report = probe_api_endpoint(
            args.url,
            method=args.method,
            headers=parse_pairs(args.header, headers=True),
            params=parse_pairs(args.param),
            json_body=body,
            expected_status=args.expect_status,
            required_json_paths=args.require_json_path,
            timeout_seconds=args.timeout,
        )
    except Exception as exc:
        # Avoid printing request headers or their values, which may contain secrets.
        message = str(exc) if isinstance(exc, ValueError) else "Probe failed; check connectivity and configuration locally (details omitted to avoid leaking credentials)."
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": message}))
        return 2

    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.report:
        output = Path(args.report)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
