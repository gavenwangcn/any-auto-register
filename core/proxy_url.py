"""Proxy URL normalization helpers."""
from __future__ import annotations

import re

_PROXY_SCHEMES = ("http://", "https://", "socks5://", "socks4://")


def normalize_proxy_url(raw: str, *, default_protocol: str = "http") -> str:
    """Normalize common proxy input formats to a full proxy URL.

    Supported inputs:
      - http://user:pass@host:port
      - user:pass@host:port
      - host:port:user:pass  (e.g. RapidProxy export)
      - host:port
    """
    text = str(raw or "").strip()
    if not text:
        return ""

    protocol = str(default_protocol or "http").strip().rstrip(":/") or "http"
    lower = text.lower()
    if any(lower.startswith(scheme) for scheme in _PROXY_SCHEMES):
        return text

    if "@" in text:
        return f"{protocol}://{text}"

    if text.count(":") >= 3:
        host, port, username, password = text.split(":", 3)
        host = host.strip()
        port = port.strip()
        username = username.strip()
        password = password.strip()
        if host and port.isdigit() and username and password:
            return f"{protocol}://{username}:{password}@{host}:{port}"

    if re.match(r"^[\w.\-]+:\d+$", text):
        return f"{protocol}://{text}"

    return text
