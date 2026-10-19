# This file defines the data models used in the application.
# Add your Pydantic models or other data structures here.

from pydantic import BaseModel, Field
from typing import List, Optional

class Tracker(BaseModel):
    name: str
    domain: str
    ip: Optional[str] = None
    enable: bool = True

class HostsSource(BaseModel):
    name: str
    url: str
    enable: bool = True

class CloudflareConfig(BaseModel):
    enable: bool = True
    cron: str = "0 0 * * *"
    # Add other Cloudflare related fields if necessary

class TorrentClientConfig(BaseModel):
    id: str  # 客户端唯一标识符
    name: str  # 客户端显示名称
    type: str # e.g., 'qbittorrent', 'transmission'
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    use_https: bool = False
    path: Optional[str] = "/transmission/rpc"  # Transmission特有字段
    api_key: Optional[str] = None  # qBittorrent 5.2+ WebUI API Key，优先于用户名/密码
    enable: bool = True

class BatchAddDomainsRequest(BaseModel):
    domains: List[str]

# You might need to add other models based on your application's needs

class AuthConfig(BaseModel):
    enable: bool = False
    username: str = "admin"
    password_hash: Optional[str] = ""
    secret_key: Optional[str] = ""

class Token(BaseModel):
    access_token: str
    token_type: str

class User(BaseModel):
    username: str
    is_authenticated: bool = True