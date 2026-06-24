"""SMS provider unit tests."""
from __future__ import annotations

import pytest
from core.base_sms import (
    FIVESIM_SERVICES,
    FiveSimProvider,
    HeroSmsProvider,
    SmsActivation,
    SmsActivateProvider,
    create_sms_provider,
    create_phone_callbacks,
    SMS_ACTIVATE_SERVICES,
    SMS_ACTIVATE_COUNTRIES,
    _resolve_fivesim_country,
    _resolve_fivesim_product,
)
import core.base_sms as sms_module


class TestSmsActivateServiceMapping:
    def test_cursor_maps_to_ot(self):
        assert SMS_ACTIVATE_SERVICES["cursor"] == "ot"

    def test_chatgpt_maps_to_dr(self):
        assert SMS_ACTIVATE_SERVICES["chatgpt"] == "dr"

    def test_default_exists(self):
        assert "default" in SMS_ACTIVATE_SERVICES


class TestSmsActivateCountryMapping:
    def test_us_maps_to_187(self):
        assert SMS_ACTIVATE_COUNTRIES["us"] == "187"

    def test_ru_maps_to_0(self):
        assert SMS_ACTIVATE_COUNTRIES["ru"] == "0"

    def test_th_maps_to_52(self):
        assert SMS_ACTIVATE_COUNTRIES["th"] == "52"

    def test_default_exists(self):
        assert "default" in SMS_ACTIVATE_COUNTRIES


class TestCreateSmsProvider:
    def test_sms_activate(self):
        provider = create_sms_provider("sms_activate", {"sms_activate_api_key": "test123"})
        assert isinstance(provider, SmsActivateProvider)
        assert provider.api_key == "test123"

    def test_sms_activate_missing_key(self):
        with pytest.raises(RuntimeError, match="未配置"):
            create_sms_provider("sms_activate", {})

    def test_herosms(self):
        provider = create_sms_provider("herosms", {"herosms_api_key": "hero123"})
        assert isinstance(provider, HeroSmsProvider)
        assert provider.api_key == "hero123"
        assert provider.default_service == "dr"
        assert provider.default_country == "187"

    def test_herosms_reuse_flag_parses_string_false(self):
        provider = create_sms_provider(
            "herosms",
            {
                "herosms_api_key": "hero123",
                "register_reuse_phone_to_max": "false",
            },
        )
        assert isinstance(provider, HeroSmsProvider)
        assert provider.reuse_phone_to_max is False

    def test_herosms_missing_key(self):
        with pytest.raises(RuntimeError, match="HeroSMS 未配置"):
            create_sms_provider("herosms", {})

    def test_fivesim(self):
        provider = create_sms_provider(
            "fivesim_api",
            {
                "fivesim_api_key": "token123",
                "fivesim_default_product": "openai",
                "fivesim_default_country": "england",
                "fivesim_default_operator": "any",
            },
        )
        assert isinstance(provider, FiveSimProvider)
        assert provider.api_key == "token123"
        assert provider.default_product == "openai"
        assert provider.default_country == "england"

    def test_fivesim_missing_key(self):
        with pytest.raises(RuntimeError, match="5sim 未配置"):
            create_sms_provider("fivesim_api", {})

    def test_unknown_provider(self):
        with pytest.raises(RuntimeError, match="未知"):
            create_sms_provider("unknown", {})


