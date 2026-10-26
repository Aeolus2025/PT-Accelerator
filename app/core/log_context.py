"""日志关联 ID。

一次 HTTP 请求或一个后台任务对应一个 rid，由 Filter 注入 LogRecord，
格式串里的 %(rid)s 就能把同一段流程的日志串起来。
"""

import contextvars
import logging
import re
import uuid

# 只生成小写十六进制，避免与消息开头的 [OP] / [HTTP] 这类大写标签混淆
RID_LEN = 8

_rid: contextvars.ContextVar[str] = contextvars.ContextVar("rid", default="")


def new_rid() -> str:
    """生成一个新的关联 ID。"""
    return uuid.uuid4().hex[:RID_LEN]


def set_rid(value: str) -> None:
    _rid.set(value)


def get_rid() -> str:
    return _rid.get()


def clear_rid() -> None:
    _rid.set("")


class RidFilter(logging.Filter):
    """把当前 rid 注入 LogRecord，供格式串使用。"""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = _rid.get()
        # 前缀自带中括号和空格，无上下文时为空串，不影响格式
        record.rid = "[%s] " % rid if rid else ""
        return True


RID_RE = re.compile(r"^\w+$")
