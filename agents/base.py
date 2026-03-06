"""Agent基类 - 基于LangGraph - 支持思考强度控制"""

import re
import uuid
from typing import AsyncGenerator, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from config.settings import settings, ThinkingMode
from graph.state import AgentState
from graph.nodes import AgentNodes
from graph.edges import EdgeRouter
from tools.registry import get_registry


def clean_thinking_tags(content: str) -> str:
    """清理思考过程标签 <think>...</think>"""
    if not content:
        return content
    cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
    return cleaned.strip()


class BaseMedicalAgent:
    """医学Agent基类 - 基于LangGraph实现 - 支持思考强度控制"""

    def __init__(
        self,
        name: str = "MedicalAgent",
        default_thinking_mode: Optional[ThinkingMode] = None
    ):
        self.name = name
        self.default_thinking_mode = default_thinking_mode or settings.default_thinking_mode
        self.llm = ChatOpenAI(
            base_url=settings.xinference_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=0.3,
            max_tokens=4096,
        )
        self.tool_registry = get_registry()
        self.nodes = AgentNodes(self.tool_registry)
        self.router = EdgeRouter()
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """构建LangGraph工作流

        工作流结构：
        1. analyze_intent - 分析意图和复杂度
        2. [分支] simple -> direct_answer
           [分支] complex -> create_plan -> execute_loop
        3. synthesize_answer - 合成答案
        4. reflect - 反思结果
        """
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("analyze_intent", self.nodes.analyze_intent)
        workflow.add_node("create_plan", self.nodes.create_plan)
        workflow.add_node("execute_tool", self.nodes.execute_tool)
        workflow.add_node("direct_answer", self.nodes.direct_answer)
        workflow.add_node("synthesize_answer", self.nodes.synthesize_answer)
        workflow.add_node("reflect", self.nodes.reflect)

        # 设置入口点
        workflow.set_entry_point("analyze_intent")

        # 意图分析后的路由
        workflow.add_conditional_edges(
            "analyze_intent",
            self.router.route_by_complexity,
            {
                "direct": "direct_answer",
                "plan": "create_plan"
            }
        )

        # 计划后执行
        workflow.add_edge("create_plan", "execute_tool")

        # 工具执行循环
        workflow.add_conditional_edges(
            "execute_tool",
            self.router.should_continue_execution,
            {
                "continue": "execute_tool",  # 继续执行下一步
                "done": "synthesize_answer"  # 执行完成，合成答案
            }
        )

        # 直接回答和合成答案后都进入反思
        workflow.add_edge("direct_answer", "reflect")
        workflow.add_edge("synthesize_answer", "reflect")

        # 反思后的路由
        workflow.add_conditional_edges(
            "reflect",
            self.router.should_retry,
            {
                "retry": "create_plan",  # 重新规划执行
                "finish": END,           # 正常结束
                "escalate": END          # 升级处理（也结束）
            }
        )

        return workflow.compile()

    async def ainvoke(
        self,
        question: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        thinking_mode: Optional[ThinkingMode] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """调用Agent处理请求

        Args:
            question: 用户问题
            session_id: 会话ID
            user_id: 用户ID
            thinking_mode: 思考模式，默认使用Agent的default_thinking_mode

        Yields:
            状态更新事件
        """
        # 生成会话ID
        if session_id is None:
            session_id = str(uuid.uuid4())
        if user_id is None:
            user_id = "anonymous"

        # 确定思考模式
        effective_thinking_mode = thinking_mode or self.default_thinking_mode

        # 初始化状态
        initial_state: AgentState = {
            "session_id": session_id,
            "user_id": user_id,
            "question": question,
            "complexity": "",
            "need_rag": True,
            "can_answer_directly": False,
            "suggested_tools": [],
            "suggested_thinking_mode": "",
            "thinking_mode": effective_thinking_mode.value,
            "plan": [],
            "current_step": 0,
            "total_steps": 0,
            "tool_results": [],
            "intermediate_outputs": {},
            "reflection_notes": [],
            "retry_count": 0,
            "should_retry": False,
            "final_answer": None,
            "status": "running",
            "error_message": None
        }

        # 执行工作流
        async for event in self.graph.astream(initial_state):
            yield event

    async def ainvoke_stream(
        self,
        question: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        thinking_mode: Optional[ThinkingMode] = None
    ) -> AsyncGenerator[str, None]:
        """流式调用，只返回最终答案的文本片段

        Args:
            question: 用户问题
            session_id: 会话ID
            user_id: 用户ID
            thinking_mode: 思考模式
        """
        final_answer = ""

        async for event in self.ainvoke(question, session_id, user_id, thinking_mode):
            # 只关注最终答案的更新
            if isinstance(event, dict):
                # LangGraph返回的是 {node_name: state} 格式
                for node_name, state in event.items():
                    if isinstance(state, dict) and "final_answer" in state:
                        new_answer = state["final_answer"]
                        # 清理思考过程标签
                        new_answer = clean_thinking_tags(new_answer)
                        if new_answer and new_answer != final_answer:
                            # 计算新增的部分
                            if new_answer.startswith(final_answer):
                                delta = new_answer[len(final_answer):]
                                yield delta
                            else:
                                yield new_answer
                            final_answer = new_answer