class TestCreatePhoneCallbacks:
    def test_returns_tuple(self):
        # This will fail on actual API call, but we can test the structure
        callback, cleanup = create_phone_callbacks(
            "sms_activate",
            {"sms_activate_api_key": "test"},
            service="cursor",
        )
        assert callable(callback)
        assert callable(cleanup)

    def test_provider_is_created_lazily_and_cleanup_cancels_pending_activation(self, monkeypatch):
        events = []
        logs = []

        class FakeProvider:
            def get_number(self, *, service: str, country: str = ""):
                events.append(("get_number", service, country))
                return SmsActivation(activation_id="act_1", phone_number="+15551234567")

            def get_code(self, activation_id: str, *, timeout: int = 120) -> str:
                events.append(("get_code", activation_id, timeout))
                return ""

            def cancel(self, activation_id: str) -> bool:
                events.append(("cancel", activation_id))
                return True

            def report_success(self, activation_id: str) -> bool:
                events.append(("report_success", activation_id))
                return True

        monkeypatch.setattr("core.base_sms.create_sms_provider", lambda provider_key, config: FakeProvider())

        callback, cleanup = create_phone_callbacks(
            "sms_activate",
            {"sms_activate_api_key": "test"},
            service="chatgpt",
            country="us",
            log_fn=logs.append,
        )

        assert events == []
        assert callback() == "+15551234567"
        cleanup()
        assert ("get_number", "chatgpt", "us") in events
        assert ("cancel", "act_1") in events
        assert any("准备租用手机号" in item for item in logs)
        assert any("已成功租到号码" in item for item in logs)
        assert any("已释放未使用号码" in item for item in logs)

    def test_cleanup_does_not_cancel_after_success(self, monkeypatch):
        events = []
        logs = []

        class FakeProvider:
            def get_number(self, *, service: str, country: str = ""):
                events.append(("get_number", service, country))
                return SmsActivation(activation_id="act_2", phone_number="+15557654321")

            def get_code(self, activation_id: str, *, timeout: int = 120) -> str:
                events.append(("get_code", activation_id, timeout))
                return "123456"

            def cancel(self, activation_id: str) -> bool:
                events.append(("cancel", activation_id))
                return True

            def report_success(self, activation_id: str) -> bool:
                events.append(("report_success", activation_id))
                return True

        monkeypatch.setattr("core.base_sms.create_sms_provider", lambda provider_key, config: FakeProvider())

        callback, cleanup = create_phone_callbacks(
            "sms_activate",
            {"sms_activate_api_key": "test"},
            service="chatgpt",
            log_fn=logs.append,
        )

        assert callback() == "+15557654321"
        assert callback() == "123456"
        cleanup()
        assert ("report_success", "act_2") in events
        assert ("cancel", "act_2") not in events
        assert any("等待短信验证码" in item for item in logs)
        assert any("短信验证成功" in item for item in logs)

    def test_deferred_success_provider_reports_on_cleanup_for_legacy_callers(self, monkeypatch):
        events = []

        class FakeProvider:
            auto_report_success_on_code = False

            def get_number(self, *, service: str, country: str = ""):
                events.append(("get_number", service, country))
                return SmsActivation(activation_id="act_deferred", phone_number="+15550001111")

            def get_code(self, activation_id: str, *, timeout: int = 120) -> str:
                events.append(("get_code", activation_id, timeout))
                return "111222"

            def cancel(self, activation_id: str) -> bool:
                events.append(("cancel", activation_id))
                return True

            def report_success(self, activation_id: str) -> bool:
                events.append(("report_success", activation_id))
                return True

        monkeypatch.setattr("core.base_sms.create_sms_provider", lambda provider_key, config: FakeProvider())

        callback, cleanup = create_phone_callbacks(
            "herosms",
            {"herosms_api_key": "test"},
            service="cursor",
        )

        assert callback() == "+15550001111"
        assert callback() == "111222"
        cleanup()
        assert ("report_success", "act_deferred") in events
        assert ("cancel", "act_deferred") not in events

    def test_first_number_fetch_failure_does_not_poison_future_retries(self, monkeypatch):
        events = []

        class FakeProvider:
            def __init__(self):
                self.calls = 0

            def get_number(self, *, service: str, country: str = ""):
                self.calls += 1
                events.append(("get_number", self.calls, service, country))
                if self.calls == 1:
                    raise RuntimeError("temporary failure")
                return SmsActivation(activation_id="act_retry", phone_number="+66123456789")

            def get_code(self, activation_id: str, *, timeout: int = 120) -> str:
                events.append(("get_code", activation_id, timeout))
                return "654321"

            def cancel(self, activation_id: str) -> bool:
                events.append(("cancel", activation_id))
                return True

            def report_success(self, activation_id: str) -> bool:
                events.append(("report_success", activation_id))
                return True

        provider = FakeProvider()
        monkeypatch.setattr("core.base_sms.create_sms_provider", lambda provider_key, config: provider)

        callback, cleanup = create_phone_callbacks(
            "sms_activate",
            {"sms_activate_api_key": "test"},
            service="chatgpt",
            country="th",
        )

        with pytest.raises(RuntimeError, match="temporary failure"):
            callback()

        assert callback() == "+66123456789"
        assert callback() == "654321"
        cleanup()
        assert ("report_success", "act_retry") in events

    def test_herosms_number_fetch_failure_releases_verify_lock(self, monkeypatch):
        class FakeProvider:
            def get_number(self, *, service: str, country: str = ""):
                raise RuntimeError("temporary failure")

        monkeypatch.setattr("core.base_sms.create_sms_provider", lambda provider_key, config: FakeProvider())

        callback, cleanup = create_phone_callbacks(
            "herosms",
            {"herosms_api_key": "test"},
            service="chatgpt",
        )

        with pytest.raises(RuntimeError, match="temporary failure"):
            callback()

        assert callback._verify_lock_acquired is False
        cleanup()

    def test_mark_send_succeeded_delegates_to_provider(self, monkeypatch):
        events = []

        class FakeProvider:
            def get_number(self, *, service: str, country: str = ""):
                return SmsActivation(activation_id="act_sent", phone_number="+15551234567")

            def mark_send_succeeded(self, activation_id: str) -> None:
                events.append(("mark_send_succeeded", activation_id))

            def cancel(self, activation_id: str) -> bool:
                events.append(("cancel", activation_id))
                return True

        monkeypatch.setattr("core.base_sms.create_sms_provider", lambda provider_key, config: FakeProvider())

        callback, cleanup = create_phone_callbacks(
            "herosms",
            {"herosms_api_key": "test"},
            service="chatgpt",
        )

        assert callback() == "+15551234567"
        callback.mark_send_succeeded()
        cleanup()
        assert ("mark_send_succeeded", "act_sent") in events


