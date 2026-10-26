"""日志文件配置与解析。

日志文件按大小轮转；接口层用 parse_records/read_logs 读取，支持按级别过滤和增量拉取。
"""

import logging
import os
import re
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Optional

from app.core.log_context import RidFilter

LOG_DIR = "logs"
LOG_PATH = os.path.join(LOG_DIR, "app.log")
# rid 由 RidFilter 注入，无请求上下文时为空串
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(rid)s%(message)s"

MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 5

# 单条日志的起始行；不匹配的行是上一条的续行（异常堆栈）
# rid 段可选：改造前的旧日志没有它。只认小写十六进制，不会误吃消息开头的 [OP] 这类标签。
RECORD_RE = re.compile(
    r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) - (\S+) - "
    # rid 固定 8 位（见 log_context.RID_LEN），靠长度区分，小写方括号短正文不会被误吃
    r"(DEBUG|INFO|WARNING|ERROR|CRITICAL) - (?:\[([0-9a-f]{8})\] )?(.*)$"
)

# 消息开头的分类标签，如 [HOSTS]。面板单独成列，正文里不再重复
TAG_RE = re.compile(r"^\[([A-Z]+)\]\s*")

# 首次读取时回看的字节数，避免把整个大文件读进内存
TAIL_BYTES = 512 * 1024
MAX_LINES = 5000
LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


def resolve_level(default: str = "INFO") -> int:
    """按 LOG_LEVEL 环境变量取日志级别，非法值回退到 default。"""
    name = os.environ.get("LOG_LEVEL", default).upper()
    return getattr(logging, name, logging.INFO)


def setup_logging(level: Optional[int] = None) -> None:
    """配置根 logger：控制台 + 轮转文件。

    level 为 None 时读 LOG_LEVEL 环境变量，方便排障时开到 DEBUG 而不用改代码。
    """
    if level is None:
        level = resolve_level()
    os.makedirs(LOG_DIR, exist_ok=True)
    formatter = logging.Formatter(LOG_FORMAT)
    rid_filter = RidFilter()

    root = logging.getLogger()
    root.setLevel(level)
    # 重复调用时先清掉旧 handler，否则日志会重复输出
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    stream.addFilter(rid_filter)
    root.addHandler(stream)

    file_handler = RotatingFileHandler(
        LOG_PATH, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(rid_filter)
    root.addHandler(file_handler)


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
    """
    records: List[Dict[str, Any]] = []
    for line in text.splitlines():
        match = RECORD_RE.match(line)
        if match:
            raw = match.group(5)
            tag_match = TAG_RE.match(raw)
            records.append(
                {
                    "ts": match.group(1),
                    "logger": match.group(2),
                    "level": match.group(3),
                    "rid": match.group(4) or "",
                    "tag": tag_match.group(1) if tag_match else "",
                    # 正文去掉标签，面板把标签单独成列
                    "msg": raw[tag_match.end():] if tag_match else raw,
                    "lines": [line],
                }
            )
        elif records:
            records[-1]["lines"].append(line)
        elif line.strip():
            # 文件从记录中间开始，首行没有归属
            records.append(
                {"ts": "", "logger": "", "level": "INFO", "rid": "", "tag": "",
                 "msg": line, "lines": [line]}
            )
    return records


def read_logs(
    offset: int = 0,
    max_lines: int = 1000,
    levels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """读取日志。

    offset 为 0 时回看文件尾部 TAIL_BYTES 字节；非 0 时从该字节位置增量读取。
    offset 大于文件大小说明文件被截断或轮转，此时重置到 0。
    """
    max_lines = min(max(10, max_lines), MAX_LINES)
    wanted = set(levels) if levels else set()

    if not os.path.exists(LOG_PATH):
        return {
            "records": [],
            "offset": 0,
            "size": 0,
            "truncated": False,
            "levels": {},
        }

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
    counts: Dict[str, int] = {}
    for record in records:
        counts[record["level"]] = counts.get(record["level"], 0) + 1

    if wanted:
        records = [r for r in records if r["level"] in wanted]
    records = records[-max_lines:]

    return {
        "records": [
            {
                "ts": r["ts"],
                "logger": r["logger"],
                "level": r["level"],
                "rid": r["rid"],
                "tag": r["tag"],
                "msg": r["msg"],
                "text": "\n".join(r["lines"]),
                # 正文必须带上续行，否则面板会吞掉异常堆栈
                "body": "\n".join([r["msg"]] + r["lines"][1:]),
            }
            for r in records
        ],
        "offset": new_offset,
        "size": size,
        "truncated": truncated,
        "levels": counts,
    }
