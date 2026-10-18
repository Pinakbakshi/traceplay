"""
Unit tests for TracePlay Autonomous URL Testing Engine.
"""
import pytest
from apps.api.services.url_tester import UrlTestConfig


def test_url_test_config_domain_extraction():
    cfg1 = UrlTestConfig("https://example.com/login")
    assert cfg1.project_name == "Site: example.com"
    assert cfg1.target_url == "https://example.com/login"

    cfg2 = UrlTestConfig("http://localhost:5001/dashboard?tab=1")
    assert cfg2.project_name == "Site: localhost"

    cfg3 = UrlTestConfig("https://api.staging.myapp.io", project_name="Custom Named Project")
    assert cfg3.project_name == "Custom Named Project"