class TestSmsActivateProviderCountryResolution:
    def test_get_number_accepts_numeric_country_id(self, monkeypatch):
        captured = {}

        def fake_request(self, action: str, **params):
            captured["action"] = action
            captured["params"] = params
            return "NO_NUMBERS"

        monkeypatch.setattr(SmsActivateProvider, "_request", fake_request)
        provider = SmsActivateProvider("test123", default_country="ru")

        with pytest.raises(RuntimeError, match="NO_NUMBERS|无可用号码"):
            provider.get_number(service="chatgpt", country="52")

        assert captured["action"] == "getNumber"
        assert captured["params"]["country"] == "52"


class TestHeroSmsProvider:
    def test_get_number_uses_v2_json(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sms_module, "hero_sms_cache_file", lambda: tmp_path / ".herosms_phone_cache.json")
        monkeypatch.setattr(sms_module, "_HERO_SMS_CACHE", None)
        calls = []

        class FakeResp:
            text = '{"activationId":"act_1","phoneNumber":"5551234","countryPhoneCode":"1","activationCost":"0.6"}'

            def raise_for_status(self):
                return None

            def json(self):
                return {"activationId": "act_1", "phoneNumber": "5551234", "countryPhoneCode": "1", "activationCost": "0.6"}

        def fake_get(url, params, timeout=30, proxies=None):
            calls.append(params)
            return FakeResp()

        monkeypatch.setattr("core.base_sms.requests.get", fake_get)
        provider = HeroSmsProvider("hero123")
        activation = provider.get_number(service="chatgpt", country="187")

        assert activation.activation_id == "act_1"
        assert activation.phone_number == "+15551234"
        assert calls[0]["action"] == "getNumberV2"

    def test_get_number_falls_back_to_v1_text(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sms_module, "hero_sms_cache_file", lambda: tmp_path / ".herosms_phone_cache.json")
        monkeypatch.setattr(sms_module, "_HERO_SMS_CACHE", None)
        calls = []

        class FakeResp:
            def __init__(self, text):
                self.text = text

            def raise_for_status(self):
                return None

            def json(self):
                raise ValueError("not json")

        def fake_get(url, params, timeout=30, proxies=None):
            calls.append(params["action"])
            if params["action"] == "getNumberV2":
                return FakeResp("BAD")
            return FakeResp("ACCESS_NUMBER:act_2:15557654321")

        monkeypatch.setattr("core.base_sms.requests.get", fake_get)
        provider = HeroSmsProvider("hero123")
        activation = provider.get_number(service="chatgpt", country="187")

        assert activation.activation_id == "act_2"
        assert activation.phone_number == "+15557654321"
        assert calls == ["getNumberV2", "getNumber"]

    def test_get_code_skips_attempted_sms_event(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sms_module, "hero_sms_cache_file", lambda: tmp_path / ".herosms_phone_cache.json")
        monkeypatch.setattr(sms_module, "_HERO_SMS_CACHE", {
            "api_key_hash": sms_module._hash_secret("hero123"),
            "service": "dr",
            "country": "187",
            "activation_id": "act_3",
            "phone_number": "+15550000000",
            "acquired_at": sms_module.time.time(),
            "use_count": 0,
            "used_codes": set(),
            "attempted_sms_keys": set(),
            "reuse_stopped": False,
        })
        provider = HeroSmsProvider("hero123")
        first = {"status": "ok", "code": "111111", "sms_key": "sms_1", "allow_same_code": True}
        second = {"status": "ok", "code": "222222", "sms_key": "sms_2", "allow_same_code": True}
        results = [first, second]

        monkeypatch.setattr(provider, "get_status_v2", lambda activation_id: results.pop(0))
        monkeypatch.setattr(provider, "get_status", lambda activation_id: {"status": "wait_code"})
        monkeypatch.setattr(provider, "get_active_activations", lambda: [])
        monkeypatch.setattr(provider, "request_resend_sms", lambda activation_id: True)

        assert provider.get_code("act_3", timeout=1) == "111111"
        provider.mark_code_failed("act_3", "invalid otp")
        assert provider.get_code("act_3", timeout=1) == "222222"

    def test_mark_send_succeeded_sets_sms_sent_status(self, monkeypatch):
        calls = []
        provider = HeroSmsProvider("hero123")
        monkeypatch.setattr(provider, "set_status", lambda activation_id, status: calls.append((activation_id, status)) or "ACCESS_READY")

        provider.mark_send_succeeded("act_4")

        assert calls == [("act_4", 1)]

    def test_mark_code_failed_triggers_openai_and_herosms_resend(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sms_module, "hero_sms_cache_file", lambda: tmp_path / ".herosms_phone_cache.json")
        monkeypatch.setattr(sms_module, "_HERO_SMS_CACHE", {
            "api_key_hash": sms_module._hash_secret("hero123"),
            "service": "dr",
            "country": "187",
            "activation_id": "act_5",
            "phone_number": "+15550000000",
            "acquired_at": sms_module.time.time(),
            "use_count": 0,
            "used_codes": set(),
            "attempted_sms_keys": set(),
            "reuse_stopped": False,
        })
        events = []
        provider = HeroSmsProvider("hero123")
        provider.last_code_result = {"code": "333333", "sms_key": "sms_3"}
        provider.set_resend_callback(lambda: events.append(("openai_resend",)))
        monkeypatch.setattr(provider, "request_resend_sms", lambda activation_id: events.append(("hero_resend", activation_id)) or True)

        provider.mark_code_failed("act_5", "invalid otp")

        assert ("openai_resend",) in events
        assert ("hero_resend", "act_5") in events
        assert "333333" in sms_module._HERO_SMS_CACHE["used_codes"]
        assert "sms_3" in sms_module._HERO_SMS_CACHE["attempted_sms_keys"]

    def test_report_success_finishes_activation_when_reuse_disabled(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sms_module, "hero_sms_cache_file", lambda: tmp_path / ".herosms_phone_cache.json")
        monkeypatch.setattr(sms_module, "_HERO_SMS_CACHE", {
            "api_key_hash": sms_module._hash_secret("hero123"),
            "service": "dr",
            "country": "187",
            "activation_id": "act_6",
            "phone_number": "+15550000000",
            "acquired_at": sms_module.time.time(),
            "use_count": 0,
            "used_codes": set(),
            "attempted_sms_keys": set(),
            "reuse_stopped": False,
        })
        events = []
        provider = HeroSmsProvider("hero123", reuse_phone_to_max=False)
        provider.last_code_result = {"code": "444444", "sms_key": "sms_4"}
        monkeypatch.setattr(provider, "finish_activation", lambda activation_id: events.append(("finish", activation_id)) or True)

        assert provider.report_success("act_6") is True

        assert events == [("finish", "act_6")]
        assert sms_module._HERO_SMS_CACHE is None


