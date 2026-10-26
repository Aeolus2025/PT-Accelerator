"""认证配置接口（启用/禁用、用户名、密码）。"""

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status

from app.api.deps import get_file_config
from app.core.constants import CONFIG_PATH
from app.core.locking import config_write_lock
from app.auth import get_current_user
from app.auth import generate_initial_password, get_password_hash, verify_password
from app.models import User
from app.core import config_store
from app.utils.oplog import log_op

logger = logging.getLogger(__name__)

router = APIRouter()


# 更新认证配置
@router.post("/auth/config", dependencies=[Depends(get_current_user)])
async def update_auth_config(
    request: Request,
    enable_auth: bool = Form(None),
    username: str = Form(None),
    current_password: str = Form(None),
    new_password: str = Form(None),
    confirm_password: str = Form(None),
    current_user: User = Depends(get_current_user)
):
    """更新认证配置，包括启用/禁用、用户名和密码"""
    # 整段「读配置 → 改认证字段 → 写回」放在跨进程锁内，避免与 startup_event 的
    # 密码生成、或其他 worker 的并发保存互相覆盖配置。
    with config_write_lock():
        return await _update_auth_config_locked(
            request=request,
            enable_auth=enable_auth,
            username=username,
            current_password=current_password,
            new_password=new_password,
            confirm_password=confirm_password,
            current_user=current_user,
        )


async def _update_auth_config_locked(
    request: Request,
    enable_auth: bool = None,
    username: str = None,
    current_password: str = None,
    new_password: str = None,
    confirm_password: str = None,
    current_user: User = None
):
    current_config = get_file_config()
    
    if current_config.get("auth", {}).get("enable") and (not current_user or current_user.username == "guest"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改认证配置")

    auth_settings = current_config.get("auth", {}).copy()
    config_changed = False

    if enable_auth is not None and enable_auth != auth_settings.get("enable"):
        auth_settings["enable"] = enable_auth
        config_changed = True
        logger.info("[AUTH] 登录认证已 %s", '启用' if enable_auth else '禁用')

    if username and username != auth_settings.get("username"):
        auth_settings["username"] = username
        config_changed = True
        logger.info("[AUTH] 登录用户名已修改为: %s", username)

    if new_password:
        # 验证新密码长度
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="新密码长度至少需要8位字符")
        
        # 检查新密码与确认密码是否匹配
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="新密码与确认密码不匹配")
        
        if not current_password:
            # 如果没有提供当前密码，检查是否允许这样做
            if not auth_settings.get("password_hash") or not auth_settings.get("enable"):
                # 首次设置密码或认证被禁用时可以不需要当前密码
                auth_settings["password_hash"] = get_password_hash(new_password)
                config_changed = True
                logger.info("[AUTH] 登录密码已设置/更新。")
            else:
                raise HTTPException(status_code=400, detail="修改密码需要提供当前密码。如果您忘记了当前密码，请联系管理员。")
        else:
            # 验证当前密码
            if not auth_settings.get("password_hash"):
                raise HTTPException(status_code=400, detail="当前系统中没有设置密码，请清空当前密码字段后重试")
            elif not verify_password(current_password, auth_settings.get("password_hash", "")):
                raise HTTPException(status_code=400, detail="当前密码错误，请检查并重新输入")
            else:
                # 当前密码正确，更新为新密码
                auth_settings["password_hash"] = get_password_hash(new_password)
                config_changed = True
                logger.info("[AUTH] 登录密码已修改") 
                # 密码修改成功，使当前会话失效，强制重新登录
                request.session.pop("user", None) 

    # 启用认证但从未设置过密码：当场生成初始密码并打印到日志（原实现只在应用启动时生成，
    # 导致"启用后必须重启才能拿到密码"）。与 app/main.py 的启动兜底逻辑保持一致。
    if auth_settings.get("enable") and not auth_settings.get("password_hash"):
        generated_password = generate_initial_password(auth_settings.get("username", "admin"))
        auth_settings["password_hash"] = get_password_hash(generated_password)
        config_changed = True

    if config_changed:
        current_config["auth"] = auth_settings
        try:
            # 外层已持有 config_write_lock，这里直接写，不要重复取锁
            config_store.write(CONFIG_PATH, current_config)
            
            # 重新加载全局配置，确保认证配置变更立即生效
            from app.auth import reload_global_config
            if reload_global_config():
                logger.info("[AUTH] 全局配置已重新加载，认证配置变更立即生效")
            else:
                logger.warning("[AUTH] 全局配置重新加载失败，部分功能可能需要重启才能生效")
            
            # 重要：如果认证相关配置发生变化，清除当前session，强制重新登录
            # 这确保新的认证配置能够立即生效
            request.session.clear()
            
            message = "认证配置已更新。"
            # 根据具体更改调整消息，并处理会话
            if enable_auth is not None and not auth_settings.get("enable"):
                message += " 登录认证已禁用，您已自动登出。"
            elif new_password:
                 message += " 密码已更改，您已自动登出，请使用新密码重新登录。"
            elif username and username != current_user.username:
                 message += " 用户名已更改，您已自动登出，请重新登录。"
            else:
                message += " 为确保配置立即生效，您已自动登出，请重新登录。"
            
            log_op("更新认证", 目标=auth_settings.get("username"),
                   enabled=auth_settings.get("enable"),
                   password_changed=bool(new_password))
            return {"message": message}
        except Exception as e:
            logger.exception("[AUTH] 更新认证配置失败: %s", str(e))
            log_op("更新认证", ok=False, 错误=str(e))
            raise HTTPException(status_code=500, detail=f"更新认证配置失败: {str(e)}")

    log_op("更新认证", 目标=auth_settings.get("username"), 变更项=False)
    return {"message": "未检测到配置更改"}

