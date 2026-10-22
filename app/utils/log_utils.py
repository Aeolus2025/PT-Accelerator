"""日志辅助工具。"""

import contextlib
import logging
from typing import Iterator


@contextlib.contextmanager
def temporary_log_level(logger_name: str, level: int) -> Iterator[None]:
    """临时调整某个 logger 的级别，退出时还原（含异常路径）。"""
    target = logging.getLogger(logger_name)
    original = target.level
    target.setLevel(level)
    try:
        yield
    finally:
        target.setLevel(original)