class TestSmsActivation:
    def test_dataclass(self):
        a = SmsActivation(activation_id="123", phone_number="+79001234567")
        assert a.activation_id == "123"
        assert a.phone_number == "+79001234567"
        assert a.country == ""

    def test_with_country(self):
        a = SmsActivation(activation_id="1", phone_number="+1555", country="us")
        assert a.country == "us"


class TestHeroSmsWaitForCode:
    def test_get_code_does_not_extend_timeout_with_phone_cache(self, monkeypatch, tmp_path):
        monkeypatch.setattr(sms_module, "hero_sms_cache_file", lambda: tmp_path / ".herosms_phone_cache.json")
        monkeypatch.setattr(sms_module, "_HERO_SMS_CACHE", {
            "api_key_hash": sms_module._hash_secret("hero123"),
            "service": "dr",
            "country": "187",
            "activation_id": "act_cache",
            "phone_number": "+15550000000",
            "acquired_at": sms_module.time.time(),
            "use_count": 0,
            "used_codes": set(),
            "attempted_sms_keys": set(),
            "reuse_stopped": False,
        })
        provider = HeroSmsProvider("hero123")
        captured = []

        def fake_wait_for_code(activation_id, *, timeout, poll_interval=3, log_fn=None):
            captured.append(timeout)
            return None

        monkeypatch.setattr(provider, "wait_for_code", fake_wait_for_code)
        provider.get_code("act_cache", timeout=180)
        assert captured == [180]

    def test_wait_for_code_exits_after_post_resend_window(self, monkeypatch):
        monkeypatch.setattr(sms_module, "HERO_SMS_OPENAI_RESEND_AFTER", 1)
        monkeypatch.setattr(sms_module, "HERO_SMS_POST_RESEND_WAIT", 2)
        monkeypatch.setattr(sms_module, "HERO_SMS_POLL_LOG_INTERVAL", 1)
        monkeypatch.setattr(sms_module, "HERO_SMS_RESEND_CALLBACK_TIMEOUT", 1)

        provider = HeroSmsProvider("hero123")
        events = []
        provider.set_resend_callback(lambda: events.append("openai"))
        monkeypatch.setattr(provider, "get_status_v2", lambda activation_id: {"status": "wait_code"})
        monkeypatch.setattr(provider, "get_status", lambda activation_id: {"status": "wait_code"})
        monkeypatch.setattr(provider, "get_active_activations", lambda: [])
        monkeypatch.setattr(provider, "request_resend_sms", lambda activation_id: events.append("hero") or True)

        start = sms_module.time.time()
        result = provider.wait_for_code(
            "act_post_resend",
            timeout=30,
            poll_interval=0.2,
            log_fn=events.append,
        )
        elapsed = sms_module.time.time() - start

        assert result is None
        assert "openai" in events
        assert elapsed < 8

    def test_invoke_resend_callback_safe_times_out(self, monkeypatch):
        monkeypatch.setattr(sms_module, "HERO_SMS_RESEND_CALLBACK_TIMEOUT", 0.1)

        def slow_callback():
            sms_module.time.sleep(1)

        assert sms_module._invoke_resend_callback_safe(slow_callback, timeout=0.1) is False


