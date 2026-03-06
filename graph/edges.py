"""LangGraph边路由器 - 条件边逻辑"""

from typing import Literal
from graph.state import AgentState
from config.settings import settings


class EdgeRouter:
    """边路由器 - 决定工作流走向"""

    @staticmethod
    def route_by_complexity(state: AgentState) -> Literal["direct", "plan"]:
        """根据复杂度路由

        simple -> 直接回答
        moderate/complex -> 制定计划
        """
        complexity = state.get("complexity", "moderate")
        can_answer_directly = state.get("can_answer_directly", False)

        if complexity == "simple" or can_answer_directly:
            return "direct"
        return "plan"

    @staticmethod
    def should_continue_execution(state: AgentState) -> Literal["continue", "done"]:
        """决定是否继续执行

        还有未执行的步骤 -> continue
        所有步骤执行完成 -> done
        """
        current_step = state.get("current_step", 0)
        total_steps = state.get("total_steps", 0)

        if current_step < total_steps:
            return "continue"
        return "done"

    @staticmethod
    def should_retry(state: AgentState) -> Literal["retry", "finish", "escalate"]:
        """决定是否重试

        需要重试且未超过最大次数 -> retry
        成功完成 -> finish
        超过最大重试次数 -> escalate
        """
        should_retry = state.get("should_retry", False)
        retry_count = state.get("retry_count", 0)
        status = state.get("status", "running")

        if status == "completed":
            return "finish"

        if should_retry and retry_count < settings.max_retry_count:
            return "retry"

        if retry_count >= settings.max_retry_count:
            return "escalate"

        return "finish"

    @staticmethod
    def has_error(state: AgentState) -> Literal["error", "ok"]:
        """检查是否有错误"""
        status = state.get("status", "running")
        error_message = state.get("error_message")

        if status == "failed" or error_message:
            return "error"
        return "ok"
