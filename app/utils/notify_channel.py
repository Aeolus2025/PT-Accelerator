"""通知渠道配置展开：按渠道类型过滤配置键，避免一个渠道触发多种通知。

某些渠道的配置文件里可能残留其他类型的键（手工编辑 config.yaml 时容易发生），
不过滤会导致 add_notify_function() 误判并触发多个渠道。
"""
from typing import Any, Dict

# 各渠道类型需要的配置键。未列出的类型保留全部键（兼容自定义渠道）
CHANNEL_KEY_MAP = {
    "webhook": [
        "WEBHOOK_URL",
        "WEBHOOK_METHOD",
        "WEBHOOK_BODY",
        "WEBHOOK_HEADERS",
        "WEBHOOK_CONTENT_TYPE",
    ],
    "telegram": [
        "TG_BOT_TOKEN",
        "TG_USER_ID",
        "TG_API_HOST",
        "TG_PROXY_AUTH",
        "TG_PROXY_HOST",
        "TG_PROXY_PORT",
    ],
    "wecom_bot": ["QYWX_KEY", "QYWX_ORIGIN"],
    "wecom_app": ["QYWX_AM"],
    "smtp": [
        "SMTP_SERVER",
        "SMTP_SSL",
        "SMTP_EMAIL",
        "SMTP_PASSWORD",
        "SMTP_NAME",
    ],
    "bark": [
        "BARK_PUSH",
        "BARK_ARCHIVE",
        "BARK_GROUP",
        "BARK_SOUND",
        "BARK_ICON",
        "BARK_LEVEL",
        "BARK_URL",
    ],
    "wxpusher": ["WXPUSHER_APP_TOKEN", "WXPUSHER_TOPIC_IDS", "WXPUSHER_UIDS"],
    "gotify": ["GOTIFY_URL", "GOTIFY_TOKEN", "GOTIFY_PRIORITY"],
    "mediasaber": ["MEDIASABER_HOST", "MEDIASABER_APIKEY"],
    "feishu": ["FSKEY"],
    "dingding": ["DD_BOT_TOKEN", "DD_BOT_SECRET"],
    "igot": ["IGOT_PUSH_KEY"],
    "serverj": ["PUSH_KEY"],
    "chat": ["CHAT_URL", "CHAT_TOKEN"],
}

_META_KEYS = ("name", "type", "enable")


def flatten(channel_conf: Dict[str, Any]) -> Dict[str, Any]:
    """把单个渠道配置展开成扁平字典，只保留该类型需要的键。"""
    if not isinstance(channel_conf, dict):
        return {}

    channel_type = str(channel_conf.get("type", "")).lower()
    required = CHANNEL_KEY_MAP.get(channel_type)

    flat: Dict[str, Any] = {}
    for key, value in channel_conf.items():
        if key in _META_KEYS:
            continue
        if required:
            if key.upper() in required:
                flat[key] = value
        else:
            # 未定义映射的类型保留全部键
            flat[key] = value
    return flat