class TestFiveSimMapping:
    def test_chatgpt_maps_to_openai(self):
        assert FIVESIM_SERVICES["chatgpt"] == "openai"
        assert _resolve_fivesim_product("chatgpt", "") == "openai"

    def test_country_alias_usa(self):
        assert _resolve_fivesim_country("us", "") == "usa"
        assert _resolve_fivesim_country("uk", "") == "england"


class TestFiveSimProvider:
    def test_get_balance(self, monkeypatch):
        provider = FiveSimProvider("token123")

        class FakeResp:
            status_code = 200
            text = '{"balance": 12.5, "rating": 96, "email": "a@b.com", "frozen_balance": 0}'

            def json(self):
                return {"balance": 12.5, "rating": 96, "email": "a@b.com", "frozen_balance": 0}

        monkeypatch.setattr(provider, "_request", lambda path, **kwargs: FakeResp())
        profile = provider.get_profile()
        assert profile["balance"] == 12.5
        assert profile["rating"] == 96
        assert provider.get_balance() == 12.5

    def test_no_free_phones_plain_text(self, monkeypatch):
        provider = FiveSimProvider("token123")

        class FakeResp:
            status_code = 200
            text = "no free phones"

            def json(self):
                raise ValueError("not json")

        monkeypatch.setattr(provider, "_request", lambda path, **kwargs: FakeResp())
        with pytest.raises(RuntimeError, match="无可用号码"):
            provider.get_number(service="openai", country="england")

    def test_get_code_finishes_on_finished_status(self, monkeypatch):
        provider = FiveSimProvider("token123")
        monkeypatch.setattr(
            provider,
            "_check_order",
            lambda activation_id: {"status": "FINISHED", "sms": []},
        )
        monkeypatch.setattr(sms_module.time, "sleep", lambda _s: None)
        assert provider.get_code("99", timeout=60) == ""

    def test_get_products_fallback_to_prices(self, monkeypatch):
        provider = FiveSimProvider("token123", default_country="usa")

        class EmptyResp:
            status_code = 200
            text = "{}"

            def json(self):
                return {}

        monkeypatch.setattr(provider, "_request", lambda path, **kwargs: EmptyResp())
        monkeypatch.setattr(
            provider,
            "get_prices",
            lambda **kwargs: {
                "usa": {
                    "openai": {"virtual60": {"cost": 4, "count": 10}},
                },
            },
        )
        rows, meta = provider.get_products(country="usa", with_meta=True)
        assert meta["source"] == "guest_prices_fallback"
        assert any(row["code"] == "openai" for row in rows)

    def test_get_number(self, monkeypatch):
        provider = FiveSimProvider("token123", default_product="openai", default_country="england")

        class FakeResp:
            status_code = 200
            text = '{"id": 99, "phone": "447700900123", "status": "PENDING"}'

            def json(self):
                return {"id": 99, "phone": "447700900123", "status": "PENDING"}

        monkeypatch.setattr(provider, "_request", lambda path, **kwargs: FakeResp())
        activation = provider.get_number(service="chatgpt", country="uk")
        assert activation.activation_id == "99"
        assert activation.phone_number == "+447700900123"
        assert activation.country == "england"

    def test_get_code_returns_sms_code(self, monkeypatch):
        provider = FiveSimProvider("token123")
        calls = {"n": 0}

        def fake_check(activation_id):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"status": "RECEIVED", "sms": []}
            return {"status": "RECEIVED", "sms": [{"code": "123456"}]}

        monkeypatch.setattr(provider, "_check_order", fake_check)
        monkeypatch.setattr(sms_module.time, "sleep", lambda _s: None)
        assert provider.get_code("99", timeout=60) == "123456"

    def test_get_code_cancels_on_timeout(self, monkeypatch):
        provider = FiveSimProvider("token123")
        cancelled = []

        monkeypatch.setattr(provider, "_check_order", lambda activation_id: {"status": "PENDING", "sms": []})
        monkeypatch.setattr(provider, "cancel", lambda activation_id: cancelled.append(activation_id) or True)
        monkeypatch.setattr(sms_module.time, "sleep", lambda _s: None)

        start = sms_module.time.time()

        def fake_time():
            fake_time.counter += 1
            return start + fake_time.counter * 100

        fake_time.counter = 0
        monkeypatch.setattr(sms_module.time, "time", fake_time)
        assert provider.get_code("99", timeout=60) == ""
        assert cancelled == ["99"]
