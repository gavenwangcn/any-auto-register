from __future__ import annotations

import time

import pytest

from platforms.chatgpt import browser_register as browser_register_module


class TestBrowserSessionHelpers:
    def test_is_browser_connection_error(self):
        assert browser_register_module._is_browser_connection_error(
            RuntimeError("Page.goto: Connection closed while reading from the driver")
        )
        assert not browser_register_module._is_browser_connection_error(RuntimeError("timeout"))

    def test_close_camoufox_context_swallows_errors(self):
        logs = []

        class BrokenContext:
            def __exit__(self, exc_type, exc, tb):
                raise RuntimeError("already closed")

        browser_register_module._close_camoufox_context(BrokenContext(), logs.append)
        assert any("浏览器关闭异常" in item for item in logs)

    def test_wait_for_page_transition_clicks_passwordless_only_once(self, monkeypatch):
        logs = []
        clicks = {"count": 0}

        class FakePage:
            url = "https://auth.openai.com/log-in"

            def evaluate(self, script):
                return True

        def fake_click(page, log, *, context):
            clicks["count"] += 1
            return True

        monkeypatch.setattr(browser_register_module, "_click_passwordless_login_if_available", fake_click)
        monkeypatch.setattr(browser_register_module, "_extract_auth_error_text", lambda page: "")
        monkeypatch.setattr(
            browser_register_module,
            "_derive_registration_state_from_page",
            lambda page: {"page_type": "email_otp_verification"},
        )
        monkeypatch.setattr(browser_register_module.time, "sleep", lambda seconds: None)

        state = browser_register_module._wait_for_page_transition(
            FakePage(),
            logs.append,
            timeout=5,
            context="测试邮箱页提交",
            get_state=browser_register_module._derive_registration_state_from_page,
            success_page_types={"email_otp_verification"},
        )
        assert state["page_type"] == "email_otp_verification"
        assert clicks["count"] == 1

    def test_browser_authorize_raises_on_dead_driver(self, monkeypatch):
        logs = []

        class DeadPage:
            def evaluate(self, script):
                raise RuntimeError("Connection closed while reading from the driver")

            def goto(self, url, **kwargs):
                raise RuntimeError("Connection closed while reading from the driver")

        with pytest.raises(RuntimeError, match="浏览器驱动已断开"):
            browser_register_module._browser_authorize(
                DeadPage(),
                "https://auth.openai.com/authorize",
                logs.append,
            )
