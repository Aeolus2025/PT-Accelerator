"""全局路径与默认值的唯一来源。

各处不要再自行写字面量：改一处就要能生效，否则不同模块的默认值会悄悄漂移。
"""

CONFIG_DIR = "config"
CONFIG_PATH = "config/config.yaml"

# 未优选到 IP 时写入 hosts 的兜底地址
DEFAULT_CLOUDFLARE_IP = "104.16.91.215"

# 读取配置时依次尝试的编码：Windows 上手工保存的配置可能是 GBK
CONFIG_ENCODINGS = ("utf-8", "gbk", "gb18030")
