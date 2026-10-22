"""通知模板渲染：Jinja2 沙箱 + 变量白名单 + 默认模板兜底"""

import logging
import socket
from datetime import datetime

import jinja2
from jinja2.sandbox import SandboxedEnvironment

from version import get_version

logger = logging.getLogger("notify")

# 模板长度上限，防止超大模板拖慢渲染
MAX_TEMPLATE_LEN = 4000

# 沙箱环境：禁止访问危险属性与方法
_env = SandboxedEnvironment(
    undefined=jinja2.StrictUndefined,
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

DEFAULT_TITLE = "{{ status_emoji }} {{ task }}"
DEFAULT_CONTENT = "{{ status_emoji }} {{ content }}\n\n🕒 {{ time }}"

STATUS_EMOJI = {"success": "✅", "failed": "❌", "info": "ℹ️"}

# 模板可用的变量白名单
ALLOWED_VARS = (
    "task",
    "content",
    "status",
    "status_emoji",
    "time",
    "date",
    "hostname",
    "version",
)


def _hostname() -> str:
    try:
        return socket.gethostname()
    except Exception:
        return "unknown"


def build_context(task: str, content: str, status: str = "info") -> dict:
    """构造模板上下文。只放标量，不放 config / request 等对象。"""
    now = datetime.now()
    status = status if status in STATUS_EMOJI else "info"
    return {
        "task": str(task or ""),
        "content": str(content or ""),
        "status": status,
        "status_emoji": STATUS_EMOJI[status],
        "time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "date": now.strftime("%Y-%m-%d"),
        "hostname": _hostname(),
        "version": str(get_version()),
    }


def guess_status(content: str) -> str:
    """按关键词推断状态。失败优先，并识别「未完成」这类否定表述。"""
    text = str(content or "")
    failed_markers = (
        "失败", "错误", "异常", "未完成", "未成功", "未能", "超时",
        "error", "Error", "ERROR", "failed", "Failed",
    )
    success_markers = ("完成", "成功", "success", "Success", "已更新")
    if any(m in text for m in failed_markers):
        return "failed"
    if any(m in text for m in success_markers):
        return "success"
    return "info"


def _render_one(source: str, ctx: dict, fallback: str) -> str:
    """渲染单个模板，失败时回退默认模板"""
    src = (source or "").strip() or fallback
    if len(src) > MAX_TEMPLATE_LEN:
        logger.warning("通知模板超长（%d 字符），已回退默认模板", len(src))
        src = fallback
    try:
        return _env.from_string(src).render(**ctx)
    except Exception as e:
        logger.error("通知模板渲染失败，已回退默认模板：%s", e)
        try:
            return _env.from_string(fallback).render(**ctx)
        except Exception:
            return f"{ctx['status_emoji']} {ctx['content']}"


def render(title: str, content: str, template: dict | None = None) -> tuple[str, str]:
    """渲染通知标题与内容，返回 (title, content)"""
    tpl = template if isinstance(template, dict) else {}
    ctx = build_context(title, content, guess_status(content))
    r_title = _render_one(tpl.get("title"), ctx, DEFAULT_TITLE)
    r_content = _render_one(tpl.get("content"), ctx, DEFAULT_CONTENT)
    return r_title, r_content


def validate(source: str, ctx: dict) -> str | None:
    """
    试渲染校验模板，返回错误信息；无错误返回 None。

    沙箱拦截发生在渲染期而非编译期，因此必须真的渲染一遍才能发现问题。
    """
    src = (source or "").strip()
    if not src:
        return None
    if len(src) > MAX_TEMPLATE_LEN:
        return f"模板超过 {MAX_TEMPLATE_LEN} 字符"
    try:
        _env.from_string(src).render(**ctx)
    except Exception as e:
        return str(e)
    return None


def preview(title_tpl: str, content_tpl: str, sample: dict | None = None) -> dict:
    """渲染预览，同时返回语法错误供前端提示"""
    s = sample or {
        "task": "IP优选与Hosts更新",
        "content": "优选完成，已更新 12 条 hosts 记录",
        "status": "success",
    }
    ctx = build_context(s.get("task", ""), s.get("content", ""), s.get("status", "info"))
    errors = {}
    for field, source in (("title", title_tpl), ("content", content_tpl)):
        err = validate(source, ctx)
        if err:
            errors[field] = err
    return {
        "title": _render_one(title_tpl, ctx, DEFAULT_TITLE),
        "content": _render_one(content_tpl, ctx, DEFAULT_CONTENT),
        "vars": {k: ctx[k] for k in ALLOWED_VARS},
        "errors": errors,
    }
