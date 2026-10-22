"""路由层共享的配置读取与常量。"""

import logging
import os
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)

CONFIG_PATH = "config/config.yaml"
DEFAULT_CLOUDFLARE_IP = "104.16.91.215"  # 全局默认Cloudflare IP


def get_file_config() -> Dict[str, Any]:
    """从配置文件读取最新配置。

    注意：与 app.globals.get_config 不是同一个东西——后者返回内存中的全局
    config 对象，可能滞后于文件。路由层必须用本函数，否则会出现
    「前端改了配置但接口读到旧值」的问题。
    """
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return {}


def config_write_lock():
    """跨进程配置写锁（实现在 app/main.py）。延迟导入以避免循环依赖。"""
    from app.main import _config_write_lock as _lock

    return _lock()
