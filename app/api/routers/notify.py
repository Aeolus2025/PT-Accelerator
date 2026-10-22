"""通知配置接口：渠道增删改、测试发送、通知模板预览。"""

import copy
import logging
from typing import Any, Dict

import yaml
from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from app.api.deps import CONFIG_PATH, get_file_config
from app.utils import notify as notify_module
from app.utils import notify_channel
from app.utils import notify_template
from app.utils.file_utils import atomic_write_text

logger = logging.getLogger(__name__)

router = APIRouter()

get_config = get_file_config

# ===== 通知配置API =====

@router.get("/notify/config")
async def get_notify_config():
    """获取通知配置（从文件读取最新config）"""
    config = get_config()
    notify_cfg = config.get("notify", {})
    return {"success": True, "notify": notify_cfg}


@router.post("/notify/config")
async def save_notify_config(payload: Dict[str, Any]):
    """保存通知配置到config.yaml，并保持其余配置不变"""
    try:
        config = get_config()
        new_notify = payload.get("notify", {})
        if not isinstance(new_notify, dict):
            return {"success": False, "message": "无效的通知配置"}

        # 更新配置
        config["notify"] = new_notify

        atomic_write_text(CONFIG_PATH, yaml.dump(config, default_flow_style=False, allow_unicode=True))

        # 尝试同步到全局config，便于前端刷新
        try:
            import app.main
            app.main.config = config
        except Exception:
            pass

        logger.info("通知配置已保存")
        return {"success": True, "message": "通知配置已保存"}
    except Exception as e:
        logger.error(f"保存通知配置失败: {str(e)}")
        return {"success": False, "message": f"保存通知配置失败: {str(e)}"}


@router.post("/notify/test")
async def test_notify(payload: Dict[str, Any]):
    """测试发送通知：可携带title/content与临时覆盖的channels"""
    try:
        title = payload.get("title") or "通知测试"
        content = payload.get("content") or "这是一条测试消息"
        channels_override = payload.get("channels") or {}

        # 读取配置
        config = get_config()
        notify_cfg = copy.deepcopy(config.get("notify", {}))
        enable = notify_cfg.get("enable", True)
        if not enable:
            return {"success": False, "message": "通知功能未启用"}

        # 与任务通知共用同一套模板，保证测试所见即实际发送
        title, content = notify_template.render(
            title, content, notify_cfg.get("template") or {}
        )

        # 逐渠道发送：按每个启用渠道构建独立的kwargs
        channels = notify_cfg.get("channels", {}) or {}
        per_channel_payloads: list[Dict[str, Any]] = []


        # 先收集已保存且启用的渠道（若没有前端嵌套覆盖，则使用；若有嵌套覆盖，仅使用覆盖）
        use_saved_channels = True

        # 应用前端临时覆盖：
        # - 若为嵌套结构（按渠道名），则替换/追加对应渠道
        # - 若为顶层键集合，则作为“单次临时渠道”追加一次发送
        if isinstance(channels_override, dict) and channels_override:
            # 只要前端携带了覆盖对象，就完全忽略已保存的其它渠道
            use_saved_channels = False
            contains_nested = any(isinstance(val, dict) for val in channels_override.values())
            if contains_nested:
                for _, ch_conf in channels_override.items():
                    if isinstance(ch_conf, dict) and ch_conf.get("enable", True):
                        flat_config = notify_channel.flatten(ch_conf)
                        # 添加渠道启用状态到配置中，保持原有的启用状态
                        channel_type = ch_conf.get("type", "").lower()
                        if channel_type:
                            # 只有当渠道在配置中明确启用时，才设置ENABLE_标志
                            flat_config[f"ENABLE_{channel_type.upper()}"] = ch_conf.get("enable", False)
                        per_channel_payloads.append(flat_config)
            else:
                # 顶层键集合 -> 直接作为一次独立发送
                tmp_flat = dict(channels_override)
                per_channel_payloads.append(tmp_flat)

        if use_saved_channels and isinstance(channels, dict):
            for _, ch_conf in channels.items():
                if isinstance(ch_conf, dict) and ch_conf.get("enable"):
                    flat_config = notify_channel.flatten(ch_conf)
                    # 添加渠道启用状态到配置中，保持原有的启用状态
                    channel_type = ch_conf.get("type", "").lower()
                    if channel_type:
                        # 只有当渠道在配置中明确启用时，才设置ENABLE_标志
                        flat_config[f"ENABLE_{channel_type.upper()}"] = ch_conf.get("enable", False)
                    per_channel_payloads.append(flat_config)

        # 过滤无效渠道（最小必需字段校验）
        valid_payloads: list[Dict[str, Any]] = []
        minimal_keys_sets = [
            ("WEBHOOK_URL", "WEBHOOK_METHOD"),           # 自定义Webhook
            ("QYWX_KEY",),                               # 企业微信Bot
            ("QYWX_AM",),                                # 企业微信App
            ("TG_BOT_TOKEN", "TG_USER_ID"),             # Telegram
            ("SMTP_SERVER", "SMTP_EMAIL", "SMTP_PASSWORD"), # 邮件
            ("BARK_PUSH",),                                # Bark
            ("PUSH_KEY",),                               # Server酱
            ("IGOT_PUSH_KEY",),                          # iGot
            ("FSKEY",),                                  # 飞书
            ("DD_BOT_TOKEN", "DD_BOT_SECRET"),          # 钉钉
            ("CHAT_URL", "CHAT_TOKEN"),                 # Synology Chat
            ("MEDIASABER_HOST", "MEDIASABER_APIKEY"),   # Media Saber
        ]
        for flat in per_channel_payloads:
            for keys in minimal_keys_sets:
                if all(flat.get(k) for k in keys):
                    valid_payloads.append(flat)
                    break

        if not valid_payloads:
            return {"success": False, "message": "未检测到可用的通知渠道，请检查渠道是否启用且配置完整"}

        # 跳过标题列表
        skip_titles = notify_cfg.get("skip_titles", []) or []
        if title in skip_titles:
            return {"success": True, "message": "标题在跳过列表中，未发送"}

        # 分渠道依次发送（每次send只带该渠道相关字段）
        # 发送涉及外部请求与线程 join，放入线程池避免阻塞事件循环
        for flat in valid_payloads:
            # 测试发送时仅使用本渠道配置
            await run_in_threadpool(
                notify_module.send, title, content, True, **flat
            )
        return {"success": True, "message": "测试通知请求已发出，请检查渠道接收情况"}
    except Exception as e:
        logger.error(f"测试通知发送失败: {str(e)}", exc_info=True)
        return {"success": False, "message": f"测试通知失败: {str(e)}"}


@router.post("/notify/template/preview")
async def preview_notify_template(payload: Dict[str, Any]):
    """用样例数据渲染模板，供前端实时预览。不写配置、不发通知。"""
    try:
        title_tpl = str(payload.get("title") or "")
        content_tpl = str(payload.get("content") or "")
        result = notify_template.preview(title_tpl, content_tpl)
        return {"success": True, **result}
    except Exception as e:
        logger.error(f"模板预览失败: {e}")
        return {"success": False, "message": str(e)}
