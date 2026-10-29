from fastapi import Request
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import os
import secrets
import yaml
import logging
from typing import Optional
from app.models import User

# 配置日志
logger = logging.getLogger(__name__)

# 密码处理上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Session 签名器
session_serializer = None

# 配置路径
CONFIG_PATH = "config/config.yaml"

def init_session_serializer(secret_key: str):
    """初始化session签名器"""
    global session_serializer
    session_serializer = URLSafeTimedSerializer(secret_key)

def verify_password(plain_password, hashed_password):
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """生成密码哈希"""
    return pwd_context.hash(password)

def generate_initial_password(username: str) -> str:
    """生成初始密码并打印到日志，返回明文供调用方写入 password_hash。

    启动兜底与「启用认证」保存两处共用，避免打印格式和密码格式不一致。
    """
    password = secrets.token_urlsafe(12)

    logger.warning("[AUTH] 未设置管理员密码，已生成初始密码 用户名=%s 密码=%s", username, password)
    logger.warning("[AUTH] 登录后请立即在「安全与认证」中修改密码")
    return password

async def get_current_user(request: Request) -> Optional[User]:
    """获取当前登录用户"""
    # 加载当前配置以检查认证是否启用
    config = load_current_config()
    
    # 如果未启用认证，返回游客用户
    if not config.get("auth", {}).get("enable", False):
        return User(username="guest", is_authenticated=False)
    
    # 检查session中的用户信息
    user_data = request.session.get("user")
    if not user_data:
        return None
    
    try:
        # 验证session token  
        if session_serializer and user_data.get("token"):
            username = session_serializer.loads(user_data.get("token", ""), max_age=3600*24*7)  # 7天有效期
            if username == user_data.get("username"):
                return User(username=username, is_authenticated=True)
        elif user_data.get("username"):
            # 向后兼容没有token的旧session格式
            return User(username=user_data.get("username"), is_authenticated=True)
    except (SignatureExpired, BadTimeSignature):
        # Token过期或无效，清除session
        request.session.pop("user", None)
        return None
    
    return None

def load_current_config():
    """加载当前配置文件"""
    if os.path.exists(CONFIG_PATH):
        try:
            # 优先UTF-8，失败回退GBK/GB18030
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
                # 确保配置中有auth部分（UTF-8成功路径也需保证）
                if "auth" not in config:
                    config["auth"] = {}
                return config
            except UnicodeDecodeError:
                try:
                    with open(CONFIG_PATH, 'r', encoding='gbk') as f:
                        config = yaml.safe_load(f) or {}
                except UnicodeDecodeError:
                    with open(CONFIG_PATH, 'r', encoding='gb18030') as f:
                        config = yaml.safe_load(f) or {}
                # 确保配置中有auth部分
                if "auth" not in config:
                    config["auth"] = {}
                return config
        except Exception as e:
            logger.exception("[AUTH] 加载配置文件失败: %s", e)
            return {"auth": {}}
    return {"auth": {}}

def create_user_session(username: str) -> dict:
    """创建用户session数据"""
    if session_serializer:
        token = session_serializer.dumps(username)
        return {
            "username": username,
            "token": token
        }
    return {"username": username}

def reload_global_config():
    """重新加载认证配置，确保更改立即生效。

    配置本身以磁盘为准，这里只需要在 secret_key 变化时重建 session 序列化器。
    """
    try:
        # 重新加载当前配置
        new_config = load_current_config()

        # 如果secret_key发生变化，重新初始化session序列化器
        if new_config.get("auth", {}).get("secret_key"):
            init_session_serializer(new_config["auth"]["secret_key"])
            
        logger.info("[AUTH] 全局配置已重新加载，认证配置变更立即生效")
        return True
    except Exception as e:
        logger.exception("[AUTH] 重新加载全局配置失败: %s", e)
        return False 