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
        # CRON表达式校验（只在本次真的提交 cloudflare 节时校验）
        if "cloudflare" in config_data:
            cron_expr = (config_data.get("cloudflare") or {}).get("cron", "0 0 * * *")
            if not croniter.is_valid(cron_expr):
                raise HTTPException(status_code=400, detail="CRON表达式无效，请检查格式")

        # 只按节覆盖请求里带来的键，其余节保留锁内读到的最新值
        def _merge(current):
            for key, value in (config_data or {}).items():
                current[key] = value

        config_data = config_store.mutate(_merge)

        # 更新服务配置
        hosts_manager.reload_whitelist()
        cloudflare_service.update_config(config_data)
        scheduler_service.update_config(config_data)

        return {"message": "配置已更新"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")
