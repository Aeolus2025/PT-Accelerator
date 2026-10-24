"""操作日志。

每个用户操作记一条，格式固定为 `[OP] action target=... ok=... 键=值`，
既方便人读，也方便按 action 检索。
"""

import logging
from typing import Any, Optional

logger = logging.getLogger("app.op")

# 完全不记录
_FORBIDDEN = {
    "password",
    "new_password",
    "current_password",
    "confirm_password",
    "csrf_token",
    "session",
    "cookie",
}

# 只记首尾各 2 位
_MASKED = {
    "password_hash",
    "secret_key",
    "api_key",
    "apikey",
    "token",
    "passkey",
    "secret",
}

# 只记 origin，路径里常带凭据
_URL_KEYS = {"url", "webhook_url", "announce", "announce_url", "endpoint"}


def mask(value: Any) -> str:
    """遮蔽敏感值，保留首尾便于比对。"""
    text = str(value or "")
    if len(text) <= 4:
        return "****"
    return f"{text[:2]}****{text[-2:]}"


def _url_origin(value: Any) -> str:
    """从 URL 里只取 origin，丢掉路径与查询串。"""
    text = str(value or "")
    if "://" not in text:
        return text
    parts = text.split("://", 1)
    return parts[0] + "://" + parts[1].split("/", 1)[0]


def _format(fields: dict) -> str:
    parts = []
    for key, value in fields.items():
        lowered = key.lower()
        if lowered in _FORBIDDEN:
            continue
        if lowered in _MASKED:
            parts.append(f"{key}={mask(value)}")
        elif lowered in _URL_KEYS:
            parts.append(f"{key}={_url_origin(value)}")
        else:
            parts.append(f"{key}={value}")
    return " ".join(parts)


def log_op(
    action: str,
    *,
    target: Optional[str] = None,
    ok: bool = True,
    level: Optional[int] = None,
    **fields: Any,
) -> None:
    """记录一条操作日志。

    成功记 INFO，失败记 ERROR；业务性拒绝由调用方传 level=logging.WARNING。
    """
    if level is None:
        level = logging.INFO if ok else logging.ERROR
    head = f"[OP] {action}"
    if target is not None:
        head += f" target={target}"
    head += f" ok={str(bool(ok)).lower()}"
    extra = _format(fields)
    if extra:
        head += " " + extra
    logger.log(level, head)
