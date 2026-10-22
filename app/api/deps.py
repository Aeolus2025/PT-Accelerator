"""路由层共享的配置读取与常量。"""

from typing import Any, Dict

from app.utils.config_io import read_config

CONFIG_PATH = "config/config.yaml"
DEFAULT_CLOUDFLARE_IP = "104.16.91.215"  # 全局默认Cloudflare IP


def get_file_config() -> Dict[str, Any]:
    """从文件读取最新配置，每次调用都重新读盘。

    不要与 app.globals.get_config 混用：后者返回内存对象，可能滞后于文件。
    """
    return read_config(CONFIG_PATH)


def config_write_lock():
    """跨进程配置写锁（实现在 app/main.py）。延迟导入以避免循环依赖。"""
    from app.main import _config_write_lock as _lock

    return _lock()
