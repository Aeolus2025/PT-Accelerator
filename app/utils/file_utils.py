import os
import tempfile


def atomic_write_text(path: str, content: str, encoding: str = "utf-8") -> None:
    
    # 原子地写入文本文件
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
