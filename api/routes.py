"""FastAPI路由 - v2版本API - 支持思考强度控制 + 详细Swagger文档"""

import asyncio
import json
import os
import re
from enum import Enum
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, Field

from config.settings import settings, ThinkingMode
from agents.knowledge_agent import KnowledgeAgent
from agents.radiology_agent import RadiologyAgent
from agents.enhanced_knowledge_agent import EnhancedKnowledgeAgent


# ============= 数据模型 =============

class AgentType(str, Enum):
    """Agent类型"""
    KNOWLEDGE = "knowledge"
    RADIOLOGY = "radiology"


class ThinkingModeEnum(str, Enum):
    """思考模式枚举 - 用于API参数

    Qwen模型支持/no_think和/think指令来控制思考强度
    """
    NO_THINK = "no_think"      # 快速响应，无推理
    THINK = "think"            # 标准推理（默认）
    DEEP_THINK = "deep_think"  # 深度推理


class AskRequest(BaseModel):
    """RAG知识问答请求

    医学知识库检索问答接口，支持思考强度控制和流式输出
    """
    question: str = Field(
        ...,
        title="用户问题",
        description="提出的医学问题",
        example="肝癌的影像学表现有哪些？"
    )
    user_id: str = Field(
        default="anonymous",
        title="用户ID",
        description="用户标识",
        example="user-001"
    )
    session_id: Optional[str] = Field(
        None,
        title="会话ID",
        description="用于保持对话上下文，为空时自动创建",
        example="550e8400-e29b-41d4-a716-446655440000"
    )
    agent_type: AgentType = Field(
        default=AgentType.KNOWLEDGE,
        title="Agent类型",
        description="选择使用的Agent：knowledge(知识问答)或radiology(放射质控)"
    )
    dataset: str = Field(
        default="放射学",
        title="知识库名称",
        description="要检索的知识库",
        example="放射学"
    )
    thinking_mode: ThinkingModeEnum = Field(
        default=ThinkingModeEnum.THINK,
        title="思考模式",
        description="""控制LLM思考强度：
        - no_think: 快速响应，适合简单问题
        - think: 标准推理，适合一般问题（默认）
        - deep_think: 深度推理，适合复杂病例分析""",
        example="think"
    )


class DiagnosisMatchRequest(BaseModel):
    """放射-病理诊断匹配请求

    判断放射诊断与病理诊断是否符合，默认使用深度思考模式保证准确性
    """
    radiology_result: str = Field(
        ...,
        title="放射诊断结果",
        description="放射报告的诊断结论",
        example="考虑前列腺癌，PI-RADS 5；向上突入膀胱，并累及左输尿管膀胱壁内段致左侧输尿管积水；膀胱左后方结节，考虑转移。"
    )
    pathology_result: str = Field(
        ...,
        title="病理诊断结果",
        description="病理报告的诊断结论",
        example="前列腺腺泡性腺癌，gleason评分4+4=8分，WHO/ISUP前列腺分级分组4组，可见神经侵犯，未见脉管内癌栓"
    )
    session_id: Optional[str] = Field(
        None,
        title="会话ID",
        description="会话标识",
        example="550e8400-e29b-41d4-a716-446655440000"
    )
    thinking_mode: ThinkingModeEnum = Field(
        default=ThinkingModeEnum.DEEP_THINK,
        title="思考模式",
        description="诊断匹配默认使用深度思考模式以保证准确性",
        example="deep_think"
    )


