"""通过邮箱密码重新登录，获取 ChatGPT / Codex OAuth Token。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from core.base_mailbox import MailboxAccount, create_mailbox
from core.base_platform import Account
from infrastructure.provider_settings_repository import ProviderSettingsRepository

from .constants import CODEX_CLIENT_ID


def _resolve_mailbox_context(account: Account) -> tuple[str, str, str]:
    extra = dict(account.extra or {})
    provider_name = ""
    mailbox_email = str(account.email or "").strip()
    mailbox_account_id = ""

    for item in list(extra.get("provider_accounts") or []):
        if not isinstance(item, dict) or item.get("provider_type") != "mailbox":
            continue
        provider_name = str(item.get("provider_name") or "").strip()
        mailbox_email = str(item.get("login_identifier") or mailbox_email).strip()
        metadata = dict(item.get("metadata") or {})
        mailbox_account_id = str(metadata.get("account_id") or "").strip()
        break

    verification_mailbox = dict(extra.get("verification_mailbox") or {})
    if verification_mailbox:
        provider_name = provider_name or str(verification_mailbox.get("provider") or "").strip()
        mailbox_email = str(verification_mailbox.get("email") or mailbox_email).strip()
        mailbox_account_id = mailbox_account_id or str(verification_mailbox.get("account_id") or "").strip()

    if not provider_name:
        provider_name = str(ProviderSettingsRepository().get_default_provider_key("mailbox") or "").strip()
    return provider_name, mailbox_email, mailbox_account_id


def build_static_otp_callback(
    otp_code: str,
    *,
    log_fn: Callable[[str], None] = print,
) -> Callable[[], str] | None:
    code = str(otp_code or "").strip()
    if not code:
        return None

    def otp_cb() -> str:
        log_fn(f"使用手动填写的验证码: {code}")
        return code

    return otp_cb


def build_mailbox_otp_callback_for_email(
    email: str,
    *,
    mail_provider: str = "",
    log_fn: Callable[[str], None] = print,
    timeout: int = 600,
) -> Callable[[], str] | None:
    provider_name = str(mail_provider or "").strip()
    if not provider_name:
        provider_name = str(ProviderSettingsRepository().get_default_provider_key("mailbox") or "").strip()
    if not provider_name:
        return None

    mailbox_email = str(email or "").strip()
    settings = ProviderSettingsRepository().resolve_runtime_settings("mailbox", provider_name, {})
    mailbox = create_mailbox(provider=provider_name, extra=settings)
    mail_acct = MailboxAccount(
        email=mailbox_email,
        account_id=mailbox_email,
    )

    def otp_cb() -> str:
        log_fn("等待邮箱验证码...")
        code = mailbox.wait_for_code(mail_acct, keyword="openai", timeout=timeout)
        if code:
            log_fn(f"验证码: {code}")
        return code or ""

    return otp_cb


def build_mailbox_otp_callback(
    account: Account,
    *,
    log_fn: Callable[[str], None] = print,
    timeout: int = 600,
) -> Callable[[], str] | None:
    provider_name, mailbox_email, mailbox_account_id = _resolve_mailbox_context(account)
    if not provider_name:
        return None

    settings = ProviderSettingsRepository().resolve_runtime_settings("mailbox", provider_name, {})
    mailbox = create_mailbox(provider=provider_name, extra=settings)
    mail_acct = MailboxAccount(
        email=mailbox_email or account.email,
        account_id=mailbox_account_id or mailbox_email or account.email,
    )

    def otp_cb() -> str:
        log_fn("等待邮箱验证码...")
        code = mailbox.wait_for_code(mail_acct, keyword="openai", timeout=timeout)
        if code:
            log_fn(f"验证码: {code}")
        return code or ""

    return otp_cb


def resolve_otp_callback(
    *,
    email: str,
    account: Account | None = None,
    otp_code: str = "",
    mail_provider: str = "",
    log_fn: Callable[[str], None] = print,
) -> Callable[[], str] | None:
    static_cb = build_static_otp_callback(otp_code, log_fn=log_fn)
    if static_cb:
        return static_cb
    if account is not None:
        mailbox_cb = build_mailbox_otp_callback(account, log_fn=log_fn)
        if mailbox_cb:
            return mailbox_cb
    return build_mailbox_otp_callback_for_email(
        email,
        mail_provider=mail_provider,
        log_fn=log_fn,
    )


def fetch_tokens_via_login(
    email: str,
    password: str,
    *,
    proxy: str | None = None,
    headless: bool = True,
    otp_callback: Callable[[], str] | None = None,
    phone_callback: Callable[[], str] | None = None,
    log_fn: Callable[[str], None] = print,
) -> dict | None:
    """在全新浏览器中走 Codex CLI OAuth，用邮箱密码换取 token。"""
    from platforms.chatgpt.browser_register import ChatGPTBrowserRegister

    worker = ChatGPTBrowserRegister(
        headless=headless,
        proxy=proxy,
        otp_callback=otp_callback,
        phone_callback=phone_callback,
        log_fn=log_fn,
    )
    return worker._retry_oauth_fresh_browser(email, password)


def fetch_external_token_export(
    email: str,
    password: str,
    *,
    proxy: str | None = None,
    headless: bool = True,
    otp_code: str = "",
    mail_provider: str = "",
    email_service: str = "",
    log_fn: Callable[[str], None] = print,
) -> dict:
    """外部账号：登录并返回完整导出 JSON（不依赖系统内账号记录）。"""
    from core.base_platform import Account, AccountStatus

    email = str(email or "").strip()
    password = str(password or "").strip()
    if not email:
        raise ValueError("请填写账号邮箱")
    if not password:
        raise ValueError("请填写密码")

    otp_callback = resolve_otp_callback(
        email=email,
        otp_code=otp_code,
        mail_provider=mail_provider,
        log_fn=log_fn,
    )
    fetched = fetch_tokens_via_login(
        email,
        password,
        proxy=proxy,
        headless=headless,
        otp_callback=otp_callback,
        phone_callback=None,
        log_fn=log_fn,
    )
    if not fetched:
        raise RuntimeError("登录获取 Token 失败，请检查账号密码、邮箱验证码或浏览器环境")

    synthetic = Account(
        platform="chatgpt",
        email=email,
        password=password,
        user_id=str(fetched.get("account_id") or ""),
        token=str(fetched.get("access_token") or ""),
        status=AccountStatus.REGISTERED,
        extra={
            "email_service": email_service or mail_provider,
            "provider_accounts": (
                [{"provider_type": "mailbox", "provider_name": email_service or mail_provider}]
                if (email_service or mail_provider)
                else []
            ),
        },
    )
    export_payload = build_token_export_payload(
        synthetic,
        password=password,
        token_overrides=fetched,
    )
    if not any(
        export_payload.get(key)
        for key in ("access_token", "refresh_token", "id_token", "session_token")
    ):
        raise RuntimeError("未能获取任何 Token")
    return export_payload


def build_token_export_payload(
    account: Account,
    *,
    password: str = "",
    token_overrides: dict | None = None,
) -> dict:
    """构建与批量导出一致的 ChatGPT Token JSON。"""
    from application.account_exports import DEFAULT_CHATGPT_CLIENT_ID, _chatgpt_auth_info, _decode_jwt_payload

    extra = dict(account.extra or {})
    overrides = dict(token_overrides or {})
    access_token = str(
        overrides.get("access_token")
        or extra.get("access_token")
        or account.token
        or ""
    )
    refresh_token = str(overrides.get("refresh_token") or extra.get("refresh_token") or "")
    id_token = str(overrides.get("id_token") or extra.get("id_token") or "")
    session_token = str(overrides.get("session_token") or extra.get("session_token") or "")
    workspace_id = str(overrides.get("workspace_id") or extra.get("workspace_id") or "")

    payload = _decode_jwt_payload(access_token) if access_token else {}
    auth_info = _chatgpt_auth_info(access_token, id_token)
    client_id = str(
        overrides.get("client_id")
        or extra.get("client_id")
        or payload.get("client_id")
        or CODEX_CLIENT_ID
        or DEFAULT_CHATGPT_CLIENT_ID
    )
    account_id = str(
        overrides.get("account_id")
        or account.user_id
        or extra.get("account_id")
        or auth_info.get("chatgpt_account_id")
        or auth_info.get("account_id")
        or ""
    )
    if not workspace_id:
        workspace_id = str(auth_info.get("organization_id") or "")

    expires_at = None
    exp_timestamp = payload.get("exp")
    if isinstance(exp_timestamp, int) and exp_timestamp > 0:
        expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

    last_refresh_at = None
    iat_timestamp = payload.get("iat")
    if isinstance(iat_timestamp, int) and iat_timestamp > 0:
        last_refresh_at = datetime.fromtimestamp(iat_timestamp, tz=timezone.utc)
    elif overrides.get("last_refresh"):
        last_refresh_at = overrides.get("last_refresh")

    registered_at = None
    created_at = getattr(account, "created_at", 0) or 0
    if isinstance(created_at, int) and created_at > 0:
        registered_at = datetime.fromtimestamp(created_at, tz=timezone.utc)

    email_service = ""
    for item in list(extra.get("provider_accounts") or []):
        if isinstance(item, dict) and item.get("provider_type") == "mailbox":
            email_service = str(item.get("provider_name") or "")
            break
    if not email_service:
        verification_mailbox = dict(extra.get("verification_mailbox") or {})
        email_service = str(verification_mailbox.get("provider") or "")

    def _iso(value: datetime | None) -> str:
        if not value:
            return ""
        return value.isoformat().replace("+00:00", "Z")

    status = getattr(getattr(account, "status", None), "value", None) or str(account.status or "registered")

    return {
        "email": account.email,
        "password": password or account.password or "",
        "client_id": client_id,
        "account_id": account_id,
        "workspace_id": workspace_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "id_token": id_token,
        "session_token": session_token,
        "email_service": email_service,
        "registered_at": _iso(registered_at),
        "last_refresh": _iso(last_refresh_at),
        "expires_at": _iso(expires_at),
        "status": status,
    }
