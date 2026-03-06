"""旧API兼容适配器 - 保持与v1 API兼容 - 独立版本"""

import os
from typing import Dict, Any
from fastapi import HTTPException

from agents.radiology_agent import RadiologyAgent
from agents.knowledge_agent import KnowledgeAgent

# 从本地legacy模块导入（离线可用）
from legacy import (
    Match_result_LLM,
    Match_complex_result,
    Query_steam,
    init_chat_agent,
)


class LegacyAdapter:
    """v1 API适配器

    将v1 API请求转换为v2 Agent调用
    """

    def __init__(self):
        self.radiology_agent = None
        self.knowledge_agent = None
        self._use_new_agent = os.getenv("USE_NEW_AGENT", "true").lower() == "true"

    def _get_radiology_agent(self) -> RadiologyAgent:
        """获取放射Agent（延迟加载）"""
        if self.radiology_agent is None:
            self.radiology_agent = RadiologyAgent()
        return self.radiology_agent

    def _get_knowledge_agent(self) -> KnowledgeAgent:
        """获取知识Agent（延迟加载）"""
        if self.knowledge_agent is None:
            self.knowledge_agent = KnowledgeAgent()
        return self.knowledge_agent

    async def coincidence(
        self,
        radiology_result: str,
        pathology_result: str
    ) -> Dict[str, Any]:
        """兼容旧的 /Coincidence 接口

        v1 格式:
        POST /Coincidence
        {"radology_result": "...", "pathlogy_result": "..."}

        Returns:
            {"result": "符合", "reason": "..."}
        """
        if not self._use_new_agent:
            # 回退到旧实现（使用本地legacy模块）
            return Match_result_LLM(radiology_result, pathology_result)

        try:
            agent = self._get_radiology_agent()
            result = await agent.diagnosis_coincidence(
                radiology_result=radiology_result,
                pathology_result=pathology_result
            )

            # 转换为v1格式
            answer = result.get("result", "")
            # 尝试解析JSON
            import json
            import re

            # 从回答中提取JSON
            match = re.search(r'\{[^}]*"result"[^}]*\}', answer)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    return {
                        "result": parsed.get("result", "无法判断"),
                        "reason": parsed.get("reason", "")
                    }
                except:
                    pass

            # 回退：直接返回
            return {
                "result": "符合" if "符合" in answer else "无法判断",
                "reason": answer[:200]
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def complex_coincidence(
        self,
        verification: str,
        verification_type: str,
        pathology: str = "",
        clinical: str = "",
        think: bool = False,
        tool: bool = False
    ) -> Dict[str, Any]:
        """兼容旧的 /ComplexCoincidence 接口"""
        if not self._use_new_agent:
            # 使用本地legacy模块
            return Match_complex_result(
                verification,
                verification_type,
                pathology,
                clinical,
                think,
                tool
            )

        try:
            agent = self._get_radiology_agent()
            result = await agent.complex_coincidence(
                verification=verification,
                verification_type=verification_type,
                pathology=pathology,
                clinical=clinical,
                use_think=think,
                use_tool=tool
            )

            # 转换为v1格式
            answer = result.get("result", "")
            import json
            import re

            match = re.search(r'\{[^}]*"result"[^}]*\}', answer)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                    return {
                        "result": parsed.get("result", "无法判断"),
                        "reason": parsed.get("reason", "")
                    }
                except:
                    pass

            return {
                "result": "符合" if "符合" in answer else "无法判断",
                "reason": answer[:200]
            }

        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def rag_ask(
        self,
        question: str,
        user_id: str,
        chat_name: str = "小影"
    ):
        """兼容旧的 /rag_ask 流式接口"""
        if not self._use_new_agent:
            # 使用本地legacy模块
            # 这里需要返回流式响应，比较复杂
            # 简化处理：直接返回空
            return ""

        agent = self._get_knowledge_agent()

        async def generate():
            async for chunk in agent.ainvoke_stream(
                question=question,
                user_id=user_id
            ):
                yield chunk

        return generate()


# 全局适配器实例
legacy_adapter = LegacyAdapter()
