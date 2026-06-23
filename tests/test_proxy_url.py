"""Tests for proxy URL normalization."""
from __future__ import annotations

from core.proxy_url import normalize_proxy_url


class TestNormalizeProxyUrl:
    def test_rapidproxy_host_port_user_pass(self):
        raw = "eu.rapidproxy.io:5001:fixaigo123-residential-UZ-session-82336611-stime-10:a123456O"
        assert normalize_proxy_url(raw) == (
            "http://fixaigo123-residential-UZ-session-82336611-stime-10:a123456O@eu.rapidproxy.io:5001"
        )

    def test_existing_http_url_unchanged(self):
        url = "http://user:pass@1.2.3.4:8080"
        assert normalize_proxy_url(url) == url

    def test_user_pass_at_host_without_scheme(self):
        assert normalize_proxy_url("user:pass@host.example.com:5001") == (
            "http://user:pass@host.example.com:5001"
        )

    def test_host_port_only(self):
        assert normalize_proxy_url("127.0.0.1:7890") == "http://127.0.0.1:7890"

    def test_socks5_url_unchanged(self):
        url = "socks5://user:pass@host:1080"
        assert normalize_proxy_url(url) == url

    def test_empty_input(self):
        assert normalize_proxy_url("") == ""
        assert normalize_proxy_url("   ") == ""
