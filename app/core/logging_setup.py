"""日志文件配置与解析。

文件与面板使用同一行文本：`[时间] - [级别] - 消息`。
面板直接展示这一行原文，不再从消息里二次切分字段，两处看到的内容永远一致。
"""

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

LOG_DIR = "logs"
LOG_PATH = os.path.join(LOG_DIR, "app.log")

LOG_FORMAT = "[%(asctime)s] - [%(levelname)s] - %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

# 当前格式：[2026-10-27 20:10:50] - [INFO] - [HOSTS] 写入 条目=2 分区=1 耗时=18ms
RECORD_RE = re.compile(
    r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3})?)\] - "
    r"\[(DEBUG|INFO|WARNING|ERROR|CRITICAL)\] - (.*)$"
)

# 2.4.x 及更早的行，带模块名与 rid：
# 2026-10-26 22:41:23,995 - app.services.scheduler - INFO - [a1b2c3d4] [SCHED] 调度器已启动
# 只为读历史文件保留，新写入的行不会命中。
LEGACY_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:,\d{3})?) - \S+ - "
    r"(DEBUG|INFO|WARNING|ERROR|CRITICAL) - (?:\[[0-9a-f]{8}\] )?(.*)$"
)

# 首次读取时回看的字节数，避免把整个大文件读进内存
TAIL_BYTES = 512 * 1024
MAX_LINES = 5000

# 可选级别，与前端下拉框、筛选组保持一致
LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR")
DEFAULT_LEVEL = "INFO"

# 第三方库的常规输出属于噪音，进度由业务代码自己记：
# - apscheduler / urllib3 逐任务、逐连接刷屏
# - tzlocal 是 APScheduler 的依赖，创建调度器时会把 /etc/timezone 的探测过程打成 DEBUG
NOISY_LOGGERS = ("apscheduler", "urllib3", "python_hosts", "tzlocal", "passlib")


def config_level_name() -> Optional[str]:
    """配置文件里的日志级别，未配置或非法时返回 None。

    延迟导入 config_store：它在导入期就要用 logger，放文件头会成环。
    """
    try:
        from app.core import config_store

        value = (config_store.read().get("logging") or {}).get("level")
    except Exception:
        return None
    if isinstance(value, str) and value.upper() in LEVEL_NAMES:
        return value.upper()
    return None


def env_level_name() -> Optional[str]:
    """环境变量 LOG_LEVEL 指定的级别，未设置或非法时返回 None。"""
    value = (os.environ.get("LOG_LEVEL") or "").strip().upper()
    return value if value in LEVEL_NAMES else None


def runtime_level_name() -> str:
    """根 logger 此刻实际生效的级别，面板下拉框按它回显。"""
    return logging.getLevelName(logging.getLogger().level)


def current_level_name() -> str:
    """启动时应采用的级别名。

    优先级：环境变量 LOG_LEVEL > 配置文件 logging.level > INFO。
    环境变量优先，是为了让 `docker run -e LOG_LEVEL=DEBUG` 这类临时排障不被配置文件盖住。
    """
    return env_level_name() or config_level_name() or DEFAULT_LEVEL


def resolve_level(default: str = DEFAULT_LEVEL) -> int:
    """启动时应采用的级别数值。"""
    return getattr(logging, current_level_name(), getattr(logging, default, logging.INFO))


def apply_level(name: str) -> int:
    """立即调整根 logger 的级别，运行期生效。"""
    level = getattr(logging, str(name).upper(), None)
    if not isinstance(level, int):
        raise ValueError("未知的日志级别: %s" % name)

    logging.getLogger().setLevel(level)
    for noisy in NOISY_LOGGERS:
        # 第三方库保持不低于 WARNING，避免逐域名/逐连接刷屏
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))
    return level


