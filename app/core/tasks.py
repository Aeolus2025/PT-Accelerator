"""任务状态登记。

手动触发与定时触发都会改任务状态，原来分别记在 scheduler_service 与
hosts_manager 各自的 task_status 上，查询方需要两个都问一遍，且依赖
getattr 兜底。这里统一成一个可查询的登记表，写入方只报状态，读取方只读。
"""

import logging
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

IDLE: Dict[str, str] = {"status": "done", "message": "无正在运行的任务"}


class TaskRegistry:
    """进程内的任务状态表，key 为任务名"""

    def __init__(self):
        self._lock = threading.Lock()
        self._status: Dict[str, Dict[str, Any]] = {}

    def set(self, name: str, status: str, message: str) -> None:
        """记录某个任务的状态"""
        with self._lock:
            self._status[name] = {"status": status, "message": message}

    def start(self, name: str, message: str) -> None:
        """标记任务开始运行"""
        self.set(name, "running", message)

    def finish(self, name: str, message: str) -> None:
        """标记任务结束（成功或失败都走这里，具体由 message 描述）"""
        self.set(name, "done", message)

    def get(self, name: str) -> Dict[str, Any]:
        """读某个任务的状态，不存在时返回空闲"""
        with self._lock:
            return dict(self._status.get(name) or IDLE)

    def running(self) -> Optional[Dict[str, Any]]:
        """返回任意一个运行中的任务；都没有时返回 None。

        同时只会有一种任务在跑（优选与 hosts 更新是强串行的），
        所以不需要区分是哪个任务在跑。
        """
        with self._lock:
            for status in self._status.values():
                if status.get("status") == "running":
                    return dict(status)
        return None

    def clear(self, name: str) -> None:
        """移除某个任务的状态记录"""
        with self._lock:
            self._status.pop(name, None)


# 进程级单例：调度器、hosts 管理、接口层共用同一份状态
registry = TaskRegistry()
