"""Backend error-message internationalisation (i18n).

A small message catalogue keyed by HTTP status code, with per-locale text.
The ``Accept-Language`` request header selects the locale (falling back to
English). A middleware rewrites the ``message``/``detail`` of common error
responses (401/403/404/422/429/500) into the negotiated language without
changing status codes or response shape.

Supported locales: ``en`` (default) and ``zh``.
"""

from __future__ import annotations

from typing import Any

# status_code -> locale -> message
MESSAGES: dict[int, dict[str, str]] = {
    401: {
        "en": "Authentication required or credentials invalid.",
        "zh": "需要身份认证或凭证无效。",
    },
    403: {
        "en": "You do not have permission to perform this action.",
        "zh": "您没有执行此操作的权限。",
    },
    404: {
        "en": "The requested resource was not found.",
        "zh": "未找到请求的资源。",
    },
    422: {
        "en": "The request could not be validated.",
        "zh": "请求内容校验失败。",
    },
    429: {
        "en": "Too many requests. Please slow down.",
        "zh": "请求过于频繁，请稍后再试。",
    },
    500: {
        "en": "Internal server error.",
        "zh": "服务器内部错误。",
    },
}

DEFAULT_LOCALE = "en"
SUPPORTED = ("en", "zh")


def negotiate_locale(accept_language: str | None) -> str:
    """
    Pick the best supported locale from an Accept-Language header.

    Handles quality weights and subtags (``zh-CN`` -> ``zh``). Defaults to en.
    """
    if not accept_language:
        return DEFAULT_LOCALE

    # Parse "en-US,en;q=0.9,zh;q=0.8" into ordered base tags by q desc.
    parsed: list[tuple[str, float]] = []
    for part in accept_language.split(","):
        part = part.strip()
        if not part:
            continue
        tag, _, params = part.partition(";")
        q = 1.0
        for p in params.split(";"):
            p = p.strip()
            if p.startswith("q="):
                try:
                    q = float(p[2:])
                except ValueError:
                    q = 1.0
        base = tag.strip().split("-")[0].lower()
        parsed.append((base, q))

    parsed.sort(key=lambda x: x[1], reverse=True)
    for base, _q in parsed:
        if base in SUPPORTED:
            return base
    return DEFAULT_LOCALE


def message_for(status_code: int, locale: str) -> str:
    """Localized message for a status code (English fallback)."""
    catalog = MESSAGES.get(status_code)
    if not catalog:
        return MESSAGES[500].get(locale, MESSAGES[500][DEFAULT_LOCALE])
    return catalog.get(locale, catalog[DEFAULT_LOCALE])


def localize_error_body(body: Any, status_code: int, locale: str) -> Any:
    """
    Return a copy of an error JSON body with a localized ``message`` added and
    ``detail`` (when it is a plain string) localized. Non-dict bodies and
    non-error status codes pass through unchanged.
    """
    if status_code not in MESSAGES or not isinstance(body, dict):
        return body
    out = dict(body)
    out["message"] = message_for(status_code, locale)
    # Only replace a string detail; structured 422 detail lists are kept.
    if isinstance(out.get("detail"), str):
        out["detail"] = message_for(status_code, locale)
    return out
