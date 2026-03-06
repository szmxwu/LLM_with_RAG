"""放射诊断Agent - 专业处理放射质控任务"""

import asyncio
import json
import re
import time
from typing import AsyncGenerator, Dict, Any, Optional, Union
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from agents.base import BaseMedicalAgent
from graph.state import AgentState
from config.prompts import PromptTemplates
from config.settings import settings, ThinkingMode

# 从 legacy 模块导入成熟的诊断匹配逻辑
from legacy.llm_func import clean_sentence, Match_result_LLM, Match_complex_result
from legacy.keyword_extraction import get_orientation_position


class RadiologyAgent(BaseMedicalAgent):
    """放射诊断质控Agent

    专业能力：
    1. 放射-病理诊断符合率判断
    2. 患者历史检查分析
    3. 阅片要点提醒
    4. 诊断建议生成
    """

    def __init__(self):
        super().__init__(name="RadiologyAgent")

    def _build_graph(self) -> StateGraph:
        """构建放射Agent专用工作流"""
        workflow = StateGraph(AgentState)

        # 添加节点（复用基类节点）
        workflow.add_node("analyze_intent", self.nodes.analyze_intent)
        workflow.add_node("create_plan", self.nodes.create_plan)
        workflow.add_node("execute_tool", self.nodes.execute_tool)
        workflow.add_node("direct_answer", self.nodes.direct_answer)
        workflow.add_node("synthesize_answer", self.nodes.synthesize_answer)
        workflow.add_node("reflect", self.nodes.reflect)

        # 放射Agent专用的路由逻辑
        workflow.set_entry_point("analyze_intent")

        # 根据任务类型路由
        workflow.add_conditional_edges(
            "analyze_intent",
            self._route_radiology_task,
            {
                "diagnosis_match": "execute_tool",  # 直接执行匹配工具
                "patient_analysis": "create_plan",  # 需要规划
                "direct": "direct_answer",          # 直接回答
                "plan": "create_plan"               # 常规规划
            }
        )

        # 标准执行流程
        workflow.add_edge("create_plan", "execute_tool")

        workflow.add_conditional_edges(
            "execute_tool",
            self.router.should_continue_execution,
            {
                "continue": "execute_tool",
                "done": "synthesize_answer"
            }
        )

        workflow.add_edge("direct_answer", "reflect")
        workflow.add_edge("synthesize_answer", "reflect")

        workflow.add_conditional_edges(
            "reflect",
            self.router.should_retry,
            {
                "retry": "create_plan",
                "finish": END,
                "escalate": END
            }
        )

        return workflow.compile()

    def _route_radiology_task(self, state: AgentState) -> str:
        """放射任务专用路由"""
        question = state.get("question", "").lower()

        # 检测是否是诊断匹配任务
        match_keywords = ["符合", "对比", "病理", "诊断", "相符"]
        if any(kw in question for kw in match_keywords):
            # 检查是否包含必要的参数
            if "放射" in question or "ct" in question or "mr" in question:
                return "diagnosis_match"

        # 检测是否是患者分析任务
        analysis_keywords = ["患者", "病史", "历史", "分析", "阅片"]
        if any(kw in question for kw in analysis_keywords):
            return "patient_analysis"

        # 默认使用基类路由
        return self.router.route_by_complexity(state)

    async def diagnosis_coincidence(
        self,
        radiology_result: str,
        pathology_result: str,
        session_id: Optional[str] = None,
        thinking_mode: Optional[Union[ThinkingMode, str]] = None
    ) -> Dict[str, Any]:
        """诊断符合率判断 - 复用V1版本的成熟逻辑

        流程：
        1. 清洗文本（clean_sentence）
        2. 规则算法提取部位方位（get_orientation_position）
        3. 规则判断排除无法判断的情况（器官无交集、信息不全）
        4. LLM判断（仅在规则无法判断时调用）

        Args:
            radiology_result: 放射诊断结果
            pathology_result: 病理诊断结果
            session_id: 会话ID
            thinking_mode: 思考模式 (ThinkingMode枚举或字符串: no_think/think/deep_think)

        Returns:
            {"result": "符合/基本符合/无法判断", "reason": "判断理由"}
        """
        # 直接复用V1版本的成熟逻辑
        try:
            # 使用线程池在后台执行同步的V1逻辑
            import asyncio
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: Match_result_LLM(radiology_result, pathology_result)
            )
            return result
        except Exception as e:
            # 降级处理：直接返回错误信息
            return {
                "result": "无法判断",
                "reason": f"诊断匹配过程出错: {str(e)}"
            }

    async def patient_analysis(
        self,
        patient_history: str,
        modality: str,
        study_part: str,
        previous_reports: str = "",
        session_id: Optional[str] = None,
        thinking_mode: Optional[Union[ThinkingMode, str]] = None
    ) -> AsyncGenerator[str, None]:
        """患者检查分析

        Args:
            patient_history: 患者历史检查
            modality: 检查类型
            study_part: 检查部位
            previous_reports: 近期报告
            session_id: 会话ID
            thinking_mode: 思考模式 (ThinkingMode枚举或字符串: no_think/think/deep_think)
        """
        prompt = PromptTemplates.get_prompt(
            "PATIENT_ANALYSIS",
            history=patient_history,
            modality=modality,
            studypart=study_part,
            recent_reports=previous_reports
        )

        # 确保 thinking_mode 是 ThinkingMode 枚举类型
        effective_thinking_mode = None
        if thinking_mode is not None:
            if isinstance(thinking_mode, str):
                effective_thinking_mode = ThinkingMode(thinking_mode)
            else:
                effective_thinking_mode = thinking_mode

        async for chunk in self.ainvoke_stream(prompt, session_id, thinking_mode=effective_thinking_mode):
            yield chunk

    async def complex_coincidence(
        self,
        verification: str,
        verification_type: str,
        pathology: str = "",
        clinical: str = "",
        use_think: bool = False,
        use_tool: bool = False,
        session_id: Optional[str] = None,
        thinking_mode: Optional[Union[ThinkingMode, str]] = None
    ) -> Dict[str, Any]:
        """复杂诊断符合率判断（支持多模态）- 复用V1版本的成熟逻辑

        Args:
            verification: 待验证的诊断
            verification_type: 验证类型(CT/MR/US/ES等)
            pathology: 病理诊断
            clinical: 出院小结
            use_think: 是否使用长思考
            use_tool: 是否使用工具
            session_id: 会话ID
            thinking_mode: 思考模式（兼容参数，实际由use_think控制）

        Returns:
            {"result": "符合/基本符合/无法判断", "reason": "判断理由"}
        """
        # 直接复用V1版本的成熟逻辑
        try:
            # 使用线程池在后台执行同步的V1逻辑
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                lambda: Match_complex_result(
                    Verification=verification,
                    verification_type=verification_type,
                    Pathology=pathology,
                    Clinical=clinical,
                    think=use_think,
                    tool=use_tool
                )
            )
            return result
        except Exception as e:
            # 降级处理
            return {
                "result": "无法判断",
                "reason": f"复杂诊断匹配过程出错: {str(e)}"
            }
