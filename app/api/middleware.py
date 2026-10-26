"""请求级日志中间件：为每个 API 请求生成 rid 并记录访问日志。"""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware

from app.core.log_context import new_rid, set_rid

access = logging.getLogger("app.http")

# 这些路径不记访问日志：
# - /api/logs 被日志面板每 3 秒轮询，记下来会让日志自我膨胀
# - 静态资源一次页面加载就是十几个请求
SKIP_PREFIXES = ("/static/", "/favicon.ico")
SKIP_PATHS = ("/api/logs",)

# 超过这个耗时的请求额外提一条 WARNING
SLOW_MS = 3000


def _should_log(path: str) -> bool:
    if path in SKIP_PATHS:
        return False
    return not path.startswith(SKIP_PREFIXES)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """给每个 API 请求分配 rid，请求结束后记一条访问日志。"""

    async def dispatch(self, request, call_next):
        path = request.url.path
        if not path.startswith("/api/") or not _should_log(path):
            return await call_next(request)

        rid = new_rid()
        set_rid(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = int((time.perf_counter() - started) * 1000)
            access.exception("[HTTP] %s %s 状态码=500 耗时=%sms", request.method, path, elapsed)
            raise

        elapsed = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 500:
            level = logging.ERROR
        elif response.status_code >= 400:
            level = logging.WARNING
        else:
            level = logging.INFO
        access.log(
            level,
            "[HTTP] %s %s 状态码=%s 耗时=%sms",
            request.method,
            path,
            response.status_code,
            elapsed,
        )
        if elapsed >= SLOW_MS:
            access.warning("[HTTP] 慢请求 %s %s 耗时=%sms", request.method, path, elapsed)
        return response
