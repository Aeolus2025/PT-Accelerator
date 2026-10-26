"""Cloudflare 白名单接口。"""

import logging

from fastapi import APIRouter, BackgroundTasks, Query

from app.api.deps import get_file_config
from app.core import config_store
from app.globals import get_hosts_manager
from app.utils.oplog import log_op

logger = logging.getLogger(__name__)

router = APIRouter()



# 本模块内统一用这个名字读配置


# ===== Cloudflare白名单管理API =====

@router.get("/cloudflare-domains")
async def get_cloudflare_domains():
    config = get_file_config()
    domains = config.get("cloudflare_domains", [])
    return {"cloudflare_domains": domains}


@router.post("/cloudflare-domains")
async def add_cloudflare_domain(background_tasks: BackgroundTasks, domain: str = Query(..., description="要添加的Cloudflare域名")):
    def _add(current):
        domains = set(current.get("cloudflare_domains", []))
        domains.add(domain.strip().lower())
        current["cloudflare_domains"] = sorted(domains)

    config = config_store.mutate(_add)
    domains = config["cloudflare_domains"]
    hosts_manager = get_hosts_manager()
    hosts_manager.reload_whitelist()
    # 白名单变更后异步更新 hosts
    background_tasks.add_task(hosts_manager.update_hosts)
    log_op("添加白名单", 目标=domain, 合计=len(domains))
    return {"message": f"已添加 {domain} 到Cloudflare白名单", "cloudflare_domains": list(domains)}


@router.delete("/cloudflare-domains")
async def delete_cloudflare_domain(background_tasks: BackgroundTasks, domain: str = Query(..., description="要删除的Cloudflare域名")):
    def _remove(current):
        domains = set(current.get("cloudflare_domains", []))
        domains.discard(domain.strip().lower())
        current["cloudflare_domains"] = sorted(domains)

    config = config_store.mutate(_remove)
    domains = config["cloudflare_domains"]
    hosts_manager = get_hosts_manager()
    hosts_manager.reload_whitelist()
    # 白名单变更后异步更新 hosts
    background_tasks.add_task(hosts_manager.update_hosts)
    log_op("移除白名单", 目标=domain, 合计=len(domains))
    return {"message": f"已从Cloudflare白名单移除 {domain}", "cloudflare_domains": list(domains)}


