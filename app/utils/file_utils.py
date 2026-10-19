"""
配置文件原子写入工具。

多 worker（`uvicorn --workers N`）或“调度任务 + Web 请求”并发写 config.yaml 时，
直接 `open(path, 'w')` 会先把文件截断再写入：另一个进程若恰好在截断与写完之间读取，
会拿到空文件或半截 YAML，`yaml.safe_load` 解析失败，轻则配置丢失、重则启动报错。

本模块提供 atomic_write_text()：先写同目录临时文件，`os.replace()` 原子替换。
POSIX 下 `os.replace` 是原子的，读取方要么看到旧文件、要么看到新文件，不会看到半截内容。
"""

import os
import tempfile


def atomic_write_text(path: str, content: str, encoding: str = "utf-8") -> None:
    """
    原子地写入文本文件。

    1. 在目标文件所在目录创建临时文件（同目录才能保证 os.replace 不跨文件系统）
    2. 写入并 fsync，确保数据真正落盘
    3. os.replace() 原子替换目标文件

    失败时清理临时文件，原文件保持不动。
    """
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".tmp-", suffix=".swp")
    try:
        with os.fdopen(fd, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        # os.replace 在同一文件系统内是原子操作
        os.replace(tmp_path, path)
        tmp_path = None  # 已成功替换，不再需要清理
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