def setup_logging(level: Optional[int] = None) -> None:
    """配置根 logger：控制台 + 轮转文件。

    level 为 None 时按 current_level_name() 取，方便排障时开到 DEBUG 而不用改代码。
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATEFMT)

    root = logging.getLogger()
    root.setLevel(level if level is not None else resolve_level())
    # 重复调用时先清掉旧 handler，否则日志会重复输出
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    root.addHandler(stream)

    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(max(root.level, logging.WARNING))


def truncate_log() -> None:
    """清空日志文件。

    FileHandler 以追加模式打开，截断后内核会定位到文件末尾，不会留下空洞。
    复用 handler 的 stream 是为了避免与正在进行的写入并发。
    """
    target = None
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.FileHandler):
            if os.path.abspath(handler.baseFilename) == os.path.abspath(LOG_PATH):
                target = handler
                break

    if target is None:
        os.makedirs(LOG_DIR, exist_ok=True)
        open(LOG_PATH, "w", encoding="utf-8").close()
        return

    target.acquire()
    try:
        target.stream.seek(0)
        target.stream.truncate(0)
    finally:
        target.release()


def parse_records(text: str) -> List[Dict[str, Any]]:
    """把日志文本切成记录，续行并入上一条。

    按行过滤会把异常堆栈与它的首行拆开，所以这里以「时间戳开头的行」为记录边界。
    每条记录的 text 就是文件里的原文，面板照原样渲染，不做任何改写。
    """
    records: List[Dict[str, Any]] = []
    for line in text.splitlines():
        match = RECORD_RE.match(line) or LEGACY_RE.match(line)
        if match:
            records.append({"ts": match.group(1), "level": match.group(2), "text": line})
        elif records:
            # 续行（异常堆栈、多行消息）归属于上一条
            records[-1]["text"] = records[-1]["text"] + "\n" + line
        elif line.strip():
            # 文件从记录中间开始，首行没有归属
            records.append({"ts": "", "level": "INFO", "text": line})
    return records


def read_logs(offset: int = 0, max_lines: int = 1000) -> Dict[str, Any]:
    """读取日志。

    offset 为 0 时回看文件尾部 TAIL_BYTES 字节；非 0 时从该字节位置增量读取。
    offset 大于文件大小说明文件被截断或轮转，此时重置到 0。
    """
    max_lines = min(max(10, max_lines), MAX_LINES)

    if not os.path.exists(LOG_PATH):
        return {"records": [], "offset": 0, "size": 0, "truncated": False}

    size = os.path.getsize(LOG_PATH)
    # 文件被截断或轮转后，旧 offset 已失效
    truncated = offset > size

    if offset > 0 and not truncated:
        # offset 总是由本函数给出，落在行边界上，无需丢弃首行。
        # 但长时间不刷新后一次可能追平整个文件，仍按尾部上限截断。
        start = max(offset, size - TAIL_BYTES)
        partial_head = start > offset
    else:
        # 首次读取或文件已失效：回看尾部一段，首行可能不完整
        start = max(0, size - TAIL_BYTES)
        partial_head = start > 0

    with open(LOG_PATH, "rb") as f:
        f.seek(start)
        # 轮转上限 10MB，这里再兜一层，避免异常大的文件一次读满内存
        chunk = f.read(TAIL_BYTES)

    text = chunk.decode("utf-8", errors="replace")
    # 从中间开始时，首个不完整行丢弃
    if partial_head:
        cut = text.find("\n")
        text = text[cut + 1:] if cut >= 0 else ""
    # 末尾没写完的行留到下次读取
    pending = 0
    if text and not text.endswith("\n"):
        cut = text.rfind("\n")
        if cut >= 0:
            pending = len(text[cut + 1:].encode("utf-8"))
            text = text[:cut + 1]
        else:
            pending = len(text.encode("utf-8"))
            text = ""
    new_offset = size - pending

    records = parse_records(text)
    return {
        "records": records[-max_lines:],
        "offset": new_offset,
        "size": size,
        "truncated": truncated,
    }
