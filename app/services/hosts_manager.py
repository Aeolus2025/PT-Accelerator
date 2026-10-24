"""hosts 管理入口。

具体实现分三块：
  app/services/hosts/store.py        文件路径、分区管理、原子写
  app/services/hosts/sources.py      外部源抓取与测速
  app/services/hosts/manager.py      编排（HostsManager）
  app/services/cloudflare/detector.py  Cloudflare 判定

这里只做向前兼容的再导出，调用方继续 `from app.services.hosts_manager import HostsManager`。
"""

from app.services.hosts.manager import CFST_SCRIPT_TIMEOUT, HostsManager
from app.services.hosts.sources import DOMAIN_BLACKLIST, is_blacklisted

__all__ = ["HostsManager", "is_blacklisted", "DOMAIN_BLACKLIST", "CFST_SCRIPT_TIMEOUT"]
