"""路由层共享的配置读取与常量。"""

from typing import Any, Callable, Dict, Optional

from fastapi import Depends, HTTPException, status

from app.auth import get_current_user
from app.core import config_store
from app.core.constants import CONFIG_PATH
from app.models import User


def get_file_config() -> Dict[str, Any]:
    """从文件读取最新配置，每次调用都重新读盘。"""
    return config_store.read(CONFIG_PATH)


def save_config_and_sync(change: Callable[[Dict[str, Any]], Any]) -> None:
    """在锁内修改配置写盘，并刷新各服务手里的缓存。

    必须传「修改函数」而不是改好的配置对象：调用方往往先 read 一份、
    做几秒的检测、再写回，整份覆盖会把期间别人的改动一起冲掉。
    修改函数在锁内拿到最新配置后原地改。

    配置以磁盘为唯一来源，写盘后只需刷新各服务手里的缓存
    （目前是 HostsManager 的 Cloudflare 白名单集合）。
    """
    from app.globals import get_hosts_manager

    config_store.mutate(change)

    hosts_manager = get_hosts_manager()
    if hosts_manager is not None:
        hosts_manager.reload_whitelist()


async def require_login(current_user: Optional[User] = Depends(get_current_user)) -> User:
    """要求已登录。

    认证未启用时 get_current_user 返回 guest，这里直接放行；
    启用后未登录会拿到 None，返回 401，前端 api.js 统一跳登录页。
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录或登录已失效",
        )
    return current_user
