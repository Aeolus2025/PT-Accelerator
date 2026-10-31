"""优选参数接口。

参数本身是配置的一部分，读写走 /api/config 的 cfst 节；这里只提供命令行预览，
把当前参数拼成等价的 cfst 命令，方便用户手工复现和排错。
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from app.services import cfst_params

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/cfst/preview")
async def preview_cfst_command(payload: Dict[str, Any]):
    """返回等效命令行、参数列表与预计超时。

    非法取值在这里只做回退并返回 warnings，不抛 400 —— 预览是只读的，
    保存时才会由 /api/config 严格校验。
    """
    section = (payload or {}).get("cfst")
    if section is not None and not isinstance(section, dict):
        raise HTTPException(status_code=400, detail="优选参数格式错误：cfst 必须是键值对象")

    params, warns = cfst_params.resolve(section or {})
    return {
        "command": cfst_params.command_preview(params),
        "args": cfst_params.build_args(params),
        "timeout": cfst_params.timeout_seconds(params),
        "warnings": warns,
    }
