"""Deep link Happ для импорта подписки в один тап (iOS / Android).

Формат: happ://add/<url_подписки>#<имя_профиля>
Документация: https://www.happ.su/main/faq/adding-configuration-subscription
"""

from __future__ import annotations

import os
from urllib.parse import quote


def happ_deeplink_enabled() -> bool:
    v = os.getenv("HAPP_DEEPLINK", "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def build_happ_open_url(subscription_url: str, profile_name: str = "") -> str | None:
    """Ссылка для кнопки Telegram: открывает Happ и добавляет подписку."""
    sub = subscription_url.strip()
    if not sub or not happ_deeplink_enabled():
        return None

    deeplink = f"happ://add/{sub}"
    name = (profile_name or "").strip()
    if name:
        deeplink += f"#{quote(name, safe='')}"

    redirect = os.getenv("HAPP_INSTALL_REDIRECT_URL", "").strip()
    if redirect:
        return f"{redirect.rstrip('/')}?url={quote(deeplink, safe='')}"
    return deeplink
