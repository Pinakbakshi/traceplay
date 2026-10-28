import unittest

from packages.traceplay_runner.api_contract import _redact_url, evaluate_api_response, json_path_value


class ApiContractProbeTests(unittest.TestCase):
    def test_evaluates_expected_status_and_nested_json_paths(self):
        payload = {
            "analysis": {
                "score": 42,
                "signal": "bullish_bias",
                "components": [{"name": "rsi_momentum"}],
            }
        }
        result = evaluate_api_response(
            200,
            payload,
            expected_status=200,
            required_json_paths=["analysis.score", "analysis.signal", "analysis.components.0.name"],
        )
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["checks"]), 4)

    def test_fails_for_missing_required_path(self):
        result = evaluate_api_response(
            200,
            {"analysis": {"score": 20}},
            required_json_paths=["analysis.signal"],
        )
        self.assertFalse(result["ok"])
        self.assertFalse(result["checks"][1]["passed"])

    def test_fails_for_unexpected_status(self):
        result = evaluate_api_response(401, {"detail": "invalid key"}, expected_status=200)
        self.assertFalse(result["ok"])
        self.assertEqual(result["checks"][0]["actual"], 401)

    def test_redacts_sensitive_query_parameters(self):
        safe_url = _redact_url("https://example.test/check?symbol=BTCUSDT&api_key=secret&token=private")
        self.assertIn("symbol=BTCUSDT", safe_url)
        self.assertNotIn("secret", safe_url)
        self.assertNotIn("private", safe_url)
        self.assertIn("%5BREDACTED%5D", safe_url)

    def test_reads_nested_json_path(self):
        self.assertEqual(json_path_value({"a": [{"b": 7}]}, "a.0.b"), 7)

    def test_rejects_missing_json_path(self):
        with self.assertRaises(KeyError):
            json_path_value({"a": 1}, "a.b")


if __name__ == "__main__":
    unittest.main()
