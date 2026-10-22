"""配置文件读写。

抽成独立模块是为了让 services 层也能用同一套读写逻辑，而不必依赖 app.api.deps
（那会引入 app.main → 循环导入）。
"""

import logging
import os
from typing import Any, Dict

import yaml

logger = logging.getLogger(__name__)

CONFIG_ENCODINGS = ("utf-8", "gbk", "gb18030")


def read_config(config_path: str = "config/config.yaml") -> Dict[str, Any]:
    """读取配置文件，按 utf-8 / gbk / gb18030 顺序尝试解码。

    每次调用都重新读盘。不要与 app.globals.get_config 混用：后者返回内存对象，
    可能滞后于文件。文件不存在或无法解析时返回空字典。
    """
    if not os.path.exists(config_path):
        return {}
    for encoding in CONFIG_ENCODINGS:
        try:
            with open(config_path, "r", encoding=encoding) as f:
                return yaml.safe_load(f) or {}
        except UnicodeDecodeError:
            continue
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    logger.error("加载配置文件失败: 编码无法识别（已尝试 utf-8 / gbk / gb18030）")
    return {}


def write_config(config_path: str, data: Dict[str, Any]) -> None:
    """整体写入配置文件（UTF-8）。"""
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)


def merge_write_config(config_path: str, partial_update: Dict[str, Any]) -> Dict[str, Any]:
    """读盘后合并局部更新再写回，避免覆盖其它未修改的配置。

    返回合并后的完整配置，供调用方同步内存副本。
    """
    current = read_config(config_path)
    current.update(partial_update or {})
    write_config(config_path, current)
    return current
