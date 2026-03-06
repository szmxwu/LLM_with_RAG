"""LangGraph状态定义"""

from typing import Annotated, TypedDict, List, Dict, Any, Optional
from dataclasses import dataclass, field
import operator


class AgentState(TypedDict):
    """Agent工作流状态"""

    # 会话标识
    session_id: str
    user_id: str

    # 输入
    question: str

    # 意图分析结果
    complexity: str  # simple, moderate, complex
    need_rag: bool
    can_answer_directly: bool
    suggested_tools: List[str]
    suggested_thinking_mode: Optional[str]  # no_think, think, deep_think

    # 思考强度控制
    thinking_mode: str  # no_think, think, deep_think

    # 执行计划
    plan: List[Dict[str, Any]]  # 执行步骤
    current_step: int  # 当前执行到第几步
    total_steps: int

    # 工具执行结果
    tool_results: Annotated[List[Dict], operator.add]
    intermediate_outputs: Dict[str, Any]  # 中间结果缓存

    # 反思相关
    reflection_notes: List[str]
    retry_count: int
    should_retry: bool

    # 最终输出
    final_answer: Optional[str]
    status: str  # running, completed, failed
    error_message: Optional[str]


@dataclass
class ExecutionStep:
    """执行步骤"""
    id: int
    description: str
    tool_name: str
    params: Dict[str, Any]
    depends_on: List[int] = field(default_factory=list)
    can_parallel: bool = False
    status: str = "pending"  # pending, running, completed, failed
    result: Any = None
    error: Optional[str] = None


@dataclass
class ToolExecutionResult:
    """工具执行结果"""
    tool_name: str
    success: bool
    data: Any
    latency_ms: float
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
