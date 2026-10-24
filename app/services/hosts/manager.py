"""hosts 更新的编排层。

一次更新要串起四件事：收集待写入的域名 → 抓取外部源并测速 → 组装分区
→ 原子写回 hosts。这里只负责调度与状态维护，具体动作分别委托给
HostsStore（写文件）、HostsSourceFetcher（抓取测速）、CloudflareDetector（判定）。

两条更新路径：
  update_hosts()                只用配置里的域名 + 外部源，不跑 cfst
  run_cfst_and_update_hosts()   先跑 cfst 优选，再更新 tracker 与 hosts
"""

import json
import logging
import os
import platform
import subprocess
import time
from typing import Any, Dict, List, Optional

from app.core import config_store
from app.core.tasks import registry as task_registry
from app.core.constants import CONFIG_PATH, DEFAULT_CLOUDFLARE_IP
from app.services.cloudflare.detector import CloudflareDetector
from app.services.domain_service import strip_port as _strip_port
from app.services.hosts.sources import HostsSourceFetcher, is_blacklisted
from app.services.hosts.store import HostsStore

logger = logging.getLogger(__name__)

# 优选脚本的硬超时；跑飞了也不能让 task_running 永远为 True
CFST_SCRIPT_TIMEOUT = 900

# 任务状态在 registry 中的登记名
TASK_NAME = "hosts"


