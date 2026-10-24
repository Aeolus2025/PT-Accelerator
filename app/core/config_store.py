"""配置的唯一入口：读、写、按节合并。

所有配置读写都应经过这里，不要在别处直接 open(config.yaml)。
之前的写法散落在路由、服务、启动流程三处，各自决定要不要加锁，容易出现
「读了旧值 → 改了某一节 → 整份写回 → 覆盖别人的改动」。

读永远从磁盘来，不缓存：多 worker 下别的进程随时可能改过配置，
缓存副本会让本进程拿着旧值做决策。
"""

import logging
import os
from typing import Any, Callable, Dict

import yaml

from app.core.constants import CONFIG_ENCODINGS, CONFIG_PATH
from app.core.locking import config_write_lock
from app.utils.file_utils import atomic_write_text

logger = logging.getLogger(__name__)


def read(config_path: str = CONFIG_PATH) -> Dict[str, Any]:
    """读取配置文件，按 utf-8 / gbk / gb18030 顺序尝试解码。

    文件不存在或无法解析时返回空字典，由调用方决定缺失配置如何处理。
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


def write(config_path: str, data: Dict[str, Any]) -> None:
    """整体写入配置文件。

    原子写：先写临时文件再 os.replace，中途失败不会留下半截配置。
    统一落 UTF-8，GBK 保存的老配置读出来也以 UTF-8 写回。
    """
    atomic_write_text(
        config_path,
        yaml.dump(data or {}, default_flow_style=False, allow_unicode=True),
    )


def update(partial_update: Dict[str, Any], config_path: str = CONFIG_PATH) -> Dict[str, Any]:
    """读盘后合并局部更新再写回，避免覆盖其它未修改的配置。

    读和写在同一把锁内完成，避免两个请求各自读旧值后互相覆盖。
    返回合并后的完整配置。
    """
    with config_write_lock():
        current = read(config_path)
        current.update(partial_update or {})
        write(config_path, current)
        return current


def mutate(change: Callable[[Dict[str, Any]], Any], config_path: str = CONFIG_PATH) -> Dict[str, Any]:
    """在锁内读最新配置，交给 change 原地修改，再写回。

    用于按节合并之外的修改（如列表增删改）。调用方不能再先
    自己 read() 一份旧副本再改，否则并发请求会互相覆盖。
    返回修改后的完整配置。
    """
    with config_write_lock():
        current = read(config_path)
        change(current)
        write(config_path, current)
        return current
