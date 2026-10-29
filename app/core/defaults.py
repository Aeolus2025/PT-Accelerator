"""配置默认值：首次启动时写出的初始配置。

新部署的配置由这些常量决定，改动会影响所有尚未存在 config.yaml 的实例。
"""

from app.core.constants import DEFAULT_CLOUDFLARE_IP

# 预装的外部 hosts 源：全部默认关闭，用户可在 UI「Hosts源」页按需勾选启用。
HOSTS_SOURCE_PRESETS = [
    {
        "name": "GitHub（Gitlab源）",
        "url": "https://gitlab.com/ineo6/hosts/-/raw/master/next-hosts",
        "enable": False
    },
    {
        "name": "GitHub（Gitee源）",
        "url": "https://gitee.com/godfather1103/github-hosts/raw/master/hosts",
        "enable": False
    }
]

DEFAULT_CONFIG = {
    "cloudflare": {
        "enable": True,
        "cron": "0 0 * * *",  # 每天零点运行
        "ipv6": False,
        "additional_args": "",
        "notify": True
    },
    "trackers": [
        {
            "name": "示例Tracker",
            "domain": "tracker.example.com",
            "enable": True,
            "ip": DEFAULT_CLOUDFLARE_IP
        }
    ],
    # 外部 hosts 源预装但全部关闭：新部署不会生成 MergedHosts，用户需在 UI「Hosts源」页手动勾选启用。
    # 清单见上方 HOSTS_SOURCE_PRESETS（深拷贝，避免运行时改动污染常量）。
    "hosts_sources": [dict(s) for s in HOSTS_SOURCE_PRESETS],
    "torrent_clients": [
        {
            "id": "qb_default",
            "name": "qBittorrent 默认",
            "type": "qbittorrent",
            "host": "localhost",
            "port": 8080,
            "username": "",
            "password": "",
            "api_key": "",
            "use_https": False,
            "enable": False
        },
        {
            "id": "tr_default",
            "name": "Transmission 默认",
            "type": "transmission",
            "host": "localhost",
            "port": 9091,
            "username": "",
            "password": "",
            "use_https": False,
            "path": "/transmission/rpc",
            "enable": False
        }
    ],
    "logging": {
        "level": "INFO",  # 日志记录级别：面板下拉框可改，重启后按此生效
    },
    "auth": {
        "enable": False,
        "username": "admin",
        "password_hash": "",
        "secret_key": ""
    }
}
