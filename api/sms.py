from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.base_sms import (
    FIVESIM_DEFAULT_COUNTRY,
    FIVESIM_DEFAULT_PRODUCT,
    FiveSimProvider,
    HERO_SMS_DEFAULT_COUNTRY,
    HERO_SMS_DEFAULT_SERVICE,
    HeroSmsProvider,
    SmsBowerProvider,
)
from infrastructure.provider_settings_repository import ProviderSettingsRepository

router = APIRouter(prefix="/sms", tags=["sms"])


class HeroSmsQueryRequest(BaseModel):
    api_key: str = ""
    service: str = ""
    country: str = ""
    proxy: str = ""


def _saved_herosms_config() -> dict:
    repo = ProviderSettingsRepository()
    # 兼容旧版 provider_key "herosms" 和新版 "herosms_api"
    config = repo.resolve_runtime_settings("sms", "herosms_api", {})
    if not config.get("herosms_api_key"):
        config = repo.resolve_runtime_settings("sms", "herosms", {})
    return config


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _provider_from_payload(payload: HeroSmsQueryRequest | None = None) -> HeroSmsProvider:
    payload = payload or HeroSmsQueryRequest()
    saved = _saved_herosms_config()
    api_key = str(payload.api_key or saved.get("herosms_api_key") or "").strip()
    return HeroSmsProvider(
        api_key=api_key,
        default_service=str(payload.service or saved.get("sms_service") or HERO_SMS_DEFAULT_SERVICE),
        default_country=str(payload.country or saved.get("sms_country") or HERO_SMS_DEFAULT_COUNTRY),
        max_price=_safe_float(saved.get("herosms_max_price"), -1),
        proxy=str(payload.proxy or saved.get("sms_proxy") or saved.get("proxy") or "") or None,
    )


@router.get("/herosms/countries")
def herosms_countries():
    try:
        return {"countries": _provider_from_payload().get_countries()}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/herosms/services")
def herosms_services(country: str = ""):
    try:
        return {"services": _provider_from_payload(HeroSmsQueryRequest(country=country)).get_services(country=country or None)}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/herosms/balance")
def herosms_balance(body: HeroSmsQueryRequest | None = None):
    body = body or HeroSmsQueryRequest()
    provider = _provider_from_payload(body)
    if not provider.api_key:
        raise HTTPException(400, "HeroSMS API Key 未配置")
    try:
        return {"balance": provider.get_balance()}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/herosms/prices")
def herosms_prices(body: HeroSmsQueryRequest | None = None):
    body = body or HeroSmsQueryRequest()
    provider = _provider_from_payload(body)
    if not provider.api_key:
        raise HTTPException(400, "HeroSMS API Key 未配置")
    try:
        service = str(body.service or provider.default_service or HERO_SMS_DEFAULT_SERVICE)
        country = str(body.country or provider.default_country or HERO_SMS_DEFAULT_COUNTRY)
        return {"prices": provider.get_prices(service=service, country=country)}
    except Exception as exc:
        raise HTTPException(502, str(exc))


class HeroSmsBestCountryRequest(BaseModel):
    api_key: str = ""
    service: str = ""
    proxy: str = ""
    min_stock: int = 20
    max_price: float = 0
    top_n: int = 10


@router.post("/herosms/top-countries")
def herosms_top_countries(body: HeroSmsBestCountryRequest | None = None):
    """获取按价格排序的国家列表（含价格和库存）。"""
    body = body or HeroSmsBestCountryRequest()
    provider = _provider_from_payload(HeroSmsQueryRequest(
        api_key=body.api_key, service=body.service, proxy=body.proxy,
    ))
    if not provider.api_key:
        raise HTTPException(400, "HeroSMS API Key 未配置")
    try:
        service = str(body.service or provider.default_service or HERO_SMS_DEFAULT_SERVICE)
        rows = provider.get_top_countries(service=service)
        # 只返回有库存的
        rows = [r for r in rows if (r.get("count") or 0) > 0]
        if body.top_n > 0:
            rows = rows[:body.top_n]
        return {"countries": rows, "service": service}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/herosms/best-country")
def herosms_best_country(body: HeroSmsBestCountryRequest | None = None):
    """自动选择最优国家（价格最低 + 库存充足）。"""
    body = body or HeroSmsBestCountryRequest()
    provider = _provider_from_payload(HeroSmsQueryRequest(
        api_key=body.api_key, service=body.service, proxy=body.proxy,
    ))
    if not provider.api_key:
        raise HTTPException(400, "HeroSMS API Key 未配置")
    try:
        service = str(body.service or provider.default_service or HERO_SMS_DEFAULT_SERVICE)
        best = provider.get_best_country(
            service=service,
            min_stock=body.min_stock,
            max_price=body.max_price,
        )
        if best:
            # 获取详细信息
            rows = provider.get_top_countries(service=service)
            detail = next((r for r in rows if str(r.get("country")) == str(best)), None)
            return {
                "country": best,
                "detail": detail,
                "service": service,
            }
        return {"country": None, "detail": None, "service": service}
    except Exception as exc:
        raise HTTPException(502, str(exc))


# ── SMSBower endpoints ──────────────────────────────────────────────────────

def _saved_smsbower_config() -> dict:
    return ProviderSettingsRepository().resolve_runtime_settings("sms", "smsbower_api", {})


