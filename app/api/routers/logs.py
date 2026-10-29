"""日志查看、级别设置与清空接口。

级别筛选与关键词搜索都在面板侧完成：服务端只按文件原样返回记录，
两处过滤规则就不会出现「面板能搜到、接口搜不到」这类分歧。
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body

from app.core import config_store, logging_setup
from app.utils.oplog import log_op

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/logs")
async def get_logs(lines: int = 1000, offset: int = 0):
    """读取日志。

    offset 传上次返回的值即可增量拉取；每条记录只有时间、级别与原文，
    面板直接渲染原文，与 logs/app.log 里的那一行完全一致。
    """
    try:
        return logging_setup.read_logs(offset=offset, max_lines=lines)
    except Exception as e:
        logger.exception("[LOGS] 读取日志失败 错误=%s", str(e))
        return {
            "records": [],
            "offset": 0,
            "size": 0,
            "truncated": False,
            "error": "日志读取失败，请检查日志文件权限",
        }


@router.get("/logs/level")
async def get_log_level():
    """当前日志级别，供面板下拉框回显。"""
    return {
        "level": logging_setup.runtime_level_name(),
        "levels": list(logging_setup.LEVEL_NAMES),
        "env_level": logging_setup.env_level_name() or "",
    }


@router.post("/logs/level")
async def set_log_level(payload: Dict[str, Any] = Body(default={})):
    """调整日志记录级别：立即生效，并写入配置供下次启动沿用。

    环境变量 LOG_LEVEL 优先级高于配置，设置后会在下次重启时被它覆盖，
    这里把 env_level 一并返回，由面板提示用户。
    """
    name = str((payload or {}).get("level", "")).strip().upper()
    if name not in logging_setup.LEVEL_NAMES:
        return {
            "success": False,
            "message": "不支持的日志级别: %s" % (name or "空"),
            "level": logging_setup.runtime_level_name(),
        }

    try:
        logging_setup.apply_level(name)
        config_store.mutate(lambda cfg: cfg.setdefault("logging", {}).__setitem__("level", name))
        log_op("调整日志级别", 级别=name)
    except Exception as e:
        logger.exception("[LOGS] 设置日志级别失败 级别=%s 错误=%s", name, str(e))
        return {"success": False, "message": "设置失败: %s" % str(e)}

    return {
        "success": True,
        "level": name,
        "levels": list(logging_setup.LEVEL_NAMES),
        "env_level": logging_setup.env_level_name() or "",
    }


@router.post("/logs/clear")
async def clear_logs():
    """清空日志文件。"""
    try:
        logging_setup.truncate_log()
        # 先截断再记：写在下一次打开的新文件里，所以这一行不会被自己清掉
        log_op("清空日志")
        return {"success": True, "message": "日志已清空"}
    except Exception as e:
        logger.exception("[LOGS] 清空日志失败 错误=%s", str(e))
        return {"success": False, "message": f"清空日志失败: {str(e)}"}
