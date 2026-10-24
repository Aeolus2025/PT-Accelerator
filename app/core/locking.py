"""跨进程的配置写锁。"""

import logging
import os
import time
from contextlib import contextmanager

from app.core.constants import CONFIG_DIR

logger = logging.getLogger(__name__)


@contextmanager
def config_write_lock(timeout: float = 10.0):
    """跨进程的配置写锁。

    用途：把「读取配置 → 判断是否需要生成 → 写回配置」这段临界区变原子。
    多 worker 下每个进程都会执行 startup_event，若无此锁：
      worker A 读到 password_hash 为空 → 生成密码 P1
      worker B 也读到为空 → 生成密码 P2
      A 写文件(P1) → B 写文件(P2)
    最终生效的是 P2，但 A 的控制台/日志里打印的是 P1，用户拿着 P1 永远登不上。

    实现：POSIX 文件锁（fcntl.flock，独占）。锁文件放在 config/ 下，
    不随 CONFIG_PATH 的原子替换而消失（替换的是目标文件，不是锁文件）。
    非 POSIX 平台（Windows 开发环境）自动降级为无锁，不影响单 worker 使用。
    """
    lock_path = os.path.join(CONFIG_DIR, ".config.lock")
    os.makedirs(CONFIG_DIR, exist_ok=True)

    try:
        import fcntl
    except ImportError:  # 非 POSIX，直接放行
        yield
        return

    lock_file = open(lock_path, "a+")
    acquired = False
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    # 超时后退化为无锁继续执行，避免整个进程卡死在启动阶段
                    logger.warning(f"获取配置写锁超时({timeout}s)，继续执行（可能存在并发写风险）")
                    break
                time.sleep(0.05)
        yield
    finally:
        if acquired:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        lock_file.close()
