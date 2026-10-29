"""Tracker 接口：添加、删除、批量添加、清空。"""

import logging
import re

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from app.models import BatchAddDomainsRequest
from app.core import config_store
from app.core.constants import DEFAULT_CLOUDFLARE_IP
from app.globals import get_hosts_manager
from app.services import domain_service
from app.services.hosts_manager import HostsManager
from app.utils.oplog import log_op

logger = logging.getLogger(__name__)

router = APIRouter()



# 修改添加tracker接口，支持force_cloudflare参数
@router.post("/trackers")
async def add_tracker(
    tracker: dict,
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager),
    force_cloudflare: bool = False
):
    try:
        domain = domain_service.clean_domain(tracker.get("domain", ""))
        tracker["domain"] = domain
        if not domain_service.is_valid_domain(domain):
            raise HTTPException(status_code=400, detail=f"域名格式不正确：{domain or '(空)'}")
        def _add(current):
            trackers = current.setdefault("trackers", [])
            if any(existing["domain"] == tracker["domain"] for existing in trackers):
                raise HTTPException(status_code=400, detail="Tracker已存在")
            ip_set = {t["ip"] for t in trackers if t.get("enable") and t.get("ip")}
            if len(ip_set) > 1:
                raise HTTPException(status_code=400, detail="检测到现有Tracker的IP不一致，请先统一所有Tracker的IP后再添加。")
            tracker["ip"] = next(iter(ip_set)) if ip_set else (hosts_manager.best_cloudflare_ip or DEFAULT_CLOUDFLARE_IP)
            trackers.append(tracker)
            # force_cloudflare 为 True 时同时写入白名单
            if force_cloudflare:
                domains = set(current.get("cloudflare_domains", []))
                domains.add(domain.strip().lower())
                current["cloudflare_domains"] = list(domains)

        # 查重、IP一致性校验、追加都在锁内，避免并发两次添加都读到空列表
        config_store.mutate(_add)
        hosts_manager.reload_whitelist()
        # 统一异步触发hosts更新，避免接口阻塞
        background_tasks.add_task(hosts_manager.update_hosts)
        log_op("添加Tracker", 目标=domain, IP=tracker.get("ip"),
               强制CF=force_cloudflare)
        return {"message": "Tracker已添加，Hosts更新任务已在后台启动"}
    except HTTPException as e:
        # 业务性拒绝（已存在、IP 不一致）记 WARNING
        log_op("添加Tracker", 目标=tracker.get("domain", ""), ok=False,
               level=logging.WARNING, 原因=e.detail)
        raise
    except Exception as e:
        logger.exception("[HOSTS] 添加Tracker失败: %s", str(e))
        log_op("添加Tracker", 目标=tracker.get("domain", ""), ok=False, 错误=str(e))
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
        def _remove(current):
            trackers = current.get("trackers")
            if not trackers:
                raise HTTPException(status_code=404, detail="Tracker不存在")
            current["trackers"] = [t for t in trackers if t["domain"] != domain]

        config_store.mutate(_remove)
        # 同步清理该域名的历史记录
        hosts_manager.remove_tracker_domain(domain)
        
        # 更新hosts_manager的配置
        hosts_manager.reload_whitelist()
        
        
        # 在后台更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)

        log_op("删除Tracker", 目标=domain)
        return {"message": "Tracker已删除，Hosts更新任务已在后台启动"}
    except HTTPException as e:
        log_op("删除Tracker", 目标=domain, ok=False, level=logging.WARNING, 原因=e.detail)
        raise
    except Exception as e:
        logger.exception("[HOSTS] 删除Tracker失败: %s", str(e))
        log_op("删除Tracker", 目标=domain, ok=False, 错误=str(e))
        raise HTTPException(status_code=500, detail=f"删除Tracker失败: {str(e)}")


# 批量添加PT站点域名
@router.post("/batch-add-domains")
async def batch_add_domains(
    payload: BatchAddDomainsRequest,
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """批量添加域名"""
    try:
        # 清洗域名（去协议前缀、切路径、去空行）
        domains = domain_service.clean_domains(payload.domains)
        
        if not domains:
            return {"status": "warning", "message": "没有提供有效的域名"}

        # 格式不对的先挡掉，否则后台探测要等 60 秒才判定失败
        invalid = [d for d in domains if not domain_service.is_valid_domain(d)]
        domains = [d for d in domains if domain_service.is_valid_domain(d)]
        if not domains:
            log_op("批量添加Tracker", ok=False, level=logging.WARNING,
                   请求数=len(invalid), 原因="域名格式全部无效")
            return {
                "status": "warning",
                "message": f"没有有效的域名，格式不正确：{','.join(invalid[:5])}",
            }
        
        outcome = {}

        def _batch_add(current):
            trackers = current.setdefault("trackers", [])
            # 检查所有tracker的IP是否一致
            ok, msg = domain_service.check_ip_consistency(trackers)
            if not ok:
                outcome["error"] = msg
                return
            # 获取默认IP：沿用现有 IP，否则使用优选 IP 或默认值
            default_ip = domain_service.resolve_default_ip(
                trackers, hosts_manager.best_cloudflare_ip or DEFAULT_CLOUDFLARE_IP
            )
            # 批量添加域名：已存在或本次重复的跳过
            existing = {t.get("domain") for t in trackers}
            new_trackers, added, skipped = domain_service.build_trackers(
                domains, existing, default_ip
            )
            trackers.extend(new_trackers)
            outcome["added"] = added
            outcome["skipped"] = skipped

        config_store.mutate(_batch_add)
        if outcome.get("error"):
            log_op("批量添加Tracker", ok=False, level=logging.WARNING,
                   请求数=len(domains), 原因=outcome["error"])
            return {"status": "error", "message": outcome["error"]}
        added, skipped = outcome["added"], outcome["skipped"]
            
        # 更新hosts_manager的配置
        hosts_manager.reload_whitelist()
        
            
        # 后台更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        
        # 构建响应消息
        message = f"批量添加完成：成功添加 {len(added)} 个域名，跳过 {len(skipped)} 个已存在的域名"
        if invalid:
            message += f"；{len(invalid)} 个域名格式不正确已忽略：{','.join(invalid[:5])}"
        details = {
            "added": added,
            "skipped": skipped
        }
        
        log_op("批量添加Tracker", 请求数=len(domains) + len(invalid),
               新增=len(added), 跳过=len(skipped), 格式无效=len(invalid))
        return {
            "status": "success", 
            "message": message,
            "details": details
        }
    except Exception as e:
        logger.exception("[HOSTS] 批量添加域名失败: %s", str(e))
        log_op("批量添加Tracker", ok=False, 错误=str(e))
        return {"status": "error", "message": f"批量添加域名失败: {str(e)}"}


@router.post("/clear-all-trackers")
async def clear_all_trackers(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """清空所有tracker并同步更新hosts"""
    try:
        config_store.mutate(lambda current: current.__setitem__("trackers", []))
        hosts_manager.reload_whitelist()
        background_tasks.add_task(hosts_manager.update_hosts)
        log_op("清空Tracker")
        return {"message": "已清空所有tracker并同步更新hosts"}
    except Exception as e:
        logger.exception("[HOSTS] 清空所有tracker失败: %s", str(e))
        log_op("清空Tracker", ok=False, 错误=str(e))
        raise HTTPException(status_code=500, detail=f"清空所有tracker失败: {str(e)}")


