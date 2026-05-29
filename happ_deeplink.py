"""Ссылки Happ для импорта подписки (iOS / Android).

Рекомендуется для Telegram (url-кнопка): https://happ.su/config#<подписка в Base64 URL-safe>
Запасной вариант: happ://add/<url>#<имя>
Документация: https://www.happ.su/main/faq/adding-configuration-subscription
"""

from __future__ import annotations

import base64
import os
from urllib.parse import quote

# Telegram: максимальная длина url у inline-кнопки
_TELEGRAM_URL_MAX = 2048


def happ_deeplink_enabled() -> bool:
    v = os.getenv("HAPP_DEEPLINK", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _use_happ_config_page() -> bool:
    v = os.getenv("HAPP_USE_CONFIG_URL", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _encode_subscription_payload(subscription_url: str) -> str:
    """Кодирование URL подписки для фрагмента # в happ.su/config."""
    mode = os.getenv("HAPP_LINK_ENCODE", "base64").strip().lower()
    if mode in ("url", "encode", "percent", "uri"):
        return quote(subscription_url, safe="")
    raw = base64.urlsafe_b64encode(subscription_url.encode("utf-8")).decode("ascii")
    return raw.rstrip("=")


def build_happ_config_url(subscription_url: str, profile_name: str = "") -> str | None:
    """https://happ.su/config#<закодированная_ссылка_подписки> — подходит для кнопки Telegram."""
    _ = profile_name  # имя профиля в этом формате не передаётся
    sub = subscription_url.strip()
    if not sub or not happ_deeplink_enabled():
        return None
    base = os.getenv("HAPP_CONFIG_URL", "https://happ.su/config").strip().rstrip("/")
    if not base:
        return None
    encoded = _encode_subscription_payload(sub)
    return f"{base}#{encoded}"


def build_happ_deeplink(subscription_url: str, profile_name: str = "") -> str | None:
    """happ://add/… — запасной deep link (Telegram url-кнопки не принимают)."""
    sub = subscription_url.strip()
    if not sub or not happ_deeplink_enabled():
        return None
    deeplink = f"happ://add/{sub}"
    name = (profile_name or "").strip()
    if name:
        deeplink += f"#{quote(name, safe='')}"
    return deeplink


def build_happ_telegram_url(subscription_url: str, profile_name: str = "") -> str | None:
    """HTTPS-ссылка для inline url-кнопки в Telegram."""
    if not happ_deeplink_enabled():
        return None

    if _use_happ_config_page():
        config_url = build_happ_config_url(subscription_url, profile_name)
        if config_url and len(config_url) <= _TELEGRAM_URL_MAX:
            return config_url

    deeplink = build_happ_deeplink(subscription_url, profile_name)
    if not deeplink:
        return None
    redirect = os.getenv("HAPP_INSTALL_REDIRECT_URL", "").strip()
    if redirect:
        return f"{redirect.rstrip('/')}?url={quote(deeplink, safe='')}"
    return None


build_happ_open_url = build_happ_telegram_url
