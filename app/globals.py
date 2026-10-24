# 全局变量文件，用于存储服务实例，避免循环导入

# 服务实例
hosts_manager = None
cloudflare_service = None
scheduler_service = None
torrent_client_manager = None

def init_services(hm, cs, ss, tcm, cfg=None):
    """初始化全局服务实例。

    cfg 参数保留兼容，但不再保存：配置以磁盘文件为唯一来源，
    运行时一律通过 app.core.config_store.read() 读取，这里存副本会拿到旧值。
    """
    global hosts_manager, cloudflare_service, scheduler_service, torrent_client_manager
    hosts_manager = hm
    cloudflare_service = cs
    scheduler_service = ss
    torrent_client_manager = tcm

def get_hosts_manager():
    return hosts_manager

def get_cloudflare_service():
    return cloudflare_service

def get_scheduler_service():
    return scheduler_service

def get_torrent_client_manager():
    return torrent_client_manager

def get_config():
    """取当前配置。从磁盘读，避免任何内存副本滞后。"""
    from app.core import config_store
    return config_store.read()
