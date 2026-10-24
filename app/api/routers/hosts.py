"""Hosts 接口：hosts 源管理、更新、清空重建、手动保存。"""

import logging
import re
from typing import Any, Dict
from urllib.parse import urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.core import config_store
from app.globals import get_hosts_manager
from app.services.hosts_manager import HostsManager
from app.services.task_notify import send_task_notify
from app.utils.oplog import log_op

logger = logging.getLogger(__name__)

router = APIRouter()



# 添加hosts源（URL校验）
@router.post("/hosts-sources")
async def add_hosts_source(
    source: Dict[str, Any],
    background_tasks: BackgroundTasks,  # 新增参数
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """添加hosts源"""
    try:
        # URL校验和自动补全
        url = source.get("url", "")
        if url and not re.match(r"^https?://", url, re.IGNORECASE):
            url = "https://" + url
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Hosts源URL无效，请检查格式")
        source["url"] = url
        def _add(current):
            sources = current.setdefault("hosts_sources", [])
            if any(existing["url"] == source["url"] for existing in sources):
                raise HTTPException(status_code=400, detail="hosts源已存在")
            sources.append(source)

        # 查重与追加在同一把锁内，避免两个并发请求都通过查重后各写一份
        config_store.mutate(_add)
        
        # 更新hosts_manager的配置
        hosts_manager.reload_whitelist()
        
            
        # 异步更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        log_op("hosts.source_add", url=url)
        return {"message": "hosts源已添加，正在后台更新hosts"}
    except HTTPException as e:
        log_op("hosts.source_add", ok=False, level=logging.WARNING, reason=e.detail)
        raise
    except Exception as e:
        logger.error(f"添加hosts源失败: {str(e)}")
        log_op("hosts.source_add", ok=False, error=str(e))
        raise HTTPException(status_code=500, detail=f"添加hosts源失败: {str(e)}")


@router.delete("/hosts-sources")
async def delete_hosts_source(
    url: str,
    background_tasks: BackgroundTasks,  # 新增参数
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """删除hosts源"""
    try:
        def _remove(current):
            sources = current.get("hosts_sources")
            if not sources:
                raise HTTPException(status_code=404, detail="hosts源不存在")
            current["hosts_sources"] = [s for s in sources if s["url"] != url]

        config_store.mutate(_remove)
            
        # 更新hosts_manager的配置
        hosts_manager.reload_whitelist()
        
            
        # 异步更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        log_op("hosts.source_remove", url=url)
        return {"message": "hosts源已删除，正在后台更新hosts"}
    except HTTPException as e:
        log_op("hosts.source_remove", ok=False, level=logging.WARNING, reason=e.detail)
        raise
    except Exception as e:
        logger.error(f"删除hosts源失败: {str(e)}")
        log_op("hosts.source_remove", ok=False, error=str(e))
        raise HTTPException(status_code=500, detail=f"删除hosts源失败: {str(e)}")


# 手动更新hosts
@router.post("/update-hosts")
async def update_hosts(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """手动更新hosts"""
    try:
        # 在后台运行，避免阻塞API响应
        def task():
            ok = hosts_manager.update_hosts()
            msg = hosts_manager.get_task_status()["message"] or ("更新完成" if ok else "更新失败")
            logger.info(f"[任务通知] 仅更新Hosts -> {msg}")
            send_task_notify("仅更新Hosts", msg)
        background_tasks.add_task(task)
        log_op("hosts.update")
        return {"message": "hosts更新任务已启动"}
    except Exception as e:
        logger.error(f"更新hosts失败: {str(e)}")
        log_op("hosts.update", ok=False, error=str(e))
        raise HTTPException(status_code=500, detail=f"更新hosts失败: {str(e)}")


# 获取当前hosts
@router.get("/current-hosts")
async def get_current_hosts(
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """获取当前hosts"""
    try:
        return {"hosts": hosts_manager.read_system_hosts()}
    except Exception as e:
        logger.error(f"获取hosts失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取hosts失败: {str(e)}")


# 运行CloudflareSpeedTest优选脚本
@router.post("/run-cfst-script")
async def run_cfst_script(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """运行CloudflareSpeedTest优选脚本和更新hosts源（严格串行）"""
    try:
        def combined_task():
            logger.info("严格串行执行：优选IP+更新tracker+更新hosts")
            ok = hosts_manager.run_cfst_and_update_hosts()
            msg = hosts_manager.get_task_status()["message"] or ("执行完成" if ok else "执行失败")
            logger.info(f"[任务通知] IP优选与Hosts更新 -> {msg}")
            send_task_notify("IP优选与Hosts更新", msg)
        background_tasks.add_task(combined_task)
        log_op("cfst.run")
        return {"message": "IP优选与Hosts更新任务已启动（严格串行）"}
    except Exception as e:
        logger.error(f"启动组合任务失败: {str(e)}")
        log_op("cfst.run", ok=False, error=str(e))
        raise HTTPException(status_code=500, detail=f"启动组合任务失败: {str(e)}")


# 手动更新所有Tracker为最佳IP
@router.post("/update-all-trackers")
async def update_all_trackers(
    ip: str,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """手动更新所有Tracker为指定IP"""
    try:
        # _update_all_trackers_ip 内部已写盘并同步内存副本，这里无需再同步
        hosts_manager._update_all_trackers_ip(ip)
        hosts_manager.update_hosts()
        log_op("tracker.set_ip_all", ip=ip)
        return {"message": f"已将所有Tracker的IP更新为 {ip}"}
    except Exception as e:
        logger.error(f"更新所有Tracker的IP失败: {str(e)}")
        log_op("tracker.set_ip_all", ok=False, ip=ip, error=str(e))
        raise HTTPException(status_code=500, detail=f"更新所有Tracker的IP失败: {str(e)}")


@router.post("/clear-and-update-hosts")
async def clear_and_update_hosts(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """清理项目分区并重新生成hosts内容（保留原有系统hosts未受影响）"""
    try:
        # 1. 仅移除PT-Accelerator分区，保留原有系统hosts
        hosts_manager.clear_project_sections()
        # 2. 后台更新hosts并通知
        def task():
            ok = hosts_manager.update_hosts()
            msg = hosts_manager.get_task_status()["message"] or ("更新完成" if ok else "更新失败")
            logger.info(f"[任务通知] 清空并更新Hosts -> {msg}")
            send_task_notify("清空并更新Hosts", msg)
        background_tasks.add_task(task)
        log_op("hosts.rebuild")
        return {"message": "已清理项目分区并启动更新任务（原有hosts内容已保留）"}
    except Exception as e:
        logger.error(f"清空并更新hosts失败: {str(e)}")
        log_op("hosts.rebuild", ok=False, error=str(e))
        raise HTTPException(status_code=500, detail=f"清空并更新hosts失败: {str(e)}")



# 保存系统hosts内容
@router.post("/save-hosts-content")
async def save_hosts_content(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    try:
        content = payload.get("content", "")
        if not isinstance(content, str):
            raise HTTPException(status_code=400, detail="无效的内容")
        # 写入统一由 hosts_manager 负责：剥离项目分区 + 原子写
        removed = hosts_manager.save_user_content(content)
        # 保存后触发一次后台更新，确保项目分区一致（非阻塞）
        background_tasks.add_task(hosts_manager.update_hosts)
        log_op("hosts.save_content", removed_sections=removed, size=len(content))
        return {"success": True, "message": "Hosts已保存，已启动后台更新", "removed_sections": removed}
    except HTTPException as e:
        log_op("hosts.save_content", ok=False, level=logging.WARNING, reason=e.detail)
        raise
    except Exception as e:
        logger.error(f"保存hosts失败: {str(e)}")
        log_op("hosts.save_content", ok=False, error=str(e))
        raise HTTPException(status_code=500, detail=f"保存hosts失败: {str(e)}")