class ComplexDiagnosisRequest(BaseModel):
    """复杂诊断匹配请求（支持多模态对比）

    用于对比放射/超声/内镜诊断与金标准诊断（病理/出院小结）的符合率
    """
    verification: str = Field(
        ...,
        title="待验证的诊断",
        description="需要验证的诊断报告内容",
        example="考虑前列腺癌，PI-RADS 5；向上突入膀胱，并累及左输尿管膀胱壁内段致左侧输尿管积水；膀胱左后方结节，考虑转移。"
    )
    verification_type: str = Field(
        ...,
        title="验证类型",
        description="诊断类型：CT、MR、US(超声)、DX(X线)、MG(钼靶)、ES(内镜)等",
        example="MR"
    )
    pathology: str = Field(
        default="",
        title="病理诊断",
        description="病理诊断结果（金标准）",
        example="前列腺腺泡性腺癌，gleason评分4+4=8分"
    )
    clinical: str = Field(
        default="",
        title="出院小结",
        description="出院小结内容（金标准）",
        example="初步诊断:前列腺结节；前列腺增生；PSA升高。入院后完善检查，行超声引导下经直肠前列腺穿刺活检术。"
    )
    use_think: bool = Field(
        default=False,
        title="使用长思考（兼容旧版）",
        description="是否启用长思考模式，已迁移到thinking_mode参数"
    )
    use_tool: bool = Field(
        default=False,
        title="使用工具（兼容旧版）",
        description="是否允许调用工具查询"
    )
    session_id: Optional[str] = Field(
        None,
        title="会话ID",
        description="会话标识"
    )
    thinking_mode: ThinkingModeEnum = Field(
        default=ThinkingModeEnum.DEEP_THINK,
        title="思考模式",
        description="复杂诊断默认使用深度思考模式"
    )


class PatientAnalysisRequest(BaseModel):
    """患者检查分析请求

    根据患者历史检查记录，生成阅片要点和诊断建议
    """
    patient_history: str = Field(
        ...,
        title="患者历史检查记录",
        description="患者历史检查结果（JSON格式字符串）",
        example='''[{"modality": "CT", "result_str": "肝右叶占位性病变", "date": "2024-01-15"}]'''
    )
    modality: str = Field(
        ...,
        title="检查类型",
        description="准备进行的检查类型：CT、MR、US等",
        example="CT"
    )
    study_part: str = Field(
        ...,
        title="检查部位",
        description="准备检查的身体部位",
        example="腹部"
    )
    previous_reports: str = Field(
        default="",
        title="近期相同部位检查",
        description="近期相同部位的检查报告（JSON格式）",
        example='''[{"date": "2024-01-15", "part": "腹部", "modality": "CT", "result": "肝右叶占位"}]'''
    )
    user_id: str = Field(
        default="anonymous",
        title="用户ID",
        description="用户标识"
    )
    session_id: Optional[str] = Field(
        None,
        title="会话ID",
        description="会话标识"
    )
    thinking_mode: ThinkingModeEnum = Field(
        default=ThinkingModeEnum.THINK,
        title="思考模式",
        description="思考强度控制"
    )


# ============= WebSocket 连接管理器 =============

