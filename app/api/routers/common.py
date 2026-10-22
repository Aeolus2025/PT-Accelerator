"""路由层共用的认证依赖。"""

from app.auth import get_current_user

__all__ = ["get_current_user"]
