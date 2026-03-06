"""RAGFlow工具实现 - 独立版本"""

import os
from typing import Dict, Any, Optional
from pydantic import Field
from tools.base import BaseTool, ToolResult, ToolParameters
from config.settings import settings

# 从本地legacy模块导入（离线可用）
from legacy import (
    Retrieve_chunks,
    Match_result_LLM,
    Match_complex_result,
)


class RAGSearchParams(ToolParameters):
    """RAG搜索参数"""
    query: str = Field(..., description="搜索查询")
    dataset: str = Field(default="放射学", description="知识库名称")
    top_k: int = Field(default=8, description="返回结果数量")


class RAGSearchTool(BaseTool):
    """RAG知识库检索工具"""

    name = "rag_search"
    description = """从医学知识库检索专业信息。适用于：
    - 查询疾病影像学表现
    - 获取诊断标准
    - 检索扫描技术规范
    """
    parameters_schema = RAGSearchParams
    timeout = 30.0

    def __init__(self):
        super().__init__()
        self._client = None

    def _get_client(self):
        """获取RAGFlow客户端（延迟加载）"""
        if self._client is None:
            try:
                from ragflow_sdk import RAGFlow
                self._client = RAGFlow(
                    api_key=settings.ragflow_api_key,
                    base_url=settings.ragflow_url
                )
            except Exception as e:
                print(f"RAGFlow客户端初始化失败: {e}")
        return self._client

    async def _execute(self, params: Dict) -> ToolResult:
        """执行RAG搜索"""
        try:
            # 使用本地legacy模块的SDK进行检索
            chunks = Retrieve_chunks(
                question=params["query"],
                dataset_name=params["dataset"],
                document_name="",
                top_n=params["top_k"]
            )

            # 格式化结果
            results = []
            for chunk in chunks:
                results.append({
                    "content": chunk.content,
                    "document_name": chunk.document_name,
                    "document_id": chunk.document_id if hasattr(chunk, 'document_id') else None,
                    "image_id": chunk.image_id if hasattr(chunk, 'image_id') else None,
                    "positions": chunk.positions if hasattr(chunk, 'positions') else [],
                    "similarity": chunk.similarity if hasattr(chunk, 'similarity') else 0.0
                })

            return ToolResult(
                success=True,
                data={
                    "chunks": results,
                    "total_found": len(results),
                    "has_images": any(r.get("image_id") for r in results)
                },
                metadata={
                    "dataset": params["dataset"],
                    "query": params["query"]
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"RAG搜索失败: {str(e)}"
            )


class DiagnosisMatchParams(ToolParameters):
    """诊断匹配参数"""
    radiology_result: str = Field(..., description="放射诊断结论")
    pathology_result: str = Field(..., description="病理诊断结论")


class DiagnosisMatchTool(BaseTool):
    """放射-病理诊断匹配工具"""

    name = "diagnosis_match"
    description = "判断放射诊断与病理诊断是否相符，返回符合率评估"
    parameters_schema = DiagnosisMatchParams
    timeout = 45.0

    async def _execute(self, params: Dict) -> ToolResult:
        """执行诊断匹配"""
        try:
            # 使用本地legacy模块的逻辑
            result = Match_result_LLM(
                radology_result=params["radiology_result"],
                pathlogy_result=params["pathology_result"]
            )

            return ToolResult(
                success=True,
                data=result,
                metadata={"match_type": "radiology_pathology"}
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"诊断匹配失败: {str(e)}"
            )


class ComplexDiagnosisParams(ToolParameters):
    """复杂诊断匹配参数"""
    verification: str = Field(..., description="待验证的诊断")
    verification_type: str = Field(..., description="验证类型(CT/MR/US/ES等)")
    pathology: str = Field(default="", description="病理诊断")
    clinical: str = Field(default="", description="出院小结")
    use_think: bool = Field(default=False, description="是否使用长思考")
    use_tool: bool = Field(default=False, description="是否使用工具")


class ComplexDiagnosisMatchTool(BaseTool):
    """复杂诊断匹配工具（支持多模态对比）"""

    name = "complex_diagnosis_match"
    description = "判断放射/超声/内镜诊断与金标准诊断(病理/出院小结)是否相符"
    parameters_schema = ComplexDiagnosisParams
    timeout = 60.0

    async def _execute(self, params: Dict) -> ToolResult:
        """执行复杂诊断匹配"""
        try:
            result = Match_complex_result(
                Verification=params["verification"],
                verification_type=params["verification_type"],
                Pathology=params.get("pathology", ""),
                Clinical=params.get("clinical", ""),
                think=params.get("use_think", False),
                tool=params.get("use_tool", False)
            )

            return ToolResult(
                success=True,
                data=result,
                metadata={
                    "verification_type": params["verification_type"],
                    "has_pathology": bool(params.get("pathology")),
                    "has_clinical": bool(params.get("clinical"))
                }
            )

        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"复杂诊断匹配失败: {str(e)}"
            )
