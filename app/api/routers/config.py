"""配置读写接口。"""

import logging
from typing import Any, Dict

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_file_config
from app.globals import get_hosts_manager, get_cloudflare_service, get_scheduler_service
from app.services.cfst import CloudflareSpeedTestService
from app.services.hosts_manager import HostsManager
from app.services.scheduler import SchedulerService
from app.core import config_store
from app.utils.oplog import log_op

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/config")
async def read_config():
    """每次都从文件读取最新配置，防止内存与文件不同步导致tracker状态异常。

    统一走 get_file_config，与其余 router 共用同一套编码回退（utf-8 / gbk / gb18030）。
    此前这里直接以 utf-8 打开，GBK 保存的配置会抛 UnicodeDecodeError 导致 500。
    """
    config = get_file_config()

    # auth.secret_key 是 session 的签名密钥，前端从不使用它。
    # 一旦通过接口下发，任何能访问本服务的人都能用它离线伪造管理员会话。
    auth_section = config.get("auth")
    if isinstance(auth_section, dict):
        auth_section.pop("secret_key", None)

    return config


def _diff_keys(before, request_config):
    """真正发生变化的键；值没变的保存不算变更。"""
    changed = []
    for section, value in request_config.items():
        if not isinstance(value, dict):
            if before.get(section) != value:
                changed.append(section)
            continue
        old = before.get(section) or {}
        for key, new_value in value.items():
            if old.get(key) != new_value:
                changed.append(f"{section}.{key}")
    return sorted(changed)


def _log_config_change(before, request_config, changed_sections):
    """定时任务的开关与表达式单独记，其余配置记一条汇总。

    开关只在真的翻转时记，避免每次点保存都写一条「启用定时任务」。
    """
    new_cf = request_config.get("cloudflare")
    if isinstance(new_cf, dict):
        old_cf = before.get("cloudflare") or {}
        enable_before = bool(old_cf.get("enable", True))
        enable_after = bool(new_cf.get("enable", enable_before))
        cron_before = old_cf.get("cron")
        cron_after = new_cf.get("cron", cron_before)

        if enable_before != enable_after:
            fields = {"定时": cron_after or "-"}
            if cron_before != cron_after:
                fields["原定时"] = cron_before
            log_op("启用定时任务" if enable_after else "关闭定时任务", **fields)
            return

        if cron_before != cron_after:
            log_op("调整定时任务", 定时=cron_after, 原定时=cron_before)
            return

    changed = _diff_keys(before, request_config)
    log_op("更新配置", 变更项=",".join(changed) or "无")


@router.post("/config")
async def update_config(
    config_data: Dict[str, Any],
    hosts_manager: HostsManager = Depends(get_hosts_manager),
    cloudflare_service: CloudflareSpeedTestService = Depends(get_cloudflare_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service),
):
    """更新配置。

    只合并请求体里出现的顶层节，未提交的节保持文件中的最新值，
    这样多标签页各自保存自己那一页时不会互相覆盖。
    """
    try:
        request_config = config_data or {}

        # CRON表达式校验（只在本次真的提交 cloudflare 节时校验）
        if "cloudflare" in request_config:
            cron_expr = (request_config.get("cloudflare") or {}).get("cron", "0 0 * * *")
            if not croniter.is_valid(cron_expr):
                raise HTTPException(status_code=400, detail="CRON表达式无效，请检查格式")

        # 提交的节名要先记下来：mutate 之后 config_data 会变成完整配置
        changed_sections = sorted(request_config)

        # 保存前的值，用来判断开关是打开还是关闭
        before: Dict[str, Any] = {}

        # 只按节覆盖请求里带来的键，其余节保留锁内读到的最新值
        def _merge(current):
            before.update(current)
            for key, value in request_config.items():
                current[key] = value

        merged = config_store.mutate(_merge)

        # 更新服务配置
        hosts_manager.reload_whitelist()
        cloudflare_service.update_config(merged)
        scheduler_service.update_config(merged)

        _log_config_change(before, request_config, changed_sections)
        return {"message": "配置已更新"}
    except HTTPException as e:
        log_op("更新配置", ok=False, level=logging.WARNING, 原因=e.detail)
        raise
    except Exception as e:
        logger.exception("[CONFIG] 更新配置失败: %s", str(e))
        log_op("更新配置", ok=False, 错误=str(e))
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")
