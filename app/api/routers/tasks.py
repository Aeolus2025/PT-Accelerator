"""任务状态查询接口：调度器状态与任务运行状态（触发入口在 hosts.py）。"""

import logging

from fastapi import APIRouter, Depends

from app.core.tasks import IDLE, registry as task_registry
from app.globals import get_scheduler_service
from app.services.scheduler import SchedulerService

logger = logging.getLogger(__name__)

router = APIRouter()


# 获取调度器状态
@router.get("/scheduler-status")
async def get_scheduler_status(
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """获取调度器状态"""
    return {
        "running": scheduler_service.is_running(),
        "jobs": scheduler_service.get_jobs()
    }

# 任务状态API
@router.get("/task-status")
async def get_task_status():
    """获取当前任务状态

    前端轮询此接口以获取后台任务的执行状态。状态统一记在 core.tasks 的
    registry 里，手动触发与定时触发都写同一张表，这里只读。

    Returns:
        - status: done | running
        - message: 任务状态描述
    """
    return task_registry.running() or dict(IDLE)
