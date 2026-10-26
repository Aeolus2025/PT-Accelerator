"""hosts 文件的唯一写入入口：路径解析、分区管理、原子写。

对外只暴露三个动作：读当前内容、整体重建项目分区、保存用户手改的内容。
所有写操作都走 atomic_write_text——先写临时文件再 replace，
中途失败不会留下半截 hosts（写坏的 hosts 会让本机 DNS 直接失效）。
"""

import logging
import platform
from typing import Any, Dict, List, Tuple

from app.core import config_store
from app.utils.file_utils import atomic_write_text

logger = logging.getLogger(__name__)


class HostsStore:
    """hosts 文件的读写与分区管理。

    无状态：配置按需读盘，分区标记是常量。
    """

    def __init__(self):
        self.start_mark = "# == PT-Accelerator START =="
        self.end_mark = "# == PT-Accelerator END =="
        self.pt_start_mark = "# ===== PT站点加速开始 ===== #"
        self.pt_end_mark = "# ===== PT站点加速结束 (%d 条记录) ===== #"
        self.source_start_mark = "# ===== %s开始 ===== #"
        self.source_end_mark = "# ===== %s结束 (%d 条记录) ===== #"

    def _config(self) -> Dict[str, Any]:
        """每次读盘：多 worker 下别的进程可能刚改过配置。"""
        return config_store.read(config_store.CONFIG_PATH)

    def read_system_hosts(self) -> List[str]:
        """读取系统hosts文件内容"""
        try:
            hosts_path = self.get_hosts_path()
            with open(hosts_path, 'r') as f:
                return f.readlines()
        except Exception as e:
            logger.exception("[HOSTS] 读取hosts文件失败: %s", str(e))
            return []

    def get_hosts_path(self) -> str:
        """获取hosts文件路径，优先读取配置中的自定义路径 hosts_path"""
        try:
            current = self._config()
            if isinstance(current, dict):
                custom_path = current.get("hosts_path")
                if isinstance(custom_path, str) and custom_path.strip():
                    return custom_path
        except Exception:
            pass
        system = platform.system()
        if system == "Windows":
            return r"c:\\windows\\system32\\drivers\\etc\\hosts"
        else:  # Linux or macOS
            return "/etc/hosts"

    def _write_hosts_atomic(self, content: str) -> None:
        """原子写入 hosts。

        直接 open(path, 'w') 会先截断文件，写入中途失败会留下空文件或半截内容，
        系统 DNS 立即异常。这里写临时文件再 os.replace，失败时原文件完好。
        """
        atomic_write_text(self.get_hosts_path(), content)

    def _strip_project_sections(self, lines: List[str]) -> Tuple[List[str], int]:
        """逐行剥离本项目写入的分区，返回 (保留的行, 移除的分区数)。
        用整行精确匹配 + 状态机，而不是原来的字符串切片 find()：
        """
        kept: List[str] = []
        removed = 0
        in_block = False
        for line in lines:
            stripped = line.strip()
            if stripped == self.start_mark:
                if in_block:
                    # 上一个分区没有 END，接着丢弃
                    continue
                in_block = True
                removed += 1
                continue
            if stripped == self.end_mark:
                if in_block:
                    in_block = False
                # 孤立的 END 直接丢弃，避免残留
                continue
            if not in_block:
                kept.append(line)
        return kept, removed

    def _build_pt_section(self, pt_entries: List[str]) -> List[Tuple[str, List[str], str]]:
        """构建 PT 站点分区；无条目时返回空列表。"""
        if not pt_entries:
            return []
        return [(self.pt_start_mark, pt_entries, self.pt_end_mark % len(pt_entries))]

    def _build_merged_section(self, merged_entries: List[str], merged_enabled: bool) -> List[Tuple[str, List[str], str]]:
        """构建 MergedHosts 分区。

        没有任何启用的 hosts 源时不写入，避免残留一段陈旧条目。
        """
        if not merged_entries:
            return []
        if not merged_enabled:
            logger.debug("[MergedHosts] 无启用源，丢弃 条目=%s", len(merged_entries))
            return []
        return [(
            self.source_start_mark % "MergedHosts",
            merged_entries,
            self.source_end_mark % ("MergedHosts", len(merged_entries))
        )]

    def _update_system_hosts_with_sections(self, sections: List[Tuple[str, List[str], str]]):
        """更新系统hosts文件，保持分段格式，彻底移除所有PT-Accelerator分区，防止分区重复"""
        hosts_path = self.get_hosts_path()
        # 读取当前hosts文件
        with open(hosts_path, 'r') as f:
            lines = f.readlines()
        # 剥离所有历史残留分区（含残缺/顺序异常的情况）
        kept, removed = self._strip_project_sections(lines)
        if removed:
            logger.debug("[HOSTS] 更新前已清理历史分区 数量=%s", removed)
        # 添加新的条目，保持分段格式
        new_content = "".join(kept).rstrip() + "\n\n" + self.start_mark + "\n"
        for start_mark, entries, end_mark in sections:
            new_content += start_mark + "\n"
            for entry in entries:
                new_content += entry + "\n"
            new_content += end_mark + "\n"
        new_content += self.end_mark + "\n"
        # 写入hosts文件
        self._write_hosts_atomic(new_content)

    def clear_project_sections(self) -> None:
        """仅移除本项目写入的分区，保留系统原有hosts内容不变"""
        hosts_path = self.get_hosts_path()
        try:
            with open(hosts_path, 'r') as f:
                lines = f.readlines()
            kept, removed = self._strip_project_sections(lines)
            if removed:
                self._write_hosts_atomic("".join(kept).rstrip() + "\n")
                logger.info("[HOSTS] 清空 移除数=%s 系统内容=保留", removed)
            else:
                logger.info("[HOSTS] 清空 移除数=0")
        except Exception as e:
            logger.exception("[HOSTS] 清理PT-Accelerator分区失败: %s", str(e))

    def save_user_content(self, content: str) -> int:
        """保存用户编辑的 hosts 内容，本项目的分区会被重新生成而不是照搬。

        用户提交的内容里若含分区标记，直接写入会产生重复分区；这里先剥离所有
        项目分区，只保留用户自己的部分，再原子写回。返回被移除的分区数。
        """
        lines = content.splitlines(keepends=True)
        kept, removed = self._strip_project_sections(lines)
        self._write_hosts_atomic("".join(kept))
        if removed:
            logger.info("[HOSTS] save 移除分区=%s", removed)
        else:
            logger.info("[HOSTS] save 结果=成功")
        return removed
