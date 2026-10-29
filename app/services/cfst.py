import logging
import os
import shutil
import platform
from typing import Dict, Any

from app.services.hosts_manager import HostsManager

logger = logging.getLogger(__name__)

class CloudflareSpeedTestService:
    """CloudflareSpeedTest服务，用于测试优选Cloudflare IP"""
    
    def __init__(self, config: Dict[str, Any], hosts_manager: HostsManager):
        self.config = config
        self.hosts_manager = hosts_manager
        
        # 工作目录
        self.base_dir = os.getcwd()
        
        # 查找CloudflareSpeedTest可执行文件
        self.cft_path = self._find_cloudflare_st()
        self.bin_dir = os.path.dirname(self.cft_path)
        
        # 结果和IP文件路径
        self.result_file = os.path.join(self.base_dir, "result.csv")
        self.ip_file = os.path.join(self.base_dir, "ip.txt")
        self.ipv6_file = os.path.join(self.base_dir, "ipv6.txt")
        
        # 记录当前状态
        self.running = False
        
        logger.info("[CFST] 初始化成功")
        logger.debug("[CFST] 路径 基础目录=%s IP=%s IPv6=%s 结果=%s",
                     self.base_dir, self.ip_file, self.ipv6_file, self.result_file)
        
        # 确保IP文件存在
        self._ensure_ip_files()
        
    def _find_cloudflare_st(self) -> str:
        """查找CloudflareSpeedTest可执行文件，支持架构自适应"""
        arch_dir = self._get_arch_dir()
        machine = platform.machine().lower()
        logger.debug("[CFST] 检测到架构: %s, 使用目录: %s", machine, arch_dir)

        # 可能的路径，按架构自适应（按优先级排列，一旦命中即停止查找）
        possible_paths = [
            # 在当前目录查找
            os.path.join(self.base_dir, "cfst"),
            os.path.join(self.base_dir, arch_dir, "cfst"),

            # 在系统目录查找（Docker 镜像由 Dockerfile 安装到 /usr/local/bin/cfst）
            "/usr/local/bin/cfst",
            "/usr/bin/cfst",

            # 在Docker环境中的路径
            "/app/cfst",
            f"/app/{arch_dir}/cfst",
        ]

        for path in possible_paths:
            if not os.path.exists(path):
                continue
            if os.access(path, os.X_OK):
                logger.debug("[CFST] CloudflareSpeedTest路径: %s", path)
                return path
            # 文件存在但缺少可执行权限（常见于从压缩包/Windows 解压到仓库），当场修复后使用
            logger.warning("[CFST] cfst 文件存在但缺少可执行权限，正在修复: %s", path)
            try:
                os.chmod(path, 0o755)
                logger.info("[CFST] 已修复可执行权限 路径=%s", path)
                return path
            except OSError as e:
                logger.exception("[CFST] 修复可执行权限失败: %s -> %s", path, e)

        # 一个都不存在：给出默认路径让后续调用报明确错误
        default_path = f"./{arch_dir}/cfst"
        logger.error("[CFST] 未找到CloudflareSpeedTest可执行文件，将尝试默认路径 %s", default_path)
        return default_path
        
    def update_config(self, config: Dict[str, Any]):
        """更新配置"""
        self.config = config
    
    def _get_arch_dir(self) -> str:
        """获取当前架构对应的目录名"""
        machine = platform.machine().lower()
        if machine in ("aarch64", "arm64"):
            return "cfst_linux_arm64"
        else:
            return "cfst_linux_amd64"
    
    def _ensure_ip_files(self):
        """确保IP文件存在"""
        logger.debug("[CFST] 确保IP文件存在: %s", self.ip_file)
        
        # 检查当前目录下是否已存在ip.txt
        if os.path.exists(self.ip_file):
            logger.debug("[CFST] IP文件已存在: %s", self.ip_file)
            self._verify_ip_file(self.ip_file)
            return
        
        # 未找到ip.txt，尝试在可执行文件同目录下查找
        bin_dir_ip_file = os.path.join(self.bin_dir, "ip.txt")
        if os.path.exists(bin_dir_ip_file):
            logger.debug("[CFST] 在可执行文件目录下找到IP文件: %s", bin_dir_ip_file)
            try:
                # 复制到当前目录
                shutil.copy(bin_dir_ip_file, self.ip_file)
                logger.debug("[CFST] 已复制IP文件: %s -> %s", bin_dir_ip_file, self.ip_file)
                self._verify_ip_file(self.ip_file)
                return
            except Exception as e:
                logger.exception("[CFST] 复制IP文件失败: %s", str(e))
        
        # 在其他可能位置查找，支持架构自适应
        logger.debug("[CFST] 在其他位置查找IP文件")
        # 获取架构目录
        arch_dir = self._get_arch_dir()
        
        possible_paths = [
            os.path.join(self.base_dir, arch_dir, "ip.txt"),
            "/usr/local/bin/ip.txt",
            "/usr/local/share/CloudflareST/ip.txt",
            "/app/ip.txt"
        ]
        
        for path in possible_paths:
            logger.debug("[CFST] 检查路径: %s - %s", path, "存在" if os.path.exists(path) else "不存在")
            if os.path.exists(path):
                try:
                    shutil.copy(path, self.ip_file)
                    logger.info("[CFST] 已复制IP文件: %s -> %s", path, self.ip_file)
                    self._verify_ip_file(self.ip_file)
                    return
                except Exception as e:
                    logger.exception("[CFST] 复制IP文件失败: %s", str(e))
        
        # 还是找不到，创建一个基本的
        logger.warning("[CFST] 未找到现有IP文件，创建一个基本的Cloudflare IP列表在 %s", self.ip_file)
        self._create_default_ip_file()
        
        # 同样处理IPv6文件
        if self.config.get("cloudflare", {}).get("ipv6", False):
            self._ensure_ipv6_file()
    
    def _verify_ip_file(self, file_path: str):
        """验证IP文件是否有效"""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                line_count = len(content.splitlines())
                if len(content) < 10 or line_count < 2:
                    logger.warning("[CFST] IP文件内容可能无效，将创建默认IP文件")
                    self._create_default_ip_file()
        except Exception as e:
            logger.exception("[CFST] 读取IP文件失败: %s", str(e))
            self._create_default_ip_file()
    
    def _create_default_ip_file(self):
        """创建默认的IP文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.ip_file), exist_ok=True)
            
            with open(self.ip_file, "w") as f:
                f.write("# Cloudflare IP Ranges\n")
                f.write("# From: https://www.cloudflare.com/ips/\n")
                f.write("1.1.1.0/24\n")  # Cloudflare DNS
                f.write("1.0.0.0/24\n")  # Cloudflare DNS
                f.write("104.16.0.0/12\n")  # Cloudflare CDN
                f.write("172.64.0.0/13\n")  # Cloudflare CDN
                f.write("173.245.48.0/20\n")  # Cloudflare
                f.write("103.21.244.0/22\n")  # Cloudflare
                f.write("103.22.200.0/22\n")  # Cloudflare
                f.write("103.31.4.0/22\n")  # Cloudflare
                f.write("141.101.64.0/18\n")  # Cloudflare
                f.write("108.162.192.0/18\n")  # Cloudflare
                f.write("190.93.240.0/20\n")  # Cloudflare
                f.write("188.114.96.0/20\n")  # Cloudflare
                f.write("197.234.240.0/22\n")  # Cloudflare
                f.write("198.41.128.0/17\n")  # Cloudflare
                f.write("162.158.0.0/15\n")  # Cloudflare
                f.write("104.16.0.0/13\n")  # Cloudflare
                f.write("104.24.0.0/14\n")  # Cloudflare
            
            # 输出文件信息
            if os.path.exists(self.ip_file):
                file_size = os.path.getsize(self.ip_file)
                logger.debug("[CFST] 成功创建IP文件: %s, 大小: %s 字节", self.ip_file, file_size)
                with open(self.ip_file, 'r') as f:
                    lines = f.readlines()
                    logger.debug("[CFST] IP文件包含 %s 行", len(lines))
            else:
                logger.error("[CFST] IP文件创建失败: %s", self.ip_file)
        except Exception as e:
            logger.exception("[CFST] 创建IP文件失败: %s", str(e))
    
    def _ensure_ipv6_file(self):
        """确保IPv6文件存在"""
        logger.debug("[CFST] 确保IPv6文件存在: %s", self.ipv6_file)
        
        if os.path.exists(self.ipv6_file):
            logger.debug("[CFST] IPv6文件已存在: %s", self.ipv6_file)
            return
        
        # 在可执行文件目录下查找
        bin_dir_ipv6_file = os.path.join(self.bin_dir, "ipv6.txt")
        if os.path.exists(bin_dir_ipv6_file):
            try:
                shutil.copy(bin_dir_ipv6_file, self.ipv6_file)
                logger.debug("[CFST] 已复制IPv6文件: %s -> %s", bin_dir_ipv6_file, self.ipv6_file)
                return
            except Exception as e:
                logger.exception("[CFST] 复制IPv6文件失败: %s", str(e))
        
        # 在其他位置查找，支持架构自适应
        # 获取架构目录
        arch_dir = self._get_arch_dir()
        
        possible_paths = [
            os.path.join(self.base_dir, arch_dir, "ipv6.txt"),
            "/usr/local/bin/ipv6.txt",
            "/usr/local/share/CloudflareST/ipv6.txt",
            "/app/ipv6.txt"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    shutil.copy(path, self.ipv6_file)
                    logger.info("[CFST] 已复制IPv6文件: %s -> %s", path, self.ipv6_file)
                    return
                except Exception as e:
                    logger.exception("[CFST] 复制IPv6文件失败: %s", str(e))
        
        # 创建一个基本的IPv6文件
        try:
            with open(self.ipv6_file, "w") as f:
                f.write("# Cloudflare IPv6 Ranges\n")
                f.write("# From: https://www.cloudflare.com/ips/\n")
                f.write("2400:cb00::/32\n")
                f.write("2405:8100::/32\n")
                f.write("2606:4700::/32\n")
                f.write("2803:f800::/32\n")
                f.write("2a06:98c0::/29\n")
                f.write("2c0f:f248::/32\n")
            
            logger.debug("[CFST] 成功创建IPv6文件: %s", self.ipv6_file)
        except Exception as e:
            logger.exception("[CFST] 创建IPv6文件失败: %s", str(e))
