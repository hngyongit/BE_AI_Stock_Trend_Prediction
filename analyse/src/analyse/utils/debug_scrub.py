from __future__ import annotations

import re
from typing import Any


REDACTED = "<redacted>"

SENSITIVE_KEY_MARKERS = (
    "authorization",
    "access_token",
    "refresh_token",
    "openai_api_key",
    "gemini_api_key",
    "api_key",
    "apikey",
    "password",
    "pwd",
    "jwt",
    "secret",
    "db_url",
    "database_url",
    "connection_string",
    "token",
)

SENSITIVE_QUERY_KEYS = (
    "token",
    "access_token",
    "access-token",
    "refresh_token",
    "refresh-token",
    "api_key",
    "api-key",
    "apikey",
    "openai_api_key",
    "openai-api-key",
    "gemini_api_key",
    "gemini-api-key",
    "password",
    "pwd",
    "jwt",
)


def scrub_debug_text(value: str) -> str:
    text = str(value)
    text = re.sub(r"(?i)(authorization\s*[:=]\s*)bearer\s+[A-Za-z0-9._~+\-/=]+", rf"\1Bearer {REDACTED}", text)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]+", rf"\1{REDACTED}", text)
    text = re.sub(r"(?i)sk-[A-Za-z0-9_\-]{12,}", REDACTED, text)
    text = re.sub(r"(?i)AIza[0-9A-Za-z_\-]{12,}", REDACTED, text)
    text = _scrub_url_password(text)
    text = _scrub_query_params(text)
    text = _scrub_key_value_secrets(text)
    return text


def scrub_debug_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: REDACTED if _is_sensitive_key(key) else scrub_debug_payload(value)
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [scrub_debug_payload(value) for value in payload]
    if isinstance(payload, tuple):
        return tuple(scrub_debug_payload(value) for value in payload)
    if isinstance(payload, str):
        return scrub_debug_text(payload)
    return payload


def safe_url_for_log(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return text
    return scrub_debug_text(text)


def _is_sensitive_key(key: Any) -> bool:
    key_text = str(key or "").strip().lower().replace("-", "_")
    return any(marker in key_text for marker in SENSITIVE_KEY_MARKERS)


def _scrub_url_password(text: str) -> str:
    return re.sub(
        r"(?i)([a-z][a-z0-9+.\-]*://[^:/@\s]+:)[^@/\s]+(@)",
        rf"\1{REDACTED}\2",
        text,
    )


def _scrub_query_params(text: str) -> str:
    keys = "|".join(re.escape(key) for key in SENSITIVE_QUERY_KEYS)
    return re.sub(
        rf"(?i)([?&]({keys})=)[^&#\s]+",
        rf"\1{REDACTED}",
        text,
    )


def _scrub_key_value_secrets(text: str) -> str:
    keys = "|".join(re.escape(key) for key in SENSITIVE_QUERY_KEYS)
    text = re.sub(
        rf"(?i)\b({keys})\s*=\s*[^;&\s,]+",
        rf"\1={REDACTED}",
        text,
    )
    text = re.sub(
        rf"(?i)\b({keys})\s*:\s*[^;&\s,]+",
        rf"\1: {REDACTED}",
        text,
    )
    return text
