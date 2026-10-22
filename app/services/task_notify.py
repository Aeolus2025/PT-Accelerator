"""任务结果通知：把任务执行结果按已启用的渠道发送出去。"""

import copy
import logging
from typing import Any, Dict

from app.api.deps import get_file_config
from app.utils import notify as notify_module
from app.utils import notify_channel
from app.utils import notify_template

logger = logging.getLogger(__name__)


def send_task_notify(title: str, content: str):
    try:
        cfg = get_file_config() or {}
        notify_cfg = copy.deepcopy(cfg.get("notify", {}))

        # 标题与内容交给模板渲染，未配置模板时走内置默认格式
        pretty_title, pretty_content = notify_template.render(
            title, content, notify_cfg.get("template") or {}
        )
        channels = notify_cfg.get("channels", {}) or {}


        # 收集有效渠道
        payloads: list[Dict[str, Any]] = []
        if isinstance(channels, dict):
            for _, ch_conf in channels.items():
                if isinstance(ch_conf, dict) and ch_conf.get("enable"):
                    flat_config = notify_channel.flatten(ch_conf)
                    # 添加渠道启用状态到配置中，保持原有的启用状态
                    channel_type = ch_conf.get("type", "").lower()
                    if channel_type:
                        # 只有当渠道在配置中明确启用时，才设置ENABLE_标志
                        flat_config[f"ENABLE_{channel_type.upper()}"] = ch_conf.get("enable", False)
                    payloads.append(flat_config)

        minimal_keys_sets = [
            ("WEBHOOK_URL", "WEBHOOK_METHOD"),
            ("QYWX_KEY",),
            ("TG_BOT_TOKEN", "TG_USER_ID"),
            ("SMTP_SERVER", "SMTP_EMAIL", "SMTP_PASSWORD"),
            ("BARK_PUSH",),
            ("WXPUSHER_APP_TOKEN",),
            ("GOTIFY_URL", "GOTIFY_TOKEN"),
            ("MEDIASABER_HOST", "MEDIASABER_APIKEY"),
        ]
        valid = []
        for flat in payloads:
            for keys in minimal_keys_sets:
                if all(flat.get(k) for k in keys):
                    valid.append(flat)
                    break
        # 为每个有效渠道单独发送通知，使用 ignore_default_config=True 避免配置污染
        for flat in valid:
            notify_module.send(pretty_title, pretty_content, ignore_default_config=True, **flat)
    except Exception as e:
        logger.error(f"发送任务结果通知失败: {e}", exc_info=True)