class HostsManager:
    """hosts 更新的编排层。"""

    def __init__(self, config: Dict[str, Any]):
        # config 参数保留以兼容调用方；配置内容一律按需从磁盘读，不持有副本
        self.store = HostsStore()
        self.sources = HostsSourceFetcher()
        self.detector = CloudflareDetector()
        # 最新优选的Cloudflare IP
        self.best_cloudflare_ip = None
        # 域名IP历史记录，用于在网络波动时提供兜底IP
        self.domain_ip_history: Dict[str, str] = {}
        # 域名连续失败计数器
        self.domain_failure_counter: Dict[str, int] = {}
        # 连续失败次数阈值，超过此值才真正剔除域名
        self.max_failure_count = 3
        # 任务状态追踪
        task_registry.finish(TASK_NAME, "无任务")
        self.task_running = False
        # 运行中被拦下的更新请求：当前这轮收尾后再补跑一次，避免"界面已提示启动、实际没写"
        self.pending_update = False

    def reload_whitelist(self):
        """重新加载 Cloudflare 白名单集合。"""
        self.detector.reload_whitelist()

    # 以下三个委托给 store / detector：路由层按原接口调用，不必知道拆分细节
    def read_system_hosts(self) -> List[str]:
        """读取系统 hosts 内容。"""
        return self.store.read_system_hosts()

    def clear_project_sections(self) -> None:
        """移除本项目写入的分区，保留其他内容。"""
        self.store.clear_project_sections()

    def save_user_content(self, content: str) -> int:
        """保存用户编辑的 hosts 内容，返回被移除的分区数。"""
        return self.store.save_user_content(content)

    def is_cloudflare_domain(self, domain: str) -> bool:
        """判断域名是否为 Cloudflare 站点。"""
        return self.detector.is_cloudflare_domain(domain)

    def _merge_write_config(self, partial_update: Dict[str, Any]):
        """将局部更新安全合并写回 config/config.yaml，避免覆盖其它未修改配置"""
        try:
            config_store.update(partial_update or {}, CONFIG_PATH)
        except Exception as e:
            logger.error(f"安全合并写配置失败: {e}")

    def _config(self) -> Dict[str, Any]:
        """读取当前配置。

        每次读盘：多 worker 下别的进程可能刚改过配置，
        读内存副本会拿到旧值。写操作仍通过 _merge_write_config 落盘。
        """
        return config_store.read(CONFIG_PATH)

    def _collect_pt_entries(self) -> List[str]:
        """收集PT站点的条目（已优化：不再检测IP连通性，直接写入，但严格过滤非Cloudflare站点）"""
        entries = []
        # 如果有优选的IP，使用该IP，否则使用配置中的IP
        cloudflare_ip = self.best_cloudflare_ip or DEFAULT_CLOUDFLARE_IP
        # 添加来自配置的Tracker域名，但只添加Cloudflare站点
        trackers = self._config().get("trackers") or []
        if trackers:
            non_cf_domains = []
            for tracker in trackers:
                if not tracker.get("enable") or not tracker.get("domain"):
                    continue
                    
                domain = tracker['domain']
                # 移除端口号再检测
                clean_domain = domain.split(':')[0] if ':' in domain else domain
                
                # 严格检查是否为Cloudflare站点
                is_cf = self.detector.is_cloudflare_domain(clean_domain)
                
                if is_cf:
                    ip = tracker.get("ip") or cloudflare_ip
                    # 直接写入，不再检测连通性
                    self.domain_ip_history[domain] = ip
                    entries.append(f"{ip}\t{domain}")
                else:
                    non_cf_domains.append(domain)
            
            # 记录被过滤的非Cloudflare站点
            if non_cf_domains:
                logger.info(f"[PT站点过滤] 以下{len(non_cf_domains)}个非Cloudflare站点未添加到hosts: {', '.join(non_cf_domains)}")
                
        return entries

    # ---------------------------------------------------------- 两条入口共用的步骤

    def _filter_non_cloudflare_trackers(self):
        """剔除不是 Cloudflare 的 tracker 并写回配置，返回保留下来的列表。

        历史遗留的非 CF 域名留在配置里会让监控一直失败，所以每次更新都顺手清掉。
        """
        trackers = self._config().get("trackers") or []
        if not trackers:
            return []

        # 检测每个域名要数秒，先在锁外算好判定结果
        kept, dropped, dropped_keys = [], [], set()
        for tracker in trackers:
            domain = tracker.get("domain")
            if not domain:
                continue
            clean_domain = _strip_port(domain)
            if self.detector.is_cloudflare_domain(clean_domain):
                kept.append(tracker)
            else:
                dropped.append(domain)
                dropped_keys.add(clean_domain)

        if dropped:
            logger.info(f"[历史清理] 从配置中过滤了 {len(dropped)} 个非Cloudflare站点: {', '.join(dropped)}")

            # 只按锁内最新列表剔除被判定的域名：检测期间新加的 tracker 不能被旧快照覆盖掉
            def _apply(current):
                items = current.get("trackers") or []
                current["trackers"] = [
                    t for t in items
                    if _strip_port(t.get("domain") or "") not in dropped_keys
                ]

            config_store.mutate(_apply)
            logger.info("[历史清理] 已更新配置文件(合并写)，移除了所有非Cloudflare站点")
            kept = [t for t in kept if _strip_port(t.get("domain") or "") not in dropped_keys]
        return kept

    def _collect_source_candidates(self):
        """收集各 hosts 源与历史兜底给出的候选 IP。

        返回 (候选映射 {域名: {IP, ...}}, 启用源标志, 跳过的域名集合)。
        「启用源标志」决定后面要不要写 MergedHosts 分区：没有任何启用的源时，
        整个 MergedHosts 分区连同备份都必须清空，否则残留域名会被兜底捡回来。
        """
        disabled_domains = self._get_disabled_tracker_domains()
        tracker_domains = {
            t["domain"] for t in (self._config().get("trackers") or [])
            if t.get("enable") and t.get("domain")
        }
        merged_enabled = self._is_merged_hosts_enabled()
        if not merged_enabled:
            logger.info("[MergedHosts] 当前没有启用的 hosts 源，跳过来源收集与历史兜底")
        self._prune_domain_ip_history()

        candidates: Dict[str, set] = {}
        current_domains = set()

        def skip(domain: str) -> bool:
            return domain in tracker_domains or domain.strip().lower() in disabled_domains

        if merged_enabled:
            hosts_sources = [
                s for s in (self._config().get("hosts_sources") or [])
                if s.get("enable") and s.get("url") and s.get("name")
            ]
            if hosts_sources:
                logger.info(f"开始处理 {len(hosts_sources)} 个外部hosts源")
            for i, source in enumerate(hosts_sources):
                source_name = source.get("name", "未命名源")
                task_registry.start(TASK_NAME, f"正在处理hosts源 ({i+1}/{len(hosts_sources)}): {source_name}")
                started = time.time()
                logger.info(f"正在处理hosts源 ({i+1}/{len(hosts_sources)}): {source_name}")
                entries = self.sources._fetch_hosts_source(source["url"])
                logger.info(f"获取hosts源 {source_name} 完成，返回 {len(entries)} 条记录，耗时 {time.time() - started:.2f} 秒")
                for ip, domain in entries:
                    if skip(domain):
                        continue
                    candidates.setdefault(domain, set()).add(ip)
                    current_domains.add(domain)

            # 历史 IP 作为兜底，让本次没抓到的域名沿用上次的地址
            for domain, ip in self.domain_ip_history.items():
                if skip(domain):
                    continue
                candidates.setdefault(domain, set()).add(ip)
                current_domains.add(domain)

            # 智能兜底：本次丢失的域名看看 DNS 还通不通，通就保留备份里的 IP
            backup = self._load_merged_hosts_backup()
            for lost_domain in set(backup) - current_domains:
                if not self._can_keep_lost_domain(lost_domain):
                    logger.info(f"[兜底跳过] 域名 {lost_domain} 不满足兜底条件（无启用源/已禁用/黑名单），丢弃")
                    continue
                lost_ip = backup[lost_domain]
                if self.detector._dns_check(lost_domain, lost_ip):
                    candidates.setdefault(lost_domain, set()).add(lost_ip)
                    logger.warning(f"[兜底保留] 域名 {lost_domain} 本次未被任何源收录，但DNS检测有效，保留上次IP: {lost_ip}")
                else:
                    logger.warning(f"[兜底丢弃] 域名 {lost_domain} 本次未被任何源收录，且DNS检测无效，丢弃上次IP: {lost_ip}")

        return candidates, merged_enabled

    def _record_ping_result(self, domain: str, ip: str, ok: bool):
        """记下探测结果：成功刷新历史 IP，失败累加计数器。"""
        if not domain:
            return
        if ok:
            self.domain_ip_history[domain] = ip
            self.domain_failure_counter[domain] = 0
        else:
            self.domain_failure_counter[domain] = self.domain_failure_counter.get(domain, 0) + 1

    def _pick_best_ip(self, candidates: Dict[str, set]):
        """为每个域名挑延迟最低的 IP，全不可达时退回任意一个。

        返回 ({域名: IP}, [日志行])。
        """
        task_registry.start(TASK_NAME, "正在进行域名IP优选")
        latency_cache: Dict[str, float] = {}
        best_ips: Dict[str, str] = {}
        log_lines = []

        for domain, ip_set in candidates.items():
            if is_blacklisted(domain):
                continue
            best_ip, best_latency = None, None
            for ip in ip_set:
                latency = self.sources._ping_ip(ip, cache=latency_cache, domain=domain, on_result=self._record_ping_result)
                if latency is not None and (best_latency is None or latency < best_latency):
                    best_ip, best_latency = ip, latency
            if best_ip:
                best_ips[domain] = best_ip
                log_lines.append(f"域名 {domain} 选用IP: {best_ip}，延迟: {best_latency:.2f} ms")
            else:
                fallback = next(iter(ip_set))
                best_ips[domain] = fallback
                log_lines.append(f"域名 {domain} 所有IP不可达，兜底选用: {fallback}")

        return best_ips, log_lines

    def _write_hosts_sections(self, pt_entries: List[str], merged_ips: Dict[str, str], merged_enabled: bool):
        """拼出全部分区并原子写入系统 hosts，返回写入的条目总数。"""
        sections = self.store._build_pt_section(pt_entries)

        merged_entries = [f"{ip}\t{domain}" for domain, ip in merged_ips.items() if not is_blacklisted(domain)]
        merged_entries.sort(key=lambda x: x.split("\t")[1])
        sections.extend(self.store._build_merged_section(merged_entries, merged_enabled))

        task_registry.start(TASK_NAME, "正在更新系统hosts文件")
        logger.info("开始更新系统hosts文件")
        started = time.time()
        self.store._update_system_hosts_with_sections(sections)
        logger.info(f"更新系统hosts文件完成，耗时 {time.time() - started:.2f} 秒")

        total_entries = sum(len(entries) for _, entries, _ in sections)
        logger.info(f"成功更新hosts文件，添加了{total_entries}条记录，共{len(sections)}个分区")
        return total_entries

    def _save_backup(self, merged_ips: Dict[str, str], merged_enabled: bool):
        """无启用源时清空备份，否则兜底逻辑会把残留域名捡回来。"""
        self._save_merged_hosts_backup(merged_ips if merged_enabled else {})


    def update_hosts(self):
        """更新hosts文件，合并PT站点、订阅源和自定义规则。

        路由普遍用 background_tasks.add_task 触发，一次更新要跑几十秒。
        运行期间再来请求时不并发执行，而是记下待补跑，由当前这轮收尾后再跑一遍：
        否则界面已提示"任务已启动"，实际这次变更要等到下一次定时或手动触发才生效。
        """
        if self.task_running:
            logger.warning("已有hosts更新任务在运行，本次变更将在当前任务结束后补跑一次")
            self.pending_update = True
            return False

        self.task_running = True
        try:
            while True:
                self.pending_update = False
                if not self._update_hosts_once():
                    return False
                if not self.pending_update:
                    return True
                logger.info("检测到运行期间的更新请求，补跑一次 hosts 更新")
        finally:
            self.task_running = False

    def _update_hosts_once(self) -> bool:
        """执行一轮完整的 hosts 更新，返回是否成功。"""
        task_registry.start(TASK_NAME, "开始更新hosts文件...")
        logger.info("开始更新hosts文件...")

        try:
            self._filter_non_cloudflare_trackers()

            pt_entries = self._collect_pt_entries()
            logger.info(f"收集到 {len(pt_entries)} 条PT站点条目")

            candidates, merged_enabled = self._collect_source_candidates()
            merged_ips, log_lines = self._pick_best_ip(candidates)

            total_entries = self._write_hosts_sections(pt_entries, merged_ips, merged_enabled)

            logger.info("=== 域名优选IP结果汇总 ===")
            for line in log_lines:
                logger.info(line)
            self._save_backup(merged_ips, merged_enabled)

            task_registry.finish(TASK_NAME, f"已完成hosts更新，添加了{total_entries}条记录")
            return True
        except Exception as e:
            error_msg = f"更新hosts文件失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            task_registry.finish(TASK_NAME, error_msg)
            return False


    def _read_best_ip_from_result(self, script_path: str) -> Optional[str]:
        """读取优选脚本落盘的结果文件，取 IP 列的第一行。

        cfst 的 -o 输出是 CSV，首行为表头（IP地址,已发送,已接收,丢包率,平均延迟,下载速度,...），
        正常直接读第 2 行第 1 列，不依赖脚本的中文输出文案。
        """
        result_path = os.path.join(os.path.dirname(os.path.abspath(script_path)), "result_hosts.txt")
        if not os.path.exists(result_path):
            logger.error(f"未找到优选结果文件: {result_path}")
            return None

        try:
            with open(result_path, "r", encoding="utf-8", errors="replace") as f:
                lines = [line.strip() for line in f if line.strip()]
        except OSError as e:
            logger.error(f"读取优选结果文件失败: {e}")
            return None

        if len(lines) < 2:
            logger.error(f"优选结果文件无数据行: {result_path}")
            return None

        best_ip = lines[1].split(",")[0].strip()
        if not best_ip:
            logger.error(f"优选结果文件第一行 IP 为空: {lines[1]!r}")
            return None
        return best_ip

    def add_cloudflare_ip(self, domain: str, ip: str):
        """添加Cloudflare优选IP到配置"""
        logger.info(f"为域名 {domain} 设置Cloudflare优选IP: {ip}")
        
        # 设置最佳IP
        self.best_cloudflare_ip = ip
        logger.info(f"设置最佳Cloudflare IP: {ip}")
        
        # 更新配置中的IP：基于磁盘快照修改，避免覆盖其它进程的改动
        trackers = self._config().get("trackers") or []

        # 查找是否已存在该域名
        for tracker in trackers:
            if tracker["domain"] == domain:
                tracker["ip"] = ip
                break
        else:
            # 不存在则添加
            trackers.append({
                "name": domain,
                "domain": domain,
                "ip": ip,
                "enable": True
            })

        # 保存配置（仅写入 trackers 变更）
        self._merge_write_config({"trackers": trackers})
                    
        # 更新所有tracker的IP
        self._update_all_trackers_ip(ip)
        
        # 更新hosts
        self.update_hosts()

    def _update_all_trackers_ip(self, ip: str):
        """更新所有tracker的IP为最优IP"""
        trackers = self._config().get("trackers") or []
        if not trackers:
            return

        changed = False
        for tracker in trackers:
            if tracker.get("enable") and tracker.get("ip") != ip:
                tracker["ip"] = ip
                changed = True
                logger.info(f"更新tracker {tracker.get('domain')} 的IP为 {ip}")

        # 全量写盘会覆盖并发改动，走 merge 只提交 trackers
        if changed:
            self._merge_write_config({"trackers": trackers})

    def run_cfst_and_update_hosts(self, script_path: str = None):
        """先跑 cfst 优选脚本拿到最快 IP，再用它更新 tracker 与 hosts。

        与 update_hosts 的区别只有两点：先进脚本拿到 best_ip，以及把该 IP 写进每个
        Cloudflare tracker。其余收集来源、挑 IP、写 hosts 的步骤两者共用。
        """
        if self.task_running:
            logger.warning("已有hosts更新任务在运行，本次变更将在当前任务结束后补跑一次")
            self.pending_update = True
            return False
        self.task_running = True
        task_registry.start(TASK_NAME, "正在执行Cloudflare优选IP任务")

        try:
            if not script_path:
                machine = platform.machine().lower()
                if machine in ("aarch64", "arm64"):
                    script_path = "cfst_linux_arm64/cfst_hosts.sh"
                else:
                    script_path = "cfst_linux_amd64/cfst_hosts.sh"
            logger.info("开始执行严格串行的优选IP+更新tracker+更新hosts流程")

            best_ip = self._run_cfst_script(script_path)
            if not best_ip:
                return False  # _run_cfst_script 已写好失败状态

            self.best_cloudflare_ip = best_ip
            logger.info(f"串行流程提取到最优IP: {best_ip}")

            updated_count = self._apply_ip_to_trackers(best_ip)

            pt_entries = self._collect_pt_entries()
            candidates, merged_enabled = self._collect_source_candidates()
            merged_ips, log_lines = self._pick_best_ip(candidates)
            total_entries = self._write_hosts_sections(pt_entries, merged_ips, merged_enabled)

            logger.info("=== 域名优选IP结果汇总 ===")
            for line in log_lines:
                logger.info(line)
            self._save_backup(merged_ips, merged_enabled)

            task_registry.finish(
                TASK_NAME,
                f"Cloudflare优选完成！IP: {best_ip}，已更新 {updated_count} 个Tracker和 {total_entries} 条hosts记录",
            )
            self.task_running = False
            logger.info("已完成hosts文件更新")
            return True
        except Exception as e:
            error_msg = f"严格串行流程执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            task_registry.finish(TASK_NAME, error_msg)
            self.task_running = False
            return False

    def _run_cfst_script(self, script_path: str):
        """跑优选脚本并从结果文件读回最优 IP，失败时返回 None 并置好任务状态。"""
        if not os.path.exists(script_path):
            logger.error(f"脚本文件不存在: {script_path}")
            task_registry.finish(TASK_NAME, f"优选失败: 脚本文件不存在: {script_path}")
            self.task_running = False
            return None

        task_registry.start(TASK_NAME, "正在运行Cloudflare优选脚本")
        try:
            # 脚本会全套跑一遍测速，正常几分钟；给足上限防止挂死后永久占用 task_running
            result = subprocess.run(
                ["bash", script_path],
                capture_output=True,
                text=True,
                timeout=CFST_SCRIPT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            logger.error(f"优选脚本执行超时（{CFST_SCRIPT_TIMEOUT}s），流程中止")
            task_registry.finish(TASK_NAME, f"优选失败: 脚本执行超时（{CFST_SCRIPT_TIMEOUT}s）")
            self.task_running = False
            return None

        if result.returncode != 0:
            logger.error(f"脚本退出码 {result.returncode}: {result.stderr}")
            task_registry.finish(TASK_NAME, f"优选失败: 脚本退出码 {result.returncode}")
            self.task_running = False
            return None

        logger.info(f"脚本执行成功: {result.stdout}")
        # 优先读脚本落盘的结果文件，比自己解析中文 stdout 可靠得多
        best_ip = self._read_best_ip_from_result(script_path)
        if not best_ip:
            logger.error("未能从脚本输出中提取到最优IP，流程中止")
            task_registry.finish(TASK_NAME, "优选失败: 未能提取到最优IP")
            self.task_running = False
            return None
        return best_ip

    def _apply_ip_to_trackers(self, best_ip: str) -> int:
        """把优选到的 IP 写进所有 Cloudflare tracker，返回更新条数。"""
        trackers = self._config().get("trackers") or []
        if not trackers:
            return 0

        # 先算判定结果，再带进锁内应用；检测期间新增的 tracker 不会被旧快照覆盖
        cf_keys, dropped = set(), []
        for tracker in trackers:
            domain = tracker.get("domain")
            if not domain:
                continue
            clean_domain = _strip_port(domain)
            if self.detector.is_cloudflare_domain(clean_domain):
                cf_keys.add(clean_domain)
            else:
                dropped.append(domain)

        if dropped:
            logger.info(f"[IP优选] 过滤了 {len(dropped)} 个非Cloudflare站点: {', '.join(dropped)}")

        dropped_keys = {_strip_port(d) for d in dropped}
        updated = 0

        def _apply(current):
            nonlocal updated
            items = current.get("trackers") or []
            result = []
            for tracker in items:
                key = _strip_port(tracker.get("domain") or "")
                if key in dropped_keys:
                    continue
                if key in cf_keys:
                    tracker["ip"] = best_ip
                    updated += 1
                result.append(tracker)
            current["trackers"] = result

        config_store.mutate(_apply)
        logger.info(f"已将 {updated} 个Cloudflare站点Tracker的IP更新为 {best_ip}")
        return updated


    def get_task_status(self):
        """获取当前任务状态（读统一的 task registry）"""
        return task_registry.get(TASK_NAME)

    def remove_tracker_domain(self, domain: str):
        """删除tracker时同步清理历史IP和失败计数，防止兜底机制误兜底"""
        if domain in self.domain_ip_history:
            del self.domain_ip_history[domain]
        if domain in self.domain_failure_counter:
            del self.domain_failure_counter[domain]
        logger.info(f"[Tracker删除] 已清理历史记录和失败计数: {domain}")

    def _load_merged_hosts_backup(self):
        backup_path = os.path.join("config", "merged_hosts_backup.json")
        if os.path.exists(backup_path):
            try:
                with open(backup_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"读取MergedHosts备份失败: {e}")
        return {}

    def _save_merged_hosts_backup(self, merged_dict):
        backup_path = os.path.join("config", "merged_hosts_backup.json")
        try:
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(merged_dict, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"写入MergedHosts备份失败: {e}")

    def _get_disabled_tracker_domains(self):
        """获取所有已禁用的tracker域名"""
        disabled_domains = set()
        trackers = self._config().get('trackers') or []
        for t in trackers:
            if not t.get('enable', True) and t.get('domain'):
                disabled_domains.add(t['domain'].strip().lower())
        return disabled_domains

    def _get_active_tracker_domains(self) -> set:
        """获取所有已启用 tracker 的规范化域名"""
        active = set()
        for t in (self._config().get('trackers') or []):
            if t.get('enable', True) and t.get('domain'):
                normalized = self._normalize_domain(t['domain'])
                if normalized:
                    active.add(normalized)
        return active

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        """域名规范化：去端口、去首尾空白、转小写，用于一致比对"""
        if not domain:
            return ""
        return str(domain).strip().lower().split(':')[0]

    def _is_merged_hosts_enabled(self) -> bool:
        """是否存在至少一个已启用且配置完整的 hosts 源"""
        for source in (self._config().get("hosts_sources") or []):
            if source.get("enable") and source.get("url") and source.get("name"):
                return True
        return False

    def _prune_domain_ip_history(self):
        """清理 domain_ip_history：只保留当前 tracker 列表中的域名

        判定规则（必须同时满足才保留）：
        1. 规范化后属于当前配置的某个 tracker 域名（含端口写法自动归一）；
        2. 该 tracker 未被禁用（已禁用的域名不参与兜底）。

        返回被清理掉的域名集合，便于日志与测试。
        """
        history = getattr(self, "domain_ip_history", None)
        if not history:
            return set()

        active = set()
        for t in (self._config().get("trackers") or []):
            if not t.get("enable", True):
                continue  # 已禁用的 tracker 不参与兜底
            d = self._normalize_domain(t.get("domain") or "")
            if d:
                active.add(d)

        stale = []
        for key in list(history.keys()):
            if self._normalize_domain(key) not in active:
                stale.append(key)

        for key in stale:
            history.pop(key, None)

        if stale:
            logger.info(f"[历史清理] domain_ip_history 清理 {len(stale)} 条残留: {', '.join(sorted(stale))}")
        return set(stale)

    def _can_keep_lost_domain(self, domain: str) -> bool:
        """判断"从备份中捡回"的域名是否允许保留

        必须同时满足：存在已启用的 hosts 源、仍是当前某个启用 tracker 的域名、
        未被禁用、未被黑名单命中。少了「仍属于 tracker」这一条，用户删掉的域名
        只要还留在备份里且 DNS 可解析，就会被无限期捡回来。
        """
        if not self._is_merged_hosts_enabled():
            return False
        normalized = self._normalize_domain(domain)
        if not normalized:
            return False
        if normalized not in self._get_active_tracker_domains():
            return False
        if normalized in self._get_disabled_tracker_domains():
            return False
        if is_blacklisted(normalized):
            return False
        return True
