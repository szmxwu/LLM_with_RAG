"""API模块 - FastAPI路由和适配器"""

from .routes import router
from .adapter import LegacyAdapter

__all__ = ["router", "LegacyAdapter"]
