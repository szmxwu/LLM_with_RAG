"""知识问答Agent - 处理医学知识检索问答"""

from typing import AsyncGenerator, Optional
from langgraph.graph import StateGraph, END

from agents.base import BaseMedicalAgent
from graph.state import AgentState


class KnowledgeAgent(BaseMedicalAgent):
    """医学知识问答Agent

    专业能力：
    1. 医学知识库检索问答
    2. 疾病影像学表现查询
    3. 扫描技术规范查询
    4. 鉴别诊断建议
    """

    def __init__(self):
        super().__init__(name="KnowledgeAgent")

    def _build_graph(self) -> StateGraph:
        """构建知识Agent工作流

        知识Agent特点：
        - 默认使用RAG搜索
        - 简单问题直接回答
        - 复杂问题拆分后并行查询
        """
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("analyze_intent", self.nodes.analyze_intent)
        workflow.add_node("create_plan", self.nodes.create_plan)
        workflow.add_node("execute_tool", self.nodes.execute_tool)
        workflow.add_node("direct_answer", self.nodes.direct_answer)
        workflow.add_node("synthesize_answer", self.nodes.synthesize_answer)
        workflow.add_node("reflect", self.nodes.reflect)

        # 设置入口
        workflow.set_entry_point("analyze_intent")

        # 简单问题直接回答，复杂问题使用RAG
        workflow.add_conditional_edges(
            "analyze_intent",
            self._route_knowledge_task,
            {
                "direct": "direct_answer",
                "rag_simple": "execute_tool",  # 单次RAG查询
                "rag_complex": "create_plan"   # 多步骤RAG查询
            }
        )

        # RAG简单查询（单步）
        # 直接执行工具，不需要复杂规划
        workflow.add_edge("execute_tool", "synthesize_answer")

        # RAG复杂查询（多步）
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

    def _route_knowledge_task(self, state: AgentState) -> str:
        """知识任务路由"""
        complexity = state.get("complexity", "moderate")
        need_rag = state.get("need_rag", True)

        # 不需要RAG，直接回答
        if not need_rag:
            return "direct"

        # 简单问题，单次RAG查询
        if complexity == "simple":
            # 自动创建单步计划
            state["plan"] = [{
                "id": 1,
                "description": "检索医学知识库",
                "tool": "rag_search",
                "params": {
                    "query": state.get("question", ""),
                    "dataset": "放射学",
                    "top_k": 8
                },
                "depends_on": [],
                "can_parallel": False
            }]
            state["total_steps"] = 1
            return "rag_simple"

        # 复杂问题，需要规划
        return "rag_complex"

    async def ask(
        self,
        question: str,
        dataset: str = "放射学",
        session_id: Optional[str] = None
    ) -> AsyncGenerator[str, None]:
        """知识问答

        Args:
            question: 用户问题
            dataset: 知识库名称
            session_id: 会话ID

        Yields:
            回答文本流
        """
        # 注入数据集信息
        original_analyze = self.nodes.analyze_intent

        async def analyze_with_dataset(state):
            result = await original_analyze(state)
            # 确保使用指定的数据集
            if result.get("suggested_tools"):
                result["dataset"] = dataset
            return result

        # 临时替换分析节点
        self.nodes.analyze_intent = analyze_with_dataset

        try:
            async for chunk in self.ainvoke_stream(question, session_id):
                yield chunk
        finally:
            # 恢复原节点
            self.nodes.analyze_intent = original_analyze
