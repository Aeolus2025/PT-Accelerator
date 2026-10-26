"""操作日志。

每个用户操作记一条，格式为 `[OP] 动作 结果=成功 字段=值 ...`。
动作名与字段名由调用点直接写中文，本模块不做翻译。

只记录操作本身与结果，不接收密码、密钥、令牌这类凭据——
调用点本来就不该传，也不给它们留兜底逻辑。
"""

import logging
import time
from typing import Any, Optional

logger = logging.getLogger("app.op")

# 只记 origin：URL 的路径与查询串里常带凭据
_URL_KEYS = {"地址", "回调地址", "上报地址"}


def _url_origin(value: Any) -> str:
    """从 URL 里只取 origin，丢掉路径与查询串。"""
    text = str(value or "")
    if "://" not in text:
        return text
    parts = text.split("://", 1)
    return parts[0] + "://" + parts[1].split("/", 1)[0]


class Timer:
    """给耗时操作计时，渲染成 `耗时=37ms`。

    需在调用 log_op 之前转成 int 或 str，否则拿到的是对象本身。
    """

    __slots__ = ("_start",)

    def __init__(self) -> None:
        self._start = time.perf_counter()

    def __int__(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)

    def __str__(self) -> str:
        return str(int(self))


def _render(key: str, value: Any) -> Optional[str]:
    if value is None:
        return None
    if key in _URL_KEYS:
        return f"{key}={_url_origin(value)}"
    if isinstance(value, Timer):
        return f"{key}={int(value)}ms"
    if isinstance(value, bool):
        return f"{key}={'是' if value else '否'}"
    return f"{key}={value}"


def log_op(
    action: str,
    *,
    ok: bool = True,
    level: Optional[int] = None,
    **fields: Any,
) -> None:
    """记录一条操作日志。

    成功记 INFO，失败记 ERROR；业务性拒绝由调用方传 level=logging.WARNING。
    值为 None 的字段不渲染，调用点可以直接写 `原因=None if ok else ...`。
    """
    if level is None:
        level = logging.INFO if ok else logging.ERROR
    parts = [f"[OP] {action}", f"结果={'成功' if ok else '失败'}"]
    for key, value in fields.items():
        rendered = _render(key, value)
        if rendered:
            parts.append(rendered)
    logger.log(level, " ".join(parts))
