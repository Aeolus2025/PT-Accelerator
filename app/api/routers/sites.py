"""站点与 Hosts 管理接口：Cloudflare 白名单、Tracker、hosts 源、hosts 更新与清空重建。"""

import logging
import os
import re
from urllib.parse import urlparse
from typing import Any, Dict, List

import yaml
from pydantic import BaseModel
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from app.api.deps import CONFIG_PATH, get_file_config
from app.globals import get_hosts_manager
from app.services import domain_service
from app.services.hosts_manager import HostsManager
from app.services.task_notify import _send_task_notify
from app.utils.file_utils import atomic_write_text

logger = logging.getLogger(__name__)

router = APIRouter()

# 本模块内统一用这个名字读配置
get_config = get_file_config


# ===== Cloudflare白名单管理API =====

@router.get("/cloudflare-domains")
async def get_cloudflare_domains():
    config = get_config()
    domains = config.get("cloudflare_domains", [])
    return {"cloudflare_domains": domains}

@router.post("/cloudflare-domains")
async def add_cloudflare_domain(background_tasks: BackgroundTasks, domain: str = Query(..., description="要添加的Cloudflare域名")):
    config = get_config()
    domains = set(config.get("cloudflare_domains", []))
    domains.add(domain.strip().lower())
    config["cloudflare_domains"] = list(domains)
    atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
    hosts_manager = get_hosts_manager()
    hosts_manager.update_config(config)
    try:
        import app.main
        app.main.config = config
    except Exception:
        pass
    # 白名单变更后异步更新 hosts
    background_tasks.add_task(hosts_manager.update_hosts)
    return {"message": f"已添加 {domain} 到Cloudflare白名单", "cloudflare_domains": list(domains)}

@router.delete("/cloudflare-domains")
async def delete_cloudflare_domain(background_tasks: BackgroundTasks, domain: str = Query(..., description="要删除的Cloudflare域名")):
    config = get_config()
    domains = set(config.get("cloudflare_domains", []))
    domains.discard(domain.strip().lower())
    config["cloudflare_domains"] = list(domains)
    atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
    hosts_manager = get_hosts_manager()
    hosts_manager.update_config(config)
    try:
        import app.main
        app.main.config = config
    except Exception:
        pass
    # 白名单变更后异步更新 hosts
    background_tasks.add_task(hosts_manager.update_hosts)
    return {"message": f"已从Cloudflare白名单移除 {domain}", "cloudflare_domains": list(domains)}

# 修改添加tracker接口，支持force_cloudflare参数
@router.post("/trackers")
async def add_tracker(
    tracker: dict,
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager),
    force_cloudflare: bool = False
):
    try:
        domain = tracker.get("domain", "")
        if domain:
            domain = re.sub(r"^https?://", "", domain, flags=re.IGNORECASE)
            domain = domain.split("/")[0]
            tracker["domain"] = domain
        config = get_config()
        if "trackers" not in config:
            config["trackers"] = []
        for existing in config["trackers"]:
            if existing["domain"] == tracker["domain"]:
                raise HTTPException(status_code=400, detail="Tracker已存在")
        ip_set = set()
        for t in config["trackers"]:
            if t.get("enable") and t.get("ip"):
                ip_set.add(t["ip"])
        if len(ip_set) > 1:
            raise HTTPException(status_code=400, detail="检测到现有Tracker的IP不一致，请先统一所有Tracker的IP后再添加。")
        elif len(ip_set) == 1:
            default_ip = list(ip_set)[0]
        else:
            default_ip = hosts_manager.best_cloudflare_ip or "104.16.91.215"
        tracker["ip"] = default_ip
        config["trackers"].append(tracker)
        # force_cloudflare 为 True 时同时写入白名单
        if force_cloudflare:
            domains = set(config.get("cloudflare_domains", []))
            domains.add(domain.strip().lower())
            config["cloudflare_domains"] = list(domains)
        atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
        hosts_manager.update_config(config)
        # 统一异步触发hosts更新，避免接口阻塞
        background_tasks.add_task(hosts_manager.update_hosts)
        try:
            import app.main
            app.main.config = config
        except Exception:
            pass
        return {"message": "Tracker已添加，Hosts更新任务已在后台启动"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加Tracker失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"添加Tracker失败: {str(e)}")

