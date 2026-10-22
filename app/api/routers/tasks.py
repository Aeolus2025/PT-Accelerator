"""任务类接口：手动触发 IP 优选、调度器状态、任务运行状态。"""

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.globals import get_hosts_manager, get_scheduler_service
from app.services.hosts_manager import HostsManager
from app.services.scheduler import SchedulerService
from app.services.task_notify import _send_task_notify

logger = logging.getLogger(__name__)

router = APIRouter()


# 手动运行CloudflareSpeedTest
@router.post("/run-cloudflare-test")
async def run_cloudflare_test(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """手动运行CloudflareSpeedTest和更新hosts源（严格串行）"""
    try:
        # 创建组合任务
        def combined_task():
            logger.info("手动执行组合任务：优选IP + 更新tracker + 更新hosts（严格串行）")
            ok = hosts_manager.run_cfst_and_update_hosts()
            status = hosts_manager.get_task_status() if hasattr(hosts_manager, 'get_task_status') else {}
            msg = status.get('message') if isinstance(status, dict) else ("执行完成" if ok else "执行失败")
            logger.info(f"[任务通知] IP优选与Hosts更新 -> {msg}")
            _send_task_notify("IP优选与Hosts更新", msg)
        # 在后台运行，避免阻塞API响应
        background_tasks.add_task(combined_task)
        return {"message": "IP优选与Hosts更新任务已启动（严格串行）"}
    except Exception as e:
        logger.error(f"启动组合任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动组合任务失败: {str(e)}")

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

# 兼容旧版前端，避免404错误
@router.get("/last-result")
async def get_last_result_compatibility():
    """兼容旧版前端，返回空结果"""
    return {
        "success": False,
        "message": "此API端点已弃用，优选结果不再显示",
        "time": "",
        "results": []
    }

# 任务状态API
@router.get("/task-status")
async def get_task_status(
    hosts_manager: HostsManager = Depends(get_hosts_manager),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """获取当前任务状态
    
    前端轮询此接口以获取后台任务的执行状态
    
    Returns:
        任务状态：
        - status: done | running
        - message: 任务状态描述
    """
    try:
        # 首先检查scheduler_service中的任务状态
        scheduler_status = getattr(scheduler_service, 'get_task_status', lambda: {"status": "done", "message": "无任务"})()
        if scheduler_status.get("status") == "running":
            return scheduler_status
            
        # 然后检查hosts_manager中的任务状态
        hosts_status = hosts_manager.get_task_status()
        if hosts_status.get("status") == "running":
            return hosts_status
            
        # 如果都没有运行中的任务，返回默认完成状态
        return {
            "status": "done",
            "message": "无正在运行的任务"
        }
    except Exception as e:
        logger.error(f"获取任务状态时出错: {str(e)}", exc_info=True)
        # 返回安全的默认状态
        return {
            "status": "done",
            "message": "获取任务状态出错，请检查日志"
        }

