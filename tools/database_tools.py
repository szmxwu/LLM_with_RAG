"""数据库工具实现 - 独立版本"""

from typing import Dict, Any
from pydantic import Field
from tools.base import BaseTool, ToolResult, ToolParameters
from config.settings import settings

# 从本地legacy模块导入（离线可用）
from legacy import get_LLM_SQL


class SQLQueryParams(ToolParameters):
    """SQL查询参数"""
    question: str = Field(..., description="自然语言问题")


class SQLQueryTool(BaseTool):
    """自然语言转SQL查询工具"""

    name = "sql_query"
    description = """将自然语言问题转换为SQL并执行，用于查询统计数据。
    适用于：
    - 检查数量统计
    - 设备使用率查询
    - 科室工作量统计
    """
    parameters_schema = SQLQueryParams
    timeout = 60.0

    async def _execute(self, params: Dict) -> ToolResult:
        """执行SQL查询"""
        try:
            # 复用旧版逻辑
            from llm_func import get_LLM_SQL

            sql_str, viz_config, df = get_LLM_SQL(params["question"])

            # 格式化结果
            data_dict = df.to_dict(orient='records') if df is not None and not df.empty else []

            return ToolResult(
                success=True,
                data={
                    "sql": sql_str,
                    "data": data_dict,
                    "row_count": len(data_dict),
                    "visualization": viz_config
                },
                metadata={
                    "has_data": len(data_dict) > 0
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"SQL查询失败: {str(e)}"
            )


class PatientHistoryParams(ToolParameters):
    """患者历史查询参数"""
    patient_id: str = Field(..., description="患者ID")
    modality: str = Field(default="", description="检查类型筛选")
    date_range: str = Field(default="", description="日期范围")


class PatientHistoryTool(BaseTool):
    """患者历史检查查询工具"""

    name = "patient_history"
    description = "查询患者的历史检查记录"
    parameters_schema = PatientHistoryParams
    timeout = 30.0

    async def _execute(self, params: Dict) -> ToolResult:
        """执行患者历史查询"""
        # TODO: 实现患者历史查询
        # 这需要访问数据库，可能需要在llm_func中添加新函数
        return ToolResult(
            success=True,
            data={"message": "患者历史查询功能开发中"},
            metadata={"status": "todo"}
        )
