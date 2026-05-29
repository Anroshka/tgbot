"""Ссылка Happ для импорта подписки: https://happ.su/config#<Base64 URL-safe>

Документация: https://www.happ.su/main/faq/adding-configuration-subscription
"""

from __future__ import annotations

import base64
import os
from urllib.parse import quote


def happ_deeplink_enabled() -> bool:
    v = os.getenv("HAPP_DEEPLINK", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _encode_subscription_payload(subscription_url: str) -> str:
    mode = os.getenv("HAPP_LINK_ENCODE", "base64").strip().lower()
    if mode in ("url", "encode", "percent", "uri"):
        return quote(subscription_url, safe="")
    raw = base64.urlsafe_b64encode(subscription_url.encode("utf-8")).decode("ascii")
    return raw.rstrip("=")


def build_happ_config_url(subscription_url: str, profile_name: str = "") -> str | None:
    """https://happ.su/config#… — в тексте сообщения или по нажатию в чате."""
    _ = profile_name
    sub = subscription_url.strip()
    if not sub or not happ_deeplink_enabled():
        return None
    base = os.getenv("HAPP_CONFIG_URL", "https://happ.su/config").strip().rstrip("/")
    if not base:
        return None
    encoded = _encode_subscription_payload(sub)
    return f"{base}#{encoded}"
