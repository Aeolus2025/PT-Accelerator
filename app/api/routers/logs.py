"""日志查看与清空接口。"""

import logging
from typing import Optional

from fastapi import APIRouter

from app.core import logging_setup
from app.utils.oplog import log_op

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/logs")
async def get_logs(
    lines: int = 1000,
    level: Optional[str] = None,
    offset: int = 0,
):
    """读取日志。

    level 为逗号分隔的级别列表，如 `WARNING,ERROR`；offset 传上次返回的值即可增量拉取。
    """
    try:
        levels = [item.strip().upper() for item in (level or "").split(",") if item.strip()]
        result = logging_setup.read_logs(offset=offset, max_lines=lines, levels=levels)
        # 兼容旧前端：仍提供拼接好的整串
        result["logs"] = "\n".join(record["text"] for record in result["records"])
        return result
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        return {
            "logs": "",
            "records": [],
            "offset": 0,
            "size": 0,
            "truncated": False,
            "levels": {},
            "error": "日志读取失败，请检查日志文件权限和编码",
        }


@router.post("/logs/clear")
async def clear_logs():
    """清空日志文件。"""
    try:
        logging_setup.truncate_log()
        # 先截断再记：写在下一次打开的新文件里，所以这一行不会被自己清掉
        log_op("logs.clear")
        return {"success": True, "message": "日志已清空"}
    except Exception as e:
        logger.error(f"清空日志失败: {str(e)}")
        return {"success": False, "message": f"清空日志失败: {str(e)}"}
