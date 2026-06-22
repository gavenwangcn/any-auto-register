"""ChatGPT 协议邮箱注册 worker。"""
from __future__ import annotations

from typing import Callable

from platforms.chatgpt.register import RegistrationEngine


class _MailboxEmailService:
    def __init__(self, *, mailbox, mailbox_account, provider: str, before_ids=None, log_fn: Callable[[str], None] | None = None):
        self.service_type = type("ST", (), {"value": provider})()
        self._mailbox = mailbox
        self._mailbox_account = mailbox_account
        self._before_ids = set(before_ids or [])
        self._log_fn = log_fn or (lambda _msg: None)
        self._acct = None

    def create_email(self, config=None):
        self._acct = self._mailbox_account
        return {
            "email": self._mailbox_account.email,
            "service_id": getattr(self._mailbox_account, "account_id", ""),
            "token": getattr(self._mailbox_account, "account_id", ""),
        }

    def get_verification_code(self, email=None, email_id=None, timeout=120, pattern=None, otp_sent_at=None):
        acct = self._acct or self._mailbox_account
        target = email or getattr(acct, "email", "") or getattr(acct, "account_id", "")
        self._log_fn(
            f"[mailbox] 开始轮询验证码 target={target} timeout={timeout}s "
            f"before_ids={len(self._before_ids)} otp_sent_at={otp_sent_at}"
        )
        try:
            code = self._mailbox.wait_for_code(
                acct,
                keyword="",
                timeout=timeout,
                code_pattern=pattern,
                before_ids=self._before_ids,
            )
            self._log_fn(f"[mailbox] 验证码获取成功 target={target}")
            return code
        except TimeoutError as exc:
            self._log_fn(f"[mailbox] 验证码轮询超时 target={target}: {exc}")
            raise
        except Exception as exc:
            self._log_fn(f"[mailbox] 验证码获取异常 target={target}: {exc}")
            raise

    def update_status(self, success, error=None):
        return None

    @property
    def status(self):
        return None


class ChatGPTProtocolMailboxWorker:
    def __init__(
        self,
        *,
        mailbox,
        mailbox_account,
        provider: str,
        proxy_url: str | None = None,
        log_fn: Callable[[str], None] = print,
        before_ids: set | None = None,
    ):
        if not mailbox or not mailbox_account:
            raise ValueError("ChatGPT 注册流程依赖 mailbox provider，当前未获取到邮箱账号")
        if hasattr(mailbox, "_trace_log"):
            mailbox._trace_log = log_fn
        email_service = _MailboxEmailService(
            mailbox=mailbox,
            mailbox_account=mailbox_account,
            provider=provider,
            before_ids=before_ids,
            log_fn=log_fn,
        )
        self.log_fn = log_fn
        self.engine = RegistrationEngine(
            email_service=email_service,
            proxy_url=proxy_url,
            callback_logger=log_fn,
        )

    def run(self, *, email: str, password: str):
        self.log_fn(f"[ChatGPTProtocolMailboxWorker] ▶ run email={email}")
        self.engine.email = email
        self.engine.password = password
        result = self.engine.run()
        if not result or not result.success:
            self.log_fn(f"[ChatGPTProtocolMailboxWorker] ✗ run 失败: {result.error_message if result else 'unknown'}")
            raise RuntimeError(result.error_message if result else "注册失败")
        self.log_fn(f"[ChatGPTProtocolMailboxWorker] ◀ run 成功 email={result.email}")
        return result