@router.delete("/trackers/{domain}")
async def delete_tracker(
    domain: str,
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """删除Tracker"""
    try:
        # 更新配置
        config = get_config()
        if "trackers" not in config:
            raise HTTPException(status_code=404, detail="Tracker不存在")
        
        found = False
        config["trackers"] = [t for t in config["trackers"] if t["domain"] != domain]
        # 同步清理该域名的历史记录
        hosts_manager.remove_tracker_domain(domain)
        
        # 保存配置
        atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
        
        # 更新hosts_manager的配置
        hosts_manager.update_config(config)
        
        # 同步更新全局config对象，确保前端API获取到最新数据
        try:
            import app.main
            app.main.config = config
            logger.info(f"删除Tracker API已同步刷新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"删除Tracker API刷新全局config对象失败: {str(e)}")
        
        # 在后台更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        
        return {"message": "Tracker已删除，Hosts更新任务已在后台启动"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除Tracker失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除Tracker失败: {str(e)}")

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
        config = get_config()
        if "hosts_sources" not in config:
            config["hosts_sources"] = []
        for existing in config["hosts_sources"]:
            if existing["url"] == source["url"]:
                raise HTTPException(status_code=400, detail="hosts源已存在")
        config["hosts_sources"].append(source)
        atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
        
        # 更新hosts_manager的配置
        hosts_manager.update_config(config)
        
        # 同步更新全局config对象，确保前端API获取到最新数据
        try:
            import app.main
            app.main.config = config
            logger.info("添加hosts源API已同步刷新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"添加hosts源API刷新全局config对象失败: {str(e)}")
            
        # 异步更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        return {"message": "hosts源已添加，正在后台更新hosts"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加hosts源失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"添加hosts源失败: {str(e)}")

@router.delete("/hosts-sources")
async def delete_hosts_source(
    url: str,
    background_tasks: BackgroundTasks,  # 新增参数
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """删除hosts源"""
    try:
        config = get_config()
        if "hosts_sources" not in config:
            raise HTTPException(status_code=404, detail="hosts源不存在")
        config["hosts_sources"] = [s for s in config["hosts_sources"] if s["url"] != url]
        atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
            
        # 更新hosts_manager的配置
        hosts_manager.update_config(config)
        
        # 同步更新全局config对象，确保前端API获取到最新数据
        try:
            import app.main
            app.main.config = config
            logger.info("删除hosts源API已同步刷新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"删除hosts源API刷新全局config对象失败: {str(e)}")
            
        # 异步更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        return {"message": "hosts源已删除，正在后台更新hosts"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除hosts源失败: {str(e)}")
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
            status = hosts_manager.get_task_status() if hasattr(hosts_manager, 'get_task_status') else {}
            msg = status.get('message') if isinstance(status, dict) else ("更新完成" if ok else "更新失败")
            logger.info(f"[任务通知] 仅更新Hosts -> {msg}")
            _send_task_notify("仅更新Hosts", msg)
        background_tasks.add_task(task)
        return {"message": "hosts更新任务已启动"}
    except Exception as e:
        logger.error(f"更新hosts失败: {str(e)}")
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

# ===== 添加新的模型和API端点 =====

class DomainList(BaseModel):
    domains: List[str]

# 批量添加PT站点域名
@router.post("/batch-add-domains")
async def batch_add_domains(
    request: Request,
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """批量添加域名"""
    try:
        # 获取请求数据并清洗域名（去协议前缀、切路径、去空行）
        data = await request.json()
        domains = domain_service.clean_domains(data.get("domains", ""))
        
        if not domains:
            return {"status": "warning", "message": "没有提供有效的域名"}
        
        # 读取当前配置
        config = get_config()
        if "trackers" not in config:
            config["trackers"] = []
            
        # 检查所有tracker的IP是否一致
        ok, msg = domain_service.check_ip_consistency(config["trackers"])
        if not ok:
            return {"status": "error", "message": msg}

        # 获取默认IP：沿用现有 IP，否则使用优选 IP 或默认值
        default_ip = domain_service.resolve_default_ip(
            config["trackers"], hosts_manager.best_cloudflare_ip or "104.16.91.215"
        )

        # 批量添加域名：已存在或本次重复的跳过
        existing = {t.get("domain") for t in config["trackers"]}
        new_trackers, added, skipped = domain_service.build_trackers(
            domains, existing, default_ip
        )
        config["trackers"].extend(new_trackers)

        # 保存配置
        atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
            
        # 更新hosts_manager的配置
        hosts_manager.update_config(config)
        
        # 同步更新全局config对象，确保前端API获取到最新数据
        try:
            import app.main
            app.main.config = config
            logger.info("批量添加域名API已同步刷新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"批量添加域名API刷新全局config对象失败: {str(e)}")
            
        # 后台更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        
        # 构建响应消息
        message = f"批量添加完成：成功添加 {len(added)} 个域名，跳过 {len(skipped)} 个已存在的域名"
        details = {
            "added": added,
            "skipped": skipped
        }
        
        return {
            "status": "success", 
            "message": message,
            "details": details
        }
    except Exception as e:
        logger.error(f"批量添加域名失败: {str(e)}")
        return {"status": "error", "message": f"批量添加域名失败: {str(e)}"}

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
            status = hosts_manager.get_task_status() if hasattr(hosts_manager, 'get_task_status') else {}
            msg = status.get('message') if isinstance(status, dict) else ("执行完成" if ok else "执行失败")
            logger.info(f"[任务通知] IP优选与Hosts更新 -> {msg}")
            _send_task_notify("IP优选与Hosts更新", msg)
        background_tasks.add_task(combined_task)
        return {"message": "IP优选与Hosts更新任务已启动（严格串行）"}
    except Exception as e:
        logger.error(f"启动组合任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动组合任务失败: {str(e)}")

# 手动更新所有Tracker为最佳IP
@router.post("/update-all-trackers")
async def update_all_trackers(
    ip: str,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """手动更新所有Tracker为指定IP"""
    try:
        hosts_manager._update_all_trackers_ip(ip)
        hosts_manager.update_hosts()
        
        # 确保全局config对象同步更新
        try:
            import app.main
            app.main.config = hosts_manager.config
            logger.info("API端点已同步刷新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"API端点刷新全局config对象失败: {str(e)}")
            
        return {"message": f"已将所有Tracker的IP更新为 {ip}"}
    except Exception as e:
        logger.error(f"更新所有Tracker的IP失败: {str(e)}")
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
            status = hosts_manager.get_task_status() if hasattr(hosts_manager, 'get_task_status') else {}
            msg = status.get('message') if isinstance(status, dict) else ("更新完成" if ok else "更新失败")
            logger.info(f"[任务通知] 清空并更新Hosts -> {msg}")
            _send_task_notify("清空并更新Hosts", msg)
        background_tasks.add_task(task)
        return {"message": "已清理项目分区并启动更新任务（原有hosts内容已保留）"}
    except Exception as e:
        logger.error(f"清空并更新hosts失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清空并更新hosts失败: {str(e)}")

@router.post("/clear-all-trackers")
async def clear_all_trackers(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """清空所有tracker并同步更新hosts"""
    try:
        config = get_config()
        config["trackers"] = []
        atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))
        hosts_manager.update_config(config)
        try:
            import app.main
            app.main.config = config
        except Exception:
            pass
        background_tasks.add_task(hosts_manager.update_hosts)
        return {"message": "已清空所有tracker并同步更新hosts"}
    except Exception as e:
        logger.error(f"清空所有tracker失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清空所有tracker失败: {str(e)}")


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
        hosts_path = hosts_manager._get_hosts_path()
        with open(hosts_path, 'w') as f:
            f.write(content)
        # 保存后触发一次后台更新，确保项目分区一致（非阻塞）
        background_tasks.add_task(hosts_manager.update_hosts)
        return {"success": True, "message": "Hosts已保存，已启动后台更新"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存hosts失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存hosts失败: {str(e)}")
