"""日志查看与清空接口。"""

import logging
import os
from collections import deque

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()


# 获取日志
@router.get("/logs")
async def get_logs(lines: int = 1000):
    """获取最近的日志，统一按UTF-8读取并返回字符串，避免分块解码导致的乱码。"""
    log_file = "logs/app.log"
    try:
        if not os.path.exists(log_file):
            return {"logs": ""}

        # 使用 UTF-8 严格解码，遇到异常字符以替换符显示，避免抛错
        from collections import deque
        dq = deque(maxlen=max(10, lines))
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                dq.append(line.rstrip('\n'))
        return {"logs": "\n".join(list(dq)[-lines:])}
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        return {"logs": "日志读取失败，请检查日志文件权限和编码"}

@router.post("/logs/clear")
async def clear_logs():
    """清空日志文件内容"""
    try:
        log_file = "logs/app.log"
        # 确保目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        # 以写模式截断文件
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("")
        logger.info("日志文件已被清空")
        return {"success": True, "message": "日志已清空"}
    except Exception as e:
        logger.error(f"清空日志失败: {str(e)}")
        return {"success": False, "message": f"清空日志失败: {str(e)}"}
