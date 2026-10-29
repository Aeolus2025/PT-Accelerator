"""任务结果通知：把任务执行结果按已启用的渠道发送出去。"""

import copy
import logging
from typing import Any, Dict

from app.core import config_store
from app.utils import notify as notify_module
from app.utils import notify_channel
from app.utils import notify_template
from app.utils.oplog import Timer

logger = logging.getLogger(__name__)


def send_task_notify(title: str, content: str):
    try:
        cfg = config_store.read() or {}
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
        sent = 0
        failed = []
        timer = Timer()
        # send 内部为每个渠道各开线程，异常在网络层被吞掉，这里只能统计"已尝试"的渠道数
        for flat in valid:
            try:
                notify_module.send(pretty_title, pretty_content, ignore_default_config=True, **flat)
                sent += 1
            except Exception:
                failed.append(flat.get("name") or flat.get("type") or "unknown")
                logger.exception("[NOTIFY] 渠道发送失败")
        logger.info(
            "[NOTIFY] task_send 渠道数=%s 已发送=%s 失败数=%s 失败渠道=%s 耗时=%s",
            len(valid), sent, len(failed), ",".join(failed) or "-", int(timer),
        )
    except Exception:
        logger.exception("[NOTIFY] 任务通知发送失败")