def _smsbower_from_payload(payload: HeroSmsQueryRequest | None = None) -> SmsBowerProvider:
    payload = payload or HeroSmsQueryRequest()
    saved = _saved_smsbower_config()
    api_key = str(payload.api_key or saved.get("smsbower_api_key") or "").strip()
    return SmsBowerProvider(
        api_key=api_key,
        default_service=str(payload.service or saved.get("sms_service") or saved.get("smsbower_service") or HERO_SMS_DEFAULT_SERVICE),
        default_country=str(payload.country or saved.get("sms_country") or saved.get("smsbower_country") or HERO_SMS_DEFAULT_COUNTRY),
        max_price=_safe_float(saved.get("smsbower_max_price"), -1),
        proxy=str(payload.proxy or saved.get("sms_proxy") or saved.get("proxy") or "") or None,
    )


@router.get("/smsbower/countries")
def smsbower_countries():
    try:
        provider = _smsbower_from_payload()
        if not provider.api_key:
            return {"countries": []}
        return {"countries": provider.get_countries()}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/smsbower/services")
def smsbower_services(country: str = ""):
    try:
        provider = _smsbower_from_payload(HeroSmsQueryRequest(country=country))
        if not provider.api_key:
            return {"services": []}
        return {"services": provider.get_services(country=country or None)}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/smsbower/balance")
def smsbower_balance(body: HeroSmsQueryRequest | None = None):
    body = body or HeroSmsQueryRequest()
    provider = _smsbower_from_payload(body)
    if not provider.api_key:
        raise HTTPException(400, "SMSBower API Key 未配置")
    try:
        return {"balance": provider.get_balance()}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/smsbower/prices")
def smsbower_prices(body: HeroSmsQueryRequest | None = None):
    body = body or HeroSmsQueryRequest()
    provider = _smsbower_from_payload(body)
    if not provider.api_key:
        raise HTTPException(400, "SMSBower API Key 未配置")
    try:
        service = str(body.service or provider.default_service or HERO_SMS_DEFAULT_SERVICE)
        country = str(body.country or provider.default_country or HERO_SMS_DEFAULT_COUNTRY)
        return {"prices": provider.get_prices(service=service, country=country)}
    except Exception as exc:
        raise HTTPException(502, str(exc))


# ── 5sim endpoints ──────────────────────────────────────────────────────────

def _saved_fivesim_config() -> dict:
    return ProviderSettingsRepository().resolve_runtime_settings("sms", "fivesim_api", {})


def _fivesim_from_payload(payload: HeroSmsQueryRequest | None = None) -> FiveSimProvider:
    payload = payload or HeroSmsQueryRequest()
    saved = _saved_fivesim_config()
    api_key = str(payload.api_key or saved.get("fivesim_api_key") or "").strip()
    return FiveSimProvider(
        api_key=api_key,
        default_product=str(
            payload.service
            or saved.get("sms_service")
            or saved.get("fivesim_default_product")
            or FIVESIM_DEFAULT_PRODUCT
        ),
        default_country=str(
            payload.country
            or saved.get("sms_country")
            or saved.get("fivesim_default_country")
            or FIVESIM_DEFAULT_COUNTRY
        ),
        default_operator=str(saved.get("fivesim_default_operator") or "any"),
        max_price=_safe_float(saved.get("fivesim_max_price"), -1),
        proxy=str(payload.proxy or saved.get("sms_proxy") or saved.get("proxy") or "") or None,
    )


@router.get("/fivesim/countries")
def fivesim_countries():
    try:
        provider = _fivesim_from_payload()
        if not provider.api_key:
            return {"countries": []}
        return {"countries": provider.get_countries()}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.get("/fivesim/products")
def fivesim_products(country: str = ""):
    try:
        provider = _fivesim_from_payload(HeroSmsQueryRequest(country=country))
        if not provider.api_key:
            return {"products": []}
        return {"products": provider.get_products(country=country or None)}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/fivesim/balance")
def fivesim_balance(body: HeroSmsQueryRequest | None = None):
    body = body or HeroSmsQueryRequest()
    provider = _fivesim_from_payload(body)
    if not provider.api_key:
        raise HTTPException(400, "5sim API Token 未配置")
    try:
        return {"balance": provider.get_balance()}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/fivesim/prices")
def fivesim_prices(body: HeroSmsQueryRequest | None = None):
    body = body or HeroSmsQueryRequest()
    provider = _fivesim_from_payload(body)
    if not provider.api_key:
        raise HTTPException(400, "5sim API Token 未配置")
    try:
        product = str(body.service or provider.default_product or FIVESIM_DEFAULT_PRODUCT)
        country = str(body.country or provider.default_country or FIVESIM_DEFAULT_COUNTRY)
        return {"prices": provider.get_prices(product=product, country=country)}
    except Exception as exc:
        raise HTTPException(502, str(exc))


@router.post("/fivesim/best-country")
def fivesim_best_country(body: HeroSmsBestCountryRequest | None = None):
    body = body or HeroSmsBestCountryRequest()
    provider = _fivesim_from_payload(HeroSmsQueryRequest(
        api_key=body.api_key, service=body.service, proxy=body.proxy,
    ))
    if not provider.api_key:
        raise HTTPException(400, "5sim API Token 未配置")
    try:
        service = str(body.service or provider.default_product or FIVESIM_DEFAULT_PRODUCT)
        best = provider.get_best_country(
            service=service,
            min_stock=body.min_stock,
            max_price=body.max_price,
        )
        detail = None
        if best:
            detail = next((row for row in provider.get_top_countries(service=service) if str(row.get("country")) == str(best)), None)
        return {"country": best, "detail": detail, "service": service}
    except Exception as exc:
        raise HTTPException(502, str(exc))
