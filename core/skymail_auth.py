"""Cloud Mail / SkyMail 公共 API Token 获取与刷新。"""
from __future__ import annotations

from typing import Any, Optional

import requests


class SkyMailAuthError(RuntimeError):
    pass


def _build_proxy(proxy: Optional[str]) -> dict | None:
    if not proxy:
        return None
    return {"http": proxy, "https": proxy}


def normalize_skymail_token(token: str) -> str:
    """去掉 Bearer 前缀与首尾空白。"""
    value = str(token or "").strip()
    if value.lower().startswith("bearer "):
        value = value[7:].strip()
    return value


def fetch_skymail_token(
    api_base: str,
    email: str,
    password: str,
    *,
    proxy: Optional[str] = None,
    timeout: int = 15,
) -> str:
    """POST /api/public/genToken 获取 Authorization Token。"""
    api = (api_base or "").rstrip("/")
    admin_email = (email or "").strip()
    admin_password = password or ""
    if not api:
        raise SkyMailAuthError("SkyMail API Base 未配置")
    if not admin_email or not admin_password:
        raise SkyMailAuthError("SkyMail 管理员邮箱或密码未配置")

    response = requests.post(
        f"{api}/api/public/genToken",
        json={"email": admin_email, "password": admin_password},
        headers={
            "accept": "application/json",
            "content-type": "application/json",
        },
        proxies=_build_proxy(proxy),
        timeout=timeout,
    )
    if response.status_code != 200:
        raise SkyMailAuthError(
            f"genToken 失败: HTTP {response.status_code} {response.text[:200]}"
        )

    data: dict[str, Any] = {}
    try:
        data = response.json()
    except Exception as exc:
        raise SkyMailAuthError(f"genToken 响应不是 JSON: {response.text[:200]}") from exc

    if data.get("code") != 200:
        message = data.get("message") or data
        raise SkyMailAuthError(f"genToken 失败: {message}")

    token = normalize_skymail_token(str((data.get("data") or {}).get("token") or ""))
    if not token:
        raise SkyMailAuthError(f"genToken 未返回 token: {data}")
    return token


def resolve_skymail_token(
    api_base: str,
    *,
    auth_token: str = "",
    email: str = "",
    password: str = "",
    force_refresh: bool = False,
    proxy: Optional[str] = None,
) -> str:
    """优先用已保存 token；需要时可强制用账号密码刷新。"""
    token = normalize_skymail_token(auth_token)
    if force_refresh:
        if not email or not password:
            raise SkyMailAuthError("SkyMail 强制刷新 Token 需要管理员邮箱和密码")
        return fetch_skymail_token(api_base, email, password, proxy=proxy)
    if token:
        return token
    if email and password:
        return fetch_skymail_token(api_base, email, password, proxy=proxy)
    raise SkyMailAuthError(
        "SkyMail 未配置 Token：请填写 skymail_email + skymail_password，或手动填写 skymail_token"
    )


def persist_skymail_token(token: str, *, provider_key: str = "") -> None:
    """将刷新后的 token 写回 provider setting（若已配置 provider_key）。"""
    key = str(provider_key or "").strip()
    if not key or not token:
        return
    from infrastructure.provider_settings_repository import ProviderSettingsRepository

    repo = ProviderSettingsRepository()
    item = repo.get_by_key("mailbox", key)
    if not item:
        return
    auth = dict(item.get_auth())
    auth["skymail_token"] = normalize_skymail_token(token)
    repo.save(
        setting_id=int(item.id or 0),
        provider_type=item.provider_type,
        provider_key=item.provider_key,
        display_name=item.display_name,
        auth_mode=item.auth_mode,
        enabled=bool(item.enabled),
        is_default=bool(item.is_default),
        config=item.get_config(),
        auth=auth,
        metadata=item.get_metadata(),
    )
