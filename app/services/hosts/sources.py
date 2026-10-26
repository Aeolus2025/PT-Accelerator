"""外部 hosts 源的抓取与 IP 测速。

抓取结果落本地缓存，源站不可达时回退到上次的内容；
测速带失败重试，连续失败超过阈值才真正剔除域名。
"""

import hashlib
import logging
import os
import socket
import subprocess
import time
from typing import Dict, List, Tuple

import requests


logger = logging.getLogger(__name__)

# 通用域名黑名单：不该出现在加速 hosts 里的基础设施域名
DOMAIN_BLACKLIST = [
    "docker.com",
    "docker.io",
    "quay.io",
    "gcr.io",
    "k8s.gcr.io",
    "ghcr.io"
]


def is_blacklisted(domain: str) -> bool:
    return any(bad in domain for bad in DOMAIN_BLACKLIST)


class HostsSourceFetcher:
    """抓取外部 hosts 源并测速。

    持有域名 IP 历史与失败计数：网络抖动时可以用历史 IP 兜底，
    不至于因为一次探测失败就把站点从 hosts 里删掉。
    """

    def __init__(self):
        self.ping_retry_count = 3

    def _get_cache_path(self, url: str) -> str:
        """根据url生成本地缓存文件路径"""
        cache_dir = "cache"
        os.makedirs(cache_dir, exist_ok=True)
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
        return os.path.join(cache_dir, url_hash + ".cache")

    def _fetch_hosts_source(self, url: str) -> List[Tuple[str, str]]:
        """智能重试+超时+本地缓存兜底+黑名单过滤"""
        cache_path = self._get_cache_path(url)
        max_retries = 2
        timeout = 20
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                response = requests.get(url, timeout=timeout)
                if response.status_code == 200:
                    entries = []
                    lines = response.text.splitlines()
                    for line in lines:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split()
                        if len(parts) < 2:
                            continue
                        ip, domain = parts[0], parts[1]
                        if is_blacklisted(domain):
                            continue  # 跳过黑名单域名
                        entries.append((ip, domain))
                    # 拉取成功，写入本地缓存
                    try:
                        with open(cache_path, 'w', encoding='utf-8') as f:
                            f.write(response.text)
                    except Exception as e:
                        logger.exception("[HOSTS] 写入缓存失败: %s, 错误: %s", cache_path, e)
                    return entries
                else:
                    last_exception = Exception(f"HTTP状态码: {response.status_code}")
            except Exception as e:
                last_exception = e
                logger.exception("[HOSTS] 拉取hosts源失败(%s/%s): %s, 错误: %s", attempt+1, max_retries+1, url, e)
        # 全部重试失败，尝试本地缓存兜底
        if os.path.exists(cache_path):
            logger.warning("[HOSTS] 所有重试失败，使用本地缓存兜底: %s", cache_path)
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                entries = []
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    ip, domain = parts[0], parts[1]
                    if is_blacklisted(domain):
                        continue
                    entries.append((ip, domain))
                return entries
            except Exception as e:
                logger.exception("[HOSTS] 读取本地缓存失败: %s, 错误: %s", cache_path, e)
        logger.error("[HOSTS] 处理hosts源出错: %s, 错误: %s", url, last_exception)
        return []

    def _ping_ip(self, ip: str, timeout: int = 1, cache: Dict[str, float] = None, domain: str = None, on_result=None) -> float:
        """用socket方式检测IP连通性，返回延迟（毫秒），不可达返回None
        
        Args:
            ip: 要测试的IP地址
            timeout: 超时时间（秒）
            cache: IP延迟缓存字典，用于避免重复测试同一IP
            domain: 与IP关联的域名，用于记录历史IP和失败计数
        """
        # 使用缓存避免重复测试
        if cache is not None and ip in cache:
            return cache[ip]
            
        # 增加多方式检测（socket连接+ICMP ping），并增加重试机制，避免因临时网络波动导致误判
        ports = [80, 443]
        # 优先尝试socket连接
        for retry in range(self.ping_retry_count):
            for port in ports:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(timeout)
                    start = time.time()
                    s.connect((ip, port))
                    end = time.time()
                    s.close()
                    latency = (end - start) * 1000  # 毫秒
                    if cache is not None:
                        cache[ip] = latency
                    if on_result:
                        on_result(domain, ip, True)
                    return latency
                except Exception:
                    continue
            # 如果所有端口都连接失败，等待短暂时间后重试
            if retry < self.ping_retry_count - 1:
                time.sleep(0.5)
        # socket全部失败后，尝试ICMP ping
        try:
            # Windows下ping命令参数不同
            ping_cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip] if os.name == "nt" else ["ping", "-c", "1", "-W", str(timeout), ip]
            result = subprocess.run(ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                if cache is not None:
                    cache[ip] = 999  # ping通但端口不通，延迟设为较高
                if on_result:
                    on_result(domain, ip, True)
                return 999
        except Exception:
            pass
        # 所有重试都失败
        if cache is not None:
            cache[ip] = None
        if on_result:
            on_result(domain, ip, False)
        return None