class ConnectionManager:
    """WebSocket连接管理器"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]

    async def send_message(self, message: dict, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(json.dumps(message))


# 全局连接管理器实例
connection_manager = ConnectionManager()


# ============= 路由 =============

router = APIRouter(prefix="/v2", tags=["v2"])

# Agent实例缓存
_agents = {
    AgentType.KNOWLEDGE: None,
    AgentType.RADIOLOGY: None,
}


def _get_agent(agent_type: AgentType):
    """获取或创建Agent实例"""
    if _agents[agent_type] is None:
        if agent_type == AgentType.KNOWLEDGE:
            _agents[agent_type] = KnowledgeAgent()
        elif agent_type == AgentType.RADIOLOGY:
            _agents[agent_type] = RadiologyAgent()
    return _agents[agent_type]


# 增强版Agent实例
_enhanced_agent: Optional[EnhancedKnowledgeAgent] = None

def _get_enhanced_agent() -> EnhancedKnowledgeAgent:
    """获取或创建增强版Agent实例"""
    global _enhanced_agent
    if _enhanced_agent is None:
        _enhanced_agent = EnhancedKnowledgeAgent()
    return _enhanced_agent


def _convert_thinking_mode(mode: ThinkingModeEnum) -> ThinkingMode:
    """转换思考模式枚举"""
    return ThinkingMode(mode.value)


@router.post(
    "/ask",
    response_class=StreamingResponse,
    summary="知识问答",
    description="""
    <b>医学知识库检索问答接口（增强版）</b><br><br>

    特性：
    • 支持流式输出，实时返回回答内容
    • 支持思考强度控制（no_think/think/deep_think）
    • 自动选择合适的Agent处理
    • <b>四阶段处理：</b>流式回答 → 参考文献 → 异步引文 → 病例关键词

    <b>思考模式说明：</b>
    • <b>no_think</b>：快速响应，适合简单问答，直接给出答案
    • <b>think</b>：标准推理（默认），单次RAG查询，适合一般问题
    • <b>deep_think</b>：深度推理，启用<b>问题拆分+并行查询+结构化报告</b>，适合复杂病例分析
      - 将复杂问题拆分为2-4个子问题
      - 并行查询每个子问题
      - 生成包含"思考过程"、"图例"、"参考文献"的结构化报告
      - 最后生成总结

    <b>输出格式：</b>
    流式返回多个部分，每部分以 [STAGE:type] 开头：
    • <code>[STAGE:answer]</code> - 流式回答内容
    • <code>[STAGE:references]</code> - 参考文献列表（Markdown格式）
    • <code>[STAGE:keywords]</code> - 病例检索关键词和链接
    • <code>[STAGE:complete]</code> - 完成标记

    返回：text/plain 流式文本
    """
)
async def ask(request: AskRequest):
    """知识问答接口 - 支持四阶段完整输出"""
    agent = _get_enhanced_agent()
    thinking_mode = _convert_thinking_mode(request.thinking_mode)

    async def generate():
        async for event in agent.ask_enhanced(
            question=request.question,
            dataset=request.dataset,
            session_id=request.session_id,
            user_id=request.user_id,
            thinking_mode=thinking_mode,
            connection_manager=connection_manager,
            chat_name=request.dataset  # V1版本使用chat_name（聊天助手名称）
        ):
            stage = event.get('stage')
            event_type = event.get('type')
            data = event.get('data', {})

            if stage == 'answer' and event_type == 'chunk':
                # 阶段1: 流式回答内容
                content = data.get('content', '')
                if content:
                    yield content

            elif stage == 'answer' and event_type == 'complete':
                # 阶段1完成标记
                yield "\n[STAGE:answer_complete]\n"

            elif stage == 'references' and event_type == 'complete':
                # 阶段2: 参考文献
                markdown = data.get('markdown', '')
                if markdown:
                    yield f"\n[STAGE:references]\n{markdown}\n"

            elif stage == 'keywords' and event_type == 'complete':
                # 阶段4: 病例检索关键词
                keywords = data.get('keywords', '')
                search_url = data.get('search_url')
                if keywords and search_url:
                    yield f"\n[STAGE:keywords]\n关键词: {keywords}\n<a href=\"{search_url}\" target=\"_blank\" style=\"font-size:18px; color:darkred;\">相关病例图片</a>\n"
                elif keywords:
                    yield f"\n[STAGE:keywords]\n关键词: {keywords}\n"

            elif stage == 'complete':
                # 全部完成
                yield f"\n[STAGE:complete]\n"

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache"}
    )


@router.post(
    "/diagnosis/match",
    summary="放射-病理诊断匹配",
    description="""
    <b>判断放射诊断与病理诊断是否相符</b>

    返回格式：
    {
        "result": "符合|基本符合|不符合|无法判断",
        "confidence": "高|中|低",
        "reason": "判断理由",
        "key_findings": ["关键发现1", "关键发现2"],
        "suggestions": "建议"
    }

    默认使用 deep_think 模式以保证诊断准确性
    """
)
async def diagnosis_match(request: DiagnosisMatchRequest):
    """放射-病理诊断匹配 - 默认使用深度思考"""
    agent = _get_agent(AgentType.RADIOLOGY)

    thinking_mode = _convert_thinking_mode(request.thinking_mode)

    result = await agent.diagnosis_coincidence(
        radiology_result=request.radiology_result,
        pathology_result=request.pathology_result,
        session_id=request.session_id,
        thinking_mode=thinking_mode
    )

    return result


@router.post(
    "/diagnosis/complex-match",
    summary="复杂诊断匹配（多模态）",
    description="""
    <b>复杂诊断符合率判断</b><br><br>

    支持对比：
    • 放射/超声/内镜诊断 vs 病理诊断（金标准）
    • 放射/超声/内镜诊断 vs 出院小结（金标准）
    • 支持同时使用病理和出院小结作为参考

    返回包含：
    • 符合率判断（符合/基本符合/不符合）
    • 详细判断理由
    • 关键发现对比
    • 质控建议

    默认使用 <b>deep_think</b> 模式
    """
)
async def complex_diagnosis_match(request: ComplexDiagnosisRequest):
    """复杂诊断匹配（支持多模态对比）- 默认使用深度思考"""
    agent = _get_agent(AgentType.RADIOLOGY)

    # 兼容旧版use_think参数
    if request.use_think and request.thinking_mode == ThinkingModeEnum.THINK:
        thinking_mode = ThinkingMode.DEEP_THINK
    else:
        thinking_mode = _convert_thinking_mode(request.thinking_mode)

    result = await agent.complex_coincidence(
        verification=request.verification,
        verification_type=request.verification_type,
        pathology=request.pathology,
        clinical=request.clinical,
        use_think=request.use_think,
        use_tool=request.use_tool,
        session_id=request.session_id,
        thinking_mode=thinking_mode
    )

    return result


@router.post(
    "/patient/analyze",
    response_class=StreamingResponse,
    summary="患者检查分析",
    description="""
    <b>根据患者历史检查生成阅片要点</b><br><br>

    分析内容：
    • 患者主要疾病按系统总结
    • 阅片时需要特别关注的要点
    • 扫描技术细节建议
    • 鉴别诊断考虑

    返回：Markdown格式的结构化报告（流式）
    """
)
async def patient_analyze(request: PatientAnalysisRequest):
    """患者检查分析 - 流式返回分析报告"""
    agent = _get_agent(AgentType.RADIOLOGY)

    thinking_mode = _convert_thinking_mode(request.thinking_mode)

    async def generate():
        async for chunk in agent.patient_analysis(
            patient_history=request.patient_history,
            modality=request.modality,
            study_part=request.study_part,
            previous_reports=request.previous_reports,
            session_id=request.session_id,
            thinking_mode=thinking_mode
        ):
            yield chunk

    return StreamingResponse(
        generate(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache"}
    )


@router.get(
    "/thinking-modes",
    summary="获取思考模式说明",
    description="获取支持的思考模式及其使用建议"
)
async def get_thinking_modes():
    """获取支持的思考模式说明"""
    return {
        "modes": [
            {
                "value": "no_think",
                "label": "快速响应",
                "description": "/no_think - 直接给出答案，不展示推理过程，响应最快",
                "use_case": "适合简单问答、闲聊、不需要深度推理的场景",
                "latency": "低",
                "cost": "低"
            },
            {
                "value": "think",
                "label": "标准推理",
                "description": "/think - 展示推理过程后给出答案（默认）",
                "use_case": "适合一般医学问题、需要一定分析的场景",
                "latency": "中",
                "cost": "中"
            },
            {
                "value": "deep_think",
                "label": "深度推理",
                "description": "/think + 深度分析 - 全面考虑多种可能性，逻辑严密",
                "use_case": "适合诊断匹配、复杂病例分析、需要高精度判断的场景",
                "latency": "高",
                "cost": "高"
            }
        ],
        "default": "think",
        "auto_select": {
            "simple_task": "no_think",
            "moderate_task": "think",
            "complex_task": "deep_think"
        },
        "recommendations": {
            "diagnosis_match": "deep_think",
            "knowledge_qa": "think",
            "patient_analysis": "think",
            "quick_query": "no_think"
        }
    }


@router.get(
    "/health",
    summary="健康检查",
    description="服务健康状态和版本信息"
)
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "version": "2.0.0",
        "features": {
            "thinking_mode_control": True,
            "streaming": True,
            "multi_agent": True,
            "langgraph": True
        },
        "agents": {
            "knowledge": _agents[AgentType.KNOWLEDGE] is not None,
            "radiology": _agents[AgentType.RADIOLOGY] is not None
        }
    }


# ============= SQL分析API =============

class SQLAnalysisRequest(BaseModel):
    """SQL分析请求"""
    question: str = Field(
        ...,
        title="分析问题",
        description="自然语言描述的数据分析需求，例如：统计各科室CT检查数量",
        example="统计上个月各科室CT检查的人次和收入"
    )
    session_id: Optional[str] = Field(
        None,
        title="会话ID",
        description="用于保持分析上下文",
        example="550e8400-e29b-41d4-a716-446655440000"
    )


@router.post(
    "/sql/analyze",
    response_class=StreamingResponse,
    summary="SQL数据分析（流式）",
    description="""
    <b>智能SQL数据分析Agent</b><br><br>

    高级特性：
    • <b>多步骤执行</b>：复杂查询自动分解为多个简单步骤
    • <b>Python处理</b>：支持Python代码执行连接中间结果
    • <b>流式输出</b>：实时返回执行进度
    • <b>图表生成</b>：自动生成柱状图PNG（base64）

    返回事件类型：
    • <code>plan</code>：执行计划生成
    • <code>step_start</code>：步骤开始执行
    • <code>step_complete</code>：步骤执行完成
    • <code>analysis</code>：数据分析中
    • <code>final</code>：最终结果（包含数据和图表）

    示例问题：
    • "统计上个月各科室CT检查的人次和收入"
    • "对比今年和去年同期MRI检查数量的变化"
    • "找出检查等待时间最长的前10个科室"

    返回格式：text/event-stream（SSE流式）
    """
)
async def sql_analyze(request: SQLAnalysisRequest):
    """SQL数据分析Agent - 支持多步骤复杂查询"""

    async def generate():
        from agents.sql_analysis_agent import SQLAnalysisAgent

        agent = SQLAnalysisAgent()

        async for event in agent.analyze(request.question, request.session_id):
            # 将事件转为JSON行
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用Nginx缓冲
        }
    )


@router.post(
    "/sql/simple",
    summary="简单SQL查询",
    description="""
    <b>简单SQL查询（非流式）</b><br><br>

    适用于简单的单表查询，快速返回结果。<br>
    返回包括SQL、数据和可视化配置。
    """
)
async def sql_simple(request: SQLAnalysisRequest):
    """简单SQL查询"""
    from tools.sql_agent import SQLAnalysisPipeline

    pipeline = SQLAnalysisPipeline()
    result = await pipeline.run(request.question)

    return JSONResponse(content=result)


# ============= 病例检索路由 =============

@router.get(
    "/list_case",
    summary="搜索病例图片",
    description="""
    <b>根据关键词搜索病例库中的相关病例图片</b><br><br>

    该接口用于显示英文关键词找到的病例，来源于 /v2/ask 接口返回的 keywords。<br><br>

    特性：<br>
    • 支持英文关键词搜索<br>
    • 如果传入中文，会自动转换为英文关键词<br>
    • 返回病例列表，包含HTML格式内容和base64编码的图片<br><br>

    返回格式：JSON数组，每个元素为病例的HTML内容（包含图片）
    """
)
async def list_case(
    keywords: str = Query(
        ...,
        title="搜索关键词",
        description="病例关键词，来源于 /v2/ask 返回的 keywords。支持英文或中文（中文会自动转换）",
        example="liver cancer imaging"
    )
):
    """
    返回病例库中的相关病例图片

    如果keywords包含中文，会先调用generate_probe转换为英文关键词
    """
    import sys
    sys.path.insert(0, '/home/wmx/work/python/LLM_with_RAG')
    from llm_func import search_case, generate_probe

    # 如果包含中文，转换为英文关键词
    if re.search(r'[\u4e00-\u9fff]+', keywords):
        keywords = await asyncio.to_thread(generate_probe, keywords)

    # 搜索病例
    result = await asyncio.to_thread(search_case, keywords)

    return JSONResponse(content={
        "keywords": keywords,
        "cases": result,
        "count": len(result)
    })


# ============= WebSocket 路由 =============

@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket连接 - 用于接收异步引文内容

    连接后，客户端可以接收：
    - reference_content: 参考文献内容（PDF/PPTX等解析结果）
    - typing_indicator: 输入状态指示器
    - completion_status: 任务完成状态
    """
    await connection_manager.connect(websocket, user_id)
    try:
        while True:
            # 等待客户端消息（可选的心跳检测）
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type")

                if msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif msg_type == "subscribe":
                    # 客户端订阅特定会话的更新
                    session_id = message.get("session_id")
                    await websocket.send_text(json.dumps({
                        "type": "subscribed",
                        "session_id": session_id
                    }))
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        connection_manager.disconnect(user_id)
