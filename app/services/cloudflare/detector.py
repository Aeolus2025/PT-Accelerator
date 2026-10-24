"""Cloudflare 站点与 IP 的判定。

判定分四层，任一层命中即可确认：
  1. 配置白名单（cloudflare_domains）
  2. 本地缓存（同一域名在 cache_expiry 秒内不重复探测）
  3. 依次尝试 CNAME / 响应头 / 多 DNS / CF-RAY 四种探测
  4. 都指向 Cloudflare 时再比对 IP 是否属于官方网段

每个域名要发数次 HTTPS/DNS 请求，逐域名重探会让整次 hosts 更新慢到分钟级，
因此结果必须缓存。
"""

import logging
import re
import socket
import time
from typing import Any, Dict, List, Set

import requests
import urllib3

from app.core import config_store

logger = logging.getLogger(__name__)


class CloudflareDetector:
    """判定域名是否为 Cloudflare 站点。

    配置按需读盘，不持有副本。
    """

    def __init__(self):
        self.cf_domains: Set[str] = set()
        self.cloudflare_cache: Dict[str, Any] = {}
        self.cache_expiry = 3600  # 缓存过期时间（秒）
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'close'
        }

    def reload_whitelist(self):
        """重新加载 Cloudflare 白名单集合。"""
        cf_domains_from_config = self._config().get('cloudflare_domains', [])
        self.cf_domains = set(cf_domains_from_config) if isinstance(cf_domains_from_config, list) else set([cf_domains_from_config])

    def _config(self) -> Dict[str, Any]:
        """每次读盘：多 worker 下别的进程可能刚改过配置。"""
        return config_store.read(config_store.CONFIG_PATH)

    def is_cloudflare_domain(self, domain: str) -> bool:
        """判断域名是否使用了Cloudflare"""
        if not domain:
            logger.debug("[Cloudflare检测] 域名为空，返回False")
            return False
        
        # 规范化域名，移除协议前缀、路径后缀和端口号
        domain = domain.lower()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'/.*$', '', domain)  # 移除路径
        domain = re.sub(r':\d+$', '', domain)  # 移除端口号
        
        # 检查缓存中是否已有结果
        current_time = time.time()
        if domain in self.cloudflare_cache:
            cache_time, is_cf = self.cloudflare_cache[domain]
            # 检查缓存是否过期
            if current_time - cache_time < self.cache_expiry:
                logger.debug(f"[Cloudflare检测] 域名 {domain} 使用缓存结果: {is_cf}")
                return is_cf
        
        logger.info(f"[Cloudflare检测] 开始检测域名: {domain}")
        
        # 获取配置中的Cloudflare域名
        cf_domains_from_config = self._config().get('cloudflare_domains', [])
        if isinstance(cf_domains_from_config, list):
            self.cf_domains.update(cf_domains_from_config)
        elif isinstance(cf_domains_from_config, str):
            self.cf_domains.add(cf_domains_from_config)
        
        # 1. 检查域名是否在白名单中
        if domain in self.cf_domains:
            logger.info(f"[Cloudflare检测] 域名 {domain} 在配置的Cloudflare域名白名单中")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 2. 检查主域名
        main_domain = self._get_main_domain(domain)
        if main_domain in self.cf_domains:
            logger.info(f"[Cloudflare检测] 域名 {domain} 的主域名 {main_domain} 在Cloudflare域名白名单中")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 3. 检查IP范围
        try:
            ip = socket.gethostbyname(domain)
            logger.debug(f"[Cloudflare检测] 域名 {domain} 解析到IP: {ip}")
            if self._is_cloudflare_ip(ip):
                logger.info(f"[Cloudflare检测] 域名 {domain} 解析到Cloudflare IP范围: {ip}")
                self._cache_cloudflare_result(domain, True)
                return True
            else:
                logger.debug(f"[Cloudflare检测] 域名 {domain} 解析到非Cloudflare IP: {ip}")
        except socket.error as e:
            logger.debug(f"[Cloudflare检测] 域名 {domain} 解析IP失败: {str(e)}")
        
        # 4. 检查DNS CNAME记录
        logger.debug(f"[Cloudflare检测] 开始CNAME记录检查: {domain}")
        is_cf_by_cname = self._check_cloudflare_by_cname(domain)
        if is_cf_by_cname:
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过CNAME记录确认使用Cloudflare")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 5. 检查HTTP头部
        logger.debug(f"[Cloudflare检测] 开始HTTP头部检查: {domain}")
        is_cf_by_headers = self._check_cloudflare_by_headers(domain)
        if is_cf_by_headers:
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过HTTP头部确认使用Cloudflare")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 6. 使用HTTP请求方法检测
        logger.debug(f"[Cloudflare检测] 开始HTTP请求方法检查: {domain}")
        is_cf_by_http = self._check_cloudflare_by_http(domain)
        if is_cf_by_http:
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过HTTP请求内容确认使用Cloudflare")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 7. 使用多个DNS服务器进行验证
        logger.debug(f"[Cloudflare检测] 开始多DNS服务器验证: {domain}")
        is_cf_by_multi_dns = self._check_cloudflare_by_multi_dns(domain)
        if is_cf_by_multi_dns:
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过多DNS服务器确认使用Cloudflare")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 8. 最后尝试直接解析
        logger.debug(f"[Cloudflare检测] 开始最后IP解析尝试: {domain}")
        try:
            for attempt in range(2):  # 尝试两次，增加可靠性
                ip = socket.gethostbyname(domain)
                logger.debug(f"[Cloudflare检测] 域名 {domain} 最终解析尝试 #{attempt+1}, IP: {ip}")
                if self._is_cloudflare_ip(ip):
                    logger.info(f"[Cloudflare检测] 域名 {domain} 最终解析确认使用Cloudflare IP: {ip}")
                    self._cache_cloudflare_result(domain, True)
                    return True
                time.sleep(0.5)  # 短暂延迟后再次尝试
        except socket.error as e:
            logger.debug(f"[Cloudflare检测] 域名 {domain} 最终解析失败: {str(e)}")
        
        logger.info(f"[Cloudflare检测] 域名 {domain} 通过所有检测方法均未确认使用Cloudflare")
        self._cache_cloudflare_result(domain, False)
        return False

    def _cache_cloudflare_result(self, domain, is_cloudflare):
        """缓存Cloudflare检测结果"""
        self.cloudflare_cache[domain] = (time.time(), is_cloudflare)
        # 清理过期缓存
        if len(self.cloudflare_cache) > 1000:  # 防止缓存过大
            self._clean_expired_cache()

    def _clean_expired_cache(self):
        """清理过期的缓存项"""
        current_time = time.time()
        expired_keys = [
            k for k, (timestamp, _) in self.cloudflare_cache.items() 
            if current_time - timestamp > self.cache_expiry
        ]
        for key in expired_keys:
            del self.cloudflare_cache[key]

    def _get_main_domain(self, domain: str) -> str:
        """获取域名的主域名部分"""
        parts = domain.split('.')
        if len(parts) <= 2:
            return domain
        
        # 检查是否为国家/地区代码域名（如 .co.uk, .com.cn）
        country_tlds = {'uk', 'au', 'jp', 'cn', 'br', 'mx', 'ru', 'eu', 'de', 'fr', 'it', 'nl', 'sg', 'kr'}
        if len(parts) >= 3 and parts[-2] in country_tlds:
            return '.'.join(parts[-3:])
        
        return '.'.join(parts[-2:])

    def _check_cloudflare_by_cname(self, domain: str) -> bool:
        """通过CNAME记录检查是否使用Cloudflare"""
        try:
            import dns.resolver
            try:
                # 配置解析器
                resolver = dns.resolver.Resolver(configure=True)
                resolver.timeout = 2.0
                resolver.lifetime = 2.0
                
                # 查询CNAME记录
                answers = resolver.resolve(domain, 'CNAME')
                for rdata in answers:
                    cname = str(rdata.target).lower()
                    # 检查CNAME是否指向Cloudflare
                    cf_indicators = ['cloudflare', 'cdn', 'cdnproviders', 'ssl', 'workers.dev', 'pages.dev']
                    if any(indicator in cname for indicator in cf_indicators):
                        logger.debug(f"[Cloudflare检测] 域名 {domain} 的CNAME指向Cloudflare: {cname}")
                        return True
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout, dns.exception.DNSException) as e:
                logger.debug(f"[Cloudflare检测] CNAME解析失败: {domain}, 错误: {str(e)}")
        except ImportError:
            logger.debug("[Cloudflare检测] dns.resolver模块不可用")
        
        return False

    def _check_cloudflare_by_headers(self, domain: str) -> bool:
        """通过HTTP响应头检查是否使用Cloudflare"""
        try:
            import requests
            
            # 禁用SSL不安全请求的警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                # 尝试HTTPS和HTTP
                for protocol in ['https', 'http']:
                    try:
                        url = f"{protocol}://{domain}"
                        resp = requests.head(url, headers=headers, timeout=3, allow_redirects=True, verify=False)
                        
                        # 检查Cloudflare特有的HTTP头
                        cf_headers = [
                            'cf-ray', 'cf-cache-status', 'cf-request-id', 'cf-worker', 
                            'cf-connecting-ip', 'cf-visitor', 'cf-bgj', 'cf-ipcountry'
                        ]
                        
                        for cf_header in cf_headers:
                            if cf_header in resp.headers:
                                logger.debug(f"[Cloudflare检测] 域名 {domain} 的HTTP响应头包含Cloudflare标识: {cf_header}")
                                return True
                        
                        # 检查Server头
                        server = resp.headers.get('Server', '').lower()
                        if 'cloudflare' in server:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的Server头指示Cloudflare: {server}")
                            return True
                        
                        # 检查Set-Cookie头
                        cookies = resp.headers.get('Set-Cookie', '').lower()
                        if any(cookie in cookies for cookie in ['__cfduid', 'cf_clearance', 'cf_use_ob']):
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的Cookie包含Cloudflare标识")
                            return True
                    except Exception as e:
                        logger.debug(f"[Cloudflare检测] {protocol}请求失败: {domain}, 错误: {str(e)}")
                        continue
            except Exception as e:
                logger.debug(f"[Cloudflare检测] HTTP请求异常: {str(e)}")
        except ImportError:
            logger.debug("[Cloudflare检测] requests模块不可用")
        
        return False

    def _check_cloudflare_by_multi_dns(self, domain: str) -> bool:
        """使用多个DNS服务器验证是否使用Cloudflare"""
        try:
            # 使用常见的公共DNS服务器
            dns_servers = ['8.8.8.8', '1.1.1.1', '9.9.9.9', '208.67.222.222']
            
            try:
                import dns.resolver
                import concurrent.futures
                
                def resolve_with_dns(dns_server):
                    try:
                        resolver = dns.resolver.Resolver(configure=False)
                        resolver.nameservers = [dns_server]
                        resolver.timeout = 1.5
                        resolver.lifetime = 1.5
                        answers = resolver.resolve(domain, 'A')
                        return [str(rdata) for rdata in answers]
                    except Exception as e:
                        logger.debug(f"[Cloudflare检测] DNS {dns_server} 解析失败: {str(e)}")
                        return []
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    future_to_dns = {executor.submit(resolve_with_dns, server): server for server in dns_servers}
                    for future in concurrent.futures.as_completed(future_to_dns):
                        dns_server = future_to_dns[future]
                        try:
                            ips = future.result()
                            for ip in ips:
                                if self._is_cloudflare_ip(ip):
                                    logger.debug(f"[Cloudflare检测] 通过DNS {dns_server} 解析到Cloudflare IP: {ip}")
                                    return True
                        except Exception as e:
                            logger.debug(f"[Cloudflare检测] 处理DNS {dns_server} 结果时出错: {str(e)}")
            except ImportError:
                logger.debug("[Cloudflare检测] dns.resolver或concurrent.futures模块不可用")
                
                # 备用方案：使用socket直接解析
                try:
                    ip = socket.gethostbyname(domain)
                    if self._is_cloudflare_ip(ip):
                        logger.debug(f"[Cloudflare检测] 使用socket直接解析到Cloudflare IP: {ip}")
                        return True
                except socket.error:
                    pass
        except Exception as e:
            logger.debug(f"[Cloudflare检测] 多DNS检测异常: {str(e)}")
        
        return False

    def _is_cloudflare_ip(self, ip: str) -> bool:
        """判断IP是否属于Cloudflare"""
        if not ip:
            logger.debug("[Cloudflare检测] IP为空")
            return False
            
        try:
            # 检查常见的Cloudflare IP范围
            cf_ip_ranges = [
                # IPv4范围 (部分)
                '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22', '104.16.0.0/13', 
                '104.24.0.0/14', '108.162.192.0/18', '131.0.72.0/22', '141.101.64.0/18', 
                '162.158.0.0/15', '172.64.0.0/13', '173.245.48.0/20', '188.114.96.0/20', 
                '190.93.240.0/20', '197.234.240.0/22', '198.41.128.0/17',
                
                # IPv6范围 (部分)
                '2400:cb00::/32', '2405:8100::/32', '2405:b500::/32', '2606:4700::/32', 
                '2803:f800::/32', '2c0f:f248::/32', '2a06:98c0::/29'
            ]
            
            try:
                import ipaddress
                ip_obj = ipaddress.ip_address(ip)
                
                for ip_range in cf_ip_ranges:
                    try:
                        if ip_obj in ipaddress.ip_network(ip_range):
                            logger.debug(f"[Cloudflare检测] IP {ip} 属于Cloudflare IP范围 {ip_range}")
                            return True
                    except ValueError as e:
                        logger.debug(f"[Cloudflare检测] 检查IP范围出错: {ip_range}, 错误: {str(e)}")
                        continue
                
                # 未匹配到任何范围
                logger.debug(f"[Cloudflare检测] IP {ip} 不在任何已知的Cloudflare IP范围内")
                
            except ImportError:
                logger.debug("[Cloudflare检测] ipaddress模块不可用，使用基本检查")
                
                # 如果ipaddress模块不可用，至少检查一些常见的范围
                cf_prefixes = [
                    '104.16.', '104.17.', '104.18.', '104.19.', '104.20.', '104.21.', '104.22.', '104.23.',
                    '172.64.', '172.65.', '172.66.', '172.67.', '172.68.', '172.69.', '172.70.',
                    '162.158.', '198.41.', '103.21.244.', '103.22.200.'
                ]
                
                for prefix in cf_prefixes:
                    if ip.startswith(prefix):
                        logger.debug(f"[Cloudflare检测] IP {ip} 匹配Cloudflare前缀 {prefix}")
                        return True
                
                logger.debug(f"[Cloudflare检测] IP {ip} 不匹配任何已知的Cloudflare前缀")
                
        except Exception as e:
            logger.debug(f"[Cloudflare检测] IP检查异常: {str(e)}")
        
        return False

    def _check_cloudflare_by_cf_ray(self, domain: str) -> bool:
        """通过检查响应头中的CF-Ray字段判断域名是否使用Cloudflare"""
        try:
            logger.debug(f"[Cloudflare检测] 使用CF-Ray标头检查域名 {domain}")
            
            # 禁用SSL不安全请求的警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            urls = [
                f"https://{domain}",
                f"http://{domain}"
            ]
            
            for url in urls:
                try:
                    response = requests.get(
                        url, 
                        headers=self.headers, 
                        timeout=5,
                        verify=False
                    )
                    
                    # 检查CF-Ray头部
                    if 'CF-Ray' in response.headers:
                        logger.debug(f"[Cloudflare检测] 域名 {domain} 响应包含CF-Ray头: {response.headers.get('CF-Ray')}")
                        return True
                        
                    # 检查其他Cloudflare特有的头部
                    cf_headers = ['cf-cache-status', 'cf-apo-via', 'cf-edge-cache', 'cf-bgj']
                    for header in cf_headers:
                        if header in response.headers:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 响应包含Cloudflare特有头: {header}")
                            return True
                            
                    # 检查服务器信息
                    server = response.headers.get('Server', '').lower()
                    if 'cloudflare' in server:
                        logger.debug(f"[Cloudflare检测] 域名 {domain} 服务器信息包含Cloudflare: {server}")
                        return True
                        
                except requests.RequestException as e:
                    logger.debug(f"[Cloudflare检测] 请求 {url} 失败: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.debug(f"[Cloudflare检测] CF-Ray检查异常: {str(e)}")
            
        return False

    def is_cloudflare_enabled(self, domain: str) -> bool:
        """
        检查域名是否启用了Cloudflare
        综合使用多种方法进行检测，任一方法返回True则认为域名使用了Cloudflare
        """
        if not domain:
            return False
            
        logger.debug(f"[Cloudflare检测] 开始检查域名 {domain}")
        
        # 首先尝试DNS检测方法
        if self._check_cloudflare_by_dns(domain):
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过DNS检测确认使用Cloudflare")
            return True
            
        # 然后尝试通过Cloudflare IP范围检测
        resolved_ips = self._resolve_domain(domain)
        if resolved_ips:
            for ip in resolved_ips:
                if self._is_cloudflare_ip(ip):
                    logger.info(f"[Cloudflare检测] 域名 {domain} 解析到Cloudflare IP: {ip}")
                    return True
                    
        # 最后尝试HTTP头部检测方法
        if self._check_cloudflare_by_cf_ray(domain):
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过HTTP头部检测确认使用Cloudflare")
            return True
            
        logger.debug(f"[Cloudflare检测] 域名 {domain} 未检测到使用Cloudflare")
        return False

    def _resolve_domain(self, domain: str) -> List[str]:
        """解析域名获取IP地址列表"""
        ips = []
        try:
            # 首先尝试使用socket库解析
            try:
                ip = socket.gethostbyname(domain)
                ips.append(ip)
            except socket.error:
                pass
            
            # 如果有dns.resolver模块，尝试使用它获取更完整的结果
            try:
                import dns.resolver
                resolver = dns.resolver.Resolver(configure=True)
                resolver.timeout = 2.0
                resolver.lifetime = 2.0
                answers = resolver.resolve(domain, 'A')
                for rdata in answers:
                    ip = str(rdata)
                    if ip not in ips:
                        ips.append(ip)
            except (ImportError, dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException):
                pass
                
            # 如果上述方法都失败，使用系统nslookup命令尝试解析
            if not ips:
                try:
                    import subprocess
                    cmd = ['nslookup', domain]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                    for line in result.stdout.splitlines():
                        line = line.strip()
                        # 查找Address行，提取IP地址
                        if line.startswith('Address:') or 'Address:' in line:
                            ip = line.split('Address:')[-1].strip()
                            if ip and ip not in ips and not ip.startswith('127.0.') and not ip.startswith('::1'):
                                ips.append(ip)
                except (subprocess.SubprocessError, FileNotFoundError, Exception):
                    pass
                    
        except Exception as e:
            logger.debug(f"[域名解析] 解析域名 {domain} 出错: {str(e)}")
            
        return ips

    def _check_cloudflare_by_dns(self, domain: str) -> bool:
        """通过DNS记录检查域名是否使用Cloudflare"""
        try:
            # 检查域名NS记录是否指向Cloudflare
            try:
                import dns.resolver
                resolver = dns.resolver.Resolver(configure=True)
                resolver.timeout = 2.0
                resolver.lifetime = 2.0
                
                # 先检查顶级域名的NS记录
                try:
                    parts = domain.split('.')
                    if len(parts) > 2:
                        root_domain = '.'.join(parts[-2:])
                    else:
                        root_domain = domain
                    
                    answers = resolver.resolve(root_domain, 'NS')
                    for rdata in answers:
                        ns = str(rdata).lower()
                        if 'cloudflare' in ns or 'ns.cloudflare.com' in ns:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的NS记录指向Cloudflare: {ns}")
                            return True
                except Exception:
                    pass
                
                # 检查CNAME记录
                try:
                    answers = resolver.resolve(domain, 'CNAME')
                    for rdata in answers:
                        cname = str(rdata.target).lower()
                        # Cloudflare CNAME特征
                        cf_indicators = ['cloudflare', 'cdn', 'workers.dev', 'pages.dev']
                        if any(indicator in cname for indicator in cf_indicators):
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的CNAME指向Cloudflare: {cname}")
                            return True
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    pass
                
                # 检查MX记录
                try:
                    answers = resolver.resolve(domain, 'MX')
                    for rdata in answers:
                        mx = str(rdata.exchange).lower()
                        if 'cloudflare' in mx:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的MX记录指向Cloudflare: {mx}")
                            return True
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    pass
                
                # 检查TXT记录中的特征
                try:
                    answers = resolver.resolve(domain, 'TXT')
                    for rdata in answers:
                        txt = str(rdata).lower()
                        if 'cloudflare' in txt:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的TXT记录包含Cloudflare特征: {txt}")
                            return True
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    pass
                    
            except ImportError:
                logger.debug("[Cloudflare检测] dns.resolver模块不可用")
                
        except Exception as e:
            logger.debug(f"[Cloudflare检测] DNS检测异常: {str(e)}")
            
        return False

    def _check_cloudflare_by_http(self, domain: str) -> bool:
        """通过HTTP请求和响应头检查域名是否使用Cloudflare"""
        try:
            # 禁用SSL不安全请求的警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # 尝试HTTPS和HTTP
            for protocol in ['https', 'http']:
                logger.debug(f"[Cloudflare检测] 尝试 {protocol} 请求: {domain}")
                url = f"{protocol}://{domain}"
                
                # 尝试发送HTTP请求
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'close'
                }
                
                # 设置较短的超时时间，避免长时间等待
                timeout = 5
                
                try:
                    response = requests.get(url, headers=headers, timeout=timeout, verify=False)
                    
                    # 检查HTTP头部是否有Cloudflare特征
                    response_headers = response.headers
                    
                    # Cloudflare特征头部
                    cf_headers = [
                        'cf-ray',
                        'cf-cache-status',
                        'cf-request-id',
                        'cf-worker',
                        'cf-connecting-ip',
                        'cf-ipcountry',
                        'cf-visitor',
                        'cf-bgj'
                    ]
                    
                    for header in cf_headers:
                        if header.lower() in response_headers:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的HTTP响应头包含Cloudflare特征: {header}")
                            return True
                    
                    # 检查服务器头部
                    server = response_headers.get('server', '').lower()
                    if 'cloudflare' in server:
                        logger.debug(f"[Cloudflare检测] 域名 {domain} 的Server头显示使用Cloudflare: {server}")
                        return True
                    
                    # 检查响应内容中的Cloudflare特征
                    try:
                        content = response.text.lower()
                        cf_content_markers = [
                            'cloudflare',
                            'cdn-cgi',
                            'cloudflare-nginx',
                            '__cf_email__',
                            'cf-error-code',
                            'cf_chl_'
                        ]
                        
                        for marker in cf_content_markers:
                            if marker in content:
                                logger.debug(f"[Cloudflare检测] 域名 {domain} 的响应内容包含Cloudflare特征: {marker}")
                                return True
                    except Exception as e:
                        logger.debug(f"[Cloudflare检测] 解析响应内容时出错: {str(e)}")
                        
                except requests.RequestException as e:
                    logger.debug(f"[Cloudflare检测] {protocol}请求异常: {str(e)}")
                    
                    # 如果连接被重置，可能是Cloudflare防火墙拦截
                    if "connection" in str(e).lower() and ("reset" in str(e).lower() or "aborted" in str(e).lower()):
                        logger.debug(f"[Cloudflare检测] 连接被重置，可能是Cloudflare防火墙: {domain}")
                        return True
                    continue  # 尝试下一个协议
                    
        except Exception as e:
            logger.debug(f"[Cloudflare检测] HTTP检测异常: {str(e)}")
            
        return False

    def _dns_check(self, domain, ip):
        try:
            result = socket.gethostbyname(domain)
            return result == ip
        except Exception:
            return False
