"""LangGraph节点实现 - 核心工作流节点 - 支持思考强度控制"""

import json
import re
import time
import asyncio
from typing import Dict, Any, List, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config.settings import settings, ThinkingMode
from config.prompts import PromptTemplates
from graph.state import AgentState, ToolExecutionResult
from tools.registry import ToolRegistry


def clean_thinking_tags(content: str) -> str:
    """清理思考过程标签 <think>...</think>

    Args:
        content: LLM返回的原始内容

    Returns:
        清理后的内容
    """
    if not content:
        return content
    # 使用正则表达式移除think标签及其内容
    cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    # 清理多余的空白字符
    cleaned = cleaned.strip()
    return cleaned


class AgentNodes:
    """Agent工作流节点 - 支持/no_think和/think思考强度控制"""

    def __init__(self, tool_registry: Optional[ToolRegistry] = None):
        self.llm = ChatOpenAI(
            base_url=settings.xinference_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=0.3,
            max_tokens=4096,
        )
        self.tool_registry = tool_registry or ToolRegistry()

    def _get_effective_thinking_mode(self, state: AgentState) -> ThinkingMode:
        """获取有效的思考模式

        优先级：
        1. 状态中已设置的thinking_mode
        2. 意图分析建议的suggested_thinking_mode
        3. 根据复杂度自动选择
        """
        # 如果状态中已经设置了思考模式，直接使用
        if state.get("thinking_mode"):
            mode_str = state["thinking_mode"]
            try:
                return ThinkingMode(mode_str)
            except ValueError:
                pass

        # 使用意图分析建议的思考模式
        if state.get("suggested_thinking_mode"):
            mode_str = state["suggested_thinking_mode"]
            try:
                return ThinkingMode(mode_str)
            except ValueError:
                pass

        # 根据复杂度自动选择
        complexity = state.get("complexity", "moderate")
        return PromptTemplates.auto_select_thinking_mode(
            complexity=complexity,
            task_type="general"
        )

    # ==================== 意图分析节点 ====================

    async def analyze_intent(self, state: AgentState) -> Dict[str, Any]:
        """分析用户意图和复杂度，同时确定思考模式"""
        # 使用标准思考模式进行意图分析（需要一定推理能力）
        try:
            prompt = PromptTemplates.get_prompt(
                "INTENT_ANALYSIS",
                thinking_mode=ThinkingMode.THINK,  # 意图分析需要推理
                question=state["question"]
            )

            response = await self.llm.ainvoke([
                SystemMessage(content="你是一个智能任务分析器。"),
                HumanMessage(content=prompt)
            ])

            # 解析JSON响应
            content = response.content
            # 提取JSON部分
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            analysis = json.loads(content.strip())

            complexity = analysis.get("complexity", "moderate")
            suggested_thinking = analysis.get("suggested_thinking_mode", "think")

            # 确定最终的思考模式
            final_thinking_mode = PromptTemplates.auto_select_thinking_mode(
                complexity=complexity,
                task_type="general"
            )

            # 如果LLM明确建议了思考模式，使用建议的
            if suggested_thinking in ["no_think", "think", "deep_think"]:
                final_thinking_mode = ThinkingMode(suggested_thinking)

            return {
                "complexity": complexity,
                "need_rag": analysis.get("need_rag", True),
                "can_answer_directly": analysis.get("can_answer_directly", False),
                "suggested_tools": analysis.get("suggested_tools", []),
                "suggested_thinking_mode": suggested_thinking,
                "thinking_mode": final_thinking_mode.value,
            }

        except Exception as e:
            # 降级处理：默认中等复杂度，标准思考模式
            return {
                "complexity": "moderate",
                "need_rag": True,
                "can_answer_directly": False,
                "suggested_tools": ["rag_search"],
                "suggested_thinking_mode": "think",
                "thinking_mode": ThinkingMode.THINK.value,
                "error_message": f"意图分析失败: {str(e)}"
            }

    # ==================== 任务规划节点 ====================

    async def create_plan(self, state: AgentState) -> Dict[str, Any]:
        """创建执行计划"""
        if state["complexity"] == "simple":
            # 简单任务无需计划，直接回答
            return {
                "plan": [],
                "total_steps": 0,
                "can_answer_directly": True
            }

        try:
            # 获取当前思考模式
            thinking_mode = self._get_effective_thinking_mode(state)

            # 获取工具描述
            tool_descriptions = self.tool_registry.get_descriptions()

            prompt = PromptTemplates.get_prompt(
                "TASK_PLANNING",
                thinking_mode=thinking_mode,
                question=state["question"],
                complexity=state["complexity"],
                tool_descriptions=tool_descriptions
            )

            response = await self.llm.ainvoke([
                SystemMessage(content="你是一个任务规划专家。"),
                HumanMessage(content=prompt)
            ])

            # 解析JSON响应
            content = response.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            plan_data = json.loads(content.strip())
            steps = plan_data.get("steps", [])

            return {
                "plan": steps,
                "total_steps": len(steps),
                "current_step": 0,
                "can_answer_directly": False
            }

        except Exception as e:
            # 降级处理：简单RAG查询计划
            return {
                "plan": [{
                    "id": 1,
                    "description": "直接检索知识库回答",
                    "tool": "rag_search",
                    "params": {"query": state["question"], "dataset": "放射学", "top_k": 8},
                    "depends_on": [],
                    "can_parallel": False
                }],
                "total_steps": 1,
                "current_step": 0,
                "can_answer_directly": False,
                "error_message": f"规划失败，使用默认计划: {str(e)}"
            }

    # ==================== 工具执行节点 ====================

    async def execute_tool(self, state: AgentState) -> Dict[str, Any]:
        """执行当前步骤的工具"""
        current_step_idx = state["current_step"]
        plan = state["plan"]

        if current_step_idx >= len(plan):
            return {"current_step": current_step_idx}

        step = plan[current_step_idx]
        tool_name = step.get("tool", "rag_search")
        params = step.get("params", {})

        # 渲染模板参数（支持从状态中引用）
        params = self._render_params(params, state)

        start_time = time.time()

        try:
            tool = self.tool_registry.get_tool(tool_name)
            if not tool:
                raise ValueError(f"未知工具: {tool_name}")

            result = await tool.execute(params)
            latency = (time.time() - start_time) * 1000

            tool_result = ToolExecutionResult(
                tool_name=tool_name,
                success=result.success,
                data=result.data,
                latency_ms=latency,
                error_message=result.error_message,
                metadata=result.metadata
            )

            return {
                "tool_results": [tool_result.__dict__],
                "current_step": current_step_idx + 1,
                "intermediate_outputs": {
                    **state.get("intermediate_outputs", {}),
                    f"step_{current_step_idx}": result.data if result.success else None
                }
            }

        except Exception as e:
            latency = (time.time() - start_time) * 1000
            tool_result = ToolExecutionResult(
                tool_name=tool_name,
                success=False,
                data=None,
                latency_ms=latency,
                error_message=str(e)
            )

            return {
                "tool_results": [tool_result.__dict__],
                "current_step": current_step_idx + 1,
                "status": "failed",
                "error_message": str(e)
            }

    def _render_params(self, params: Dict, state: AgentState) -> Dict:
        """渲染参数模板"""
        rendered = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("$"):
                # 从状态中引用
                state_key = value[1:]
                rendered[key] = state.get(state_key, value)
            else:
                rendered[key] = value
        return rendered

    # ==================== 直接回答节点 ====================

    async def direct_answer(self, state: AgentState) -> Dict[str, Any]:
        """直接回答（无需工具调用）"""
        try:
            # 获取思考模式
            thinking_mode = self._get_effective_thinking_mode(state)

            # 构建带思考指令的prompt
            thinking_instruction = PromptTemplates.get_thinking_instruction(thinking_mode)
            prompt = f"{thinking_instruction}\n\n用户问题：{state['question']}"

            response = await self.llm.ainvoke([
                SystemMessage(content="你是放射科医生的专业知识助手，叫小语。"),
                HumanMessage(content=prompt)
            ])

            # 清理思考过程标签
            cleaned_content = clean_thinking_tags(response.content)

            return {
                "final_answer": cleaned_content,
                "status": "completed"
            }

        except Exception as e:
            return {
                "final_answer": f"抱歉，回答生成失败: {str(e)}",
                "status": "failed",
                "error_message": str(e)
            }

    # ==================== 答案合成节点 ====================

    async def synthesize_answer(self, state: AgentState) -> Dict[str, Any]:
        """合成最终答案"""
        tool_results = state.get("tool_results", [])

        # 构建上下文
        context_parts = []
        for i, result in enumerate(tool_results):
            if result.get("success"):
                context_parts.append(f"[来源{i+1}] {result.get('tool_name')}:\n{result.get('data', '')}")

        context = "\n\n".join(context_parts)

        try:
            # 获取思考模式
            thinking_mode = self._get_effective_thinking_mode(state)

            prompt = PromptTemplates.get_prompt(
                "ANSWER_SYNTHESIS",
                thinking_mode=thinking_mode,
                question=state["question"],
                context=context
            )

            response = await self.llm.ainvoke([
                SystemMessage(content="你是放射科医生的专业知识助手，叫小语。"),
                HumanMessage(content=prompt)
            ])

            # 清理思考过程标签
            cleaned_content = clean_thinking_tags(response.content)

            return {
                "final_answer": cleaned_content,
                "status": "completed"
            }

        except Exception as e:
            return {
                "final_answer": f"答案合成失败: {str(e)}",
                "status": "failed",
                "error_message": str(e)
            }

    # ==================== 反思节点 ====================

    async def reflect(self, state: AgentState) -> Dict[str, Any]:
        """反思执行结果 - 可能需要调整为深度思考模式"""
        # 如果已经失败，直接返回
        if state.get("status") == "failed":
            # 如果之前的思考模式不够，升级为深度思考
            current_mode = state.get("thinking_mode", "think")
            if current_mode == "no_think":
                return {
                    "should_retry": state["retry_count"] < settings.max_retry_count,
                    "retry_count": state["retry_count"] + 1,
                    "thinking_mode": ThinkingMode.THINK.value,  # 升级思考模式
                    "reflection_notes": ["执行失败，升级为标准思考模式重试"]
                }
            elif current_mode == "think":
                return {
                    "should_retry": state["retry_count"] < settings.max_retry_count,
                    "retry_count": state["retry_count"] + 1,
                    "thinking_mode": ThinkingMode.DEEP_THINK.value,  # 升级为深度思考
                    "reflection_notes": ["执行失败，升级为深度思考模式重试"]
                }

            return {
                "should_retry": state["retry_count"] < settings.max_retry_count,
                "retry_count": state["retry_count"] + 1
            }

        # 简单检查：是否有工具执行失败
        failed_tools = [
            r for r in state.get("tool_results", [])
            if not r.get("success")
        ]

        if failed_tools and state["retry_count"] < settings.max_retry_count:
            # 根据失败情况调整思考模式
            current_mode = state.get("thinking_mode", "think")
            new_mode = current_mode

            if current_mode == "no_think":
                new_mode = ThinkingMode.THINK.value
            elif current_mode == "think" and state["retry_count"] >= 1:
                new_mode = ThinkingMode.DEEP_THINK.value

            return {
                "should_retry": True,
                "retry_count": state["retry_count"] + 1,
                "thinking_mode": new_mode,
                "reflection_notes": [f"工具执行失败: {f.get('error_message')}" for f in failed_tools]
            }

        return {
            "should_retry": False,
            "status": "completed"
        }
