"""工具注册中心"""

from typing import Dict, List, Optional, Type
from tools.base import BaseTool
import json


class ToolRegistry:
    """工具注册中心 - 统一管理所有工具"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
        self._descriptions[tool.name] = tool.description

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取工具实例"""
        return self._tools.get(name)

    def list_tools(self) -> List[str]:
        """列出所有可用工具"""
        return list(self._tools.keys())

    def get_descriptions(self) -> str:
        """获取所有工具描述（用于Prompt）"""
        lines = []
        for name, tool in self._tools.items():
            lines.append(f"- {name}: {tool.description}")
        return "\n".join(lines)

    def get_openai_schemas(self) -> List[Dict]:
        """获取OpenAI Function Calling格式的schemas"""
        return [tool.get_schema() for tool in self._tools.values()]

    def get_tool_schemas(self) -> Dict[str, Dict]:
        """获取工具schema字典"""
        return {name: tool.get_schema() for name, tool in self._tools.items()}


# 全局注册中心实例
_global_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """获取全局工具注册中心"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
        # 自动注册默认工具
        _register_default_tools(_global_registry)
    return _global_registry


def _register_default_tools(registry: ToolRegistry):
    """注册默认工具"""
    # 延迟导入避免循环依赖
    from tools.ragflow_tools import RAGSearchTool, DiagnosisMatchTool
    from tools.database_tools import SQLQueryTool

    registry.register(RAGSearchTool())
    registry.register(DiagnosisMatchTool())
    registry.register(SQLQueryTool())
