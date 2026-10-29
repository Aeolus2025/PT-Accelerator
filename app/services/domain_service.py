"""域名批量导入的领域逻辑：清洗、IP 一致性检查、tracker 构建。"""

import logging
import re
from typing import Any, Dict, List, Tuple

from app.core.constants import DEFAULT_CLOUDFLARE_IP

logger = logging.getLogger(__name__)


def clean_domain(text: str) -> str:
    """清洗单个域名：去协议前缀、切掉路径，保留端口号原样。"""
    value = str(text or "").strip()
    if not value:
        return ""
    return re.sub(r"^https?://", "", value, flags=re.IGNORECASE).split("/")[0]


def strip_port(domain: str) -> str:
    """去掉端口号，得到用于 DNS/HTTPS 探测的纯域名。"""
    return domain.split(":")[0] if ":" in domain else domain


# 顶级域至少两位字母；每级标签不超过 63 字符，且不以连字符开头或结尾
_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)
_IPV4_RE = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")


def is_valid_domain(domain: str) -> bool:
    """判断是否为可解析的域名，允许带端口与 IPv4。

    只校验格式不查 DNS：目的是挡住 `bb` 这类明显不是域名的输入。
    否则每层探测都要等超时，单个无效域名能让一次 hosts 更新多花一分钟。
    """
    host = strip_port(str(domain or "").strip())
    if not host:
        return False
    if _IPV4_RE.match(host):
        return all(0 <= int(part) <= 255 for part in host.split("."))
    return bool(_DOMAIN_RE.match(host))


def clean_domains(raw_domains) -> List[str]:
    """清洗域名：支持列表或按行分隔的字符串，去协议前缀、切路径、去空行。

    保持原有顺序与重复项（去重由后续的已存在检查负责），
    这样调用方的 added/skipped 统计与改造前一致。
    """
    if isinstance(raw_domains, list):
        items = raw_domains
    else:
        items = str(raw_domains or "").strip().split("\n")

    result: List[str] = []
    for item in items:
        domain = clean_domain(item)
        if domain:
            result.append(domain)
    return result


def check_ip_consistency(trackers: List[Dict[str, Any]]) -> Tuple[bool, str]:
    """检查现有已启用 tracker 的 IP 是否一致。返回 (是否一致, 提示信息)。"""
    ips = {t.get("ip") for t in trackers if t.get("enable") and t.get("ip")}
    if len(ips) > 1:
        return False, "检测到现有Tracker的IP不一致，请先统一所有Tracker的IP后再添加。"
    return True, ""


def resolve_default_ip(trackers: List[Dict[str, Any]], fallback: str = DEFAULT_CLOUDFLARE_IP) -> str:
    """取默认 IP：优先沿用现有已启用 tracker 的 IP，否则用优选 IP 或兜底值。"""
    ips = {t.get("ip") for t in trackers if t.get("enable") and t.get("ip")}
    if len(ips) == 1:
        return next(iter(ips))
    return fallback


def build_trackers(
    domains: List[str],
    existing_domains: set,
    default_ip: str,
) -> Tuple[List[Dict[str, Any]], List[str], List[str]]:
    """按域名列表构建 tracker 配置对象。

    返回 (新增的 tracker 列表, 已添加的域名, 跳过的域名)。
    跳过规则：域名已在 existing_domains 中，或在本次循环中已被添加过。
    """
    added: List[Dict[str, Any]] = []
    added_domains: List[str] = []
    skipped_domains: List[str] = []

    seen = set(existing_domains)
    for domain in domains:
        if domain in seen:
            skipped_domains.append(domain)
            continue
        seen.add(domain)
        added.append({
            "name": domain,
            "domain": domain,
            "ip": default_ip,
            "enable": True,
        })
        added_domains.append(domain)

    return added, added_domains, skipped_domains
