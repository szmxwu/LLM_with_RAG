"""增强版知识问答Agent - 支持四阶段完整输出和深度思考模式

V1 版本的四阶段处理：
1. 流式返回回答
2. 生成参考文献列表
3. 异步获取引文截图或引文片段
4. 生成病例检索关键词

V1 /long_think 逻辑：
- 问题分类（简单/复杂）
- 问题拆分为子问题
- 并行RAG查询
- 结构化报告生成
"""

import asyncio
import json
import os
import re
import uuid
import warnings
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

import urllib3
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser

from config.settings import settings, ThinkingMode
from tools.ragflow_tools import RAGSearchTool

# 禁用SSL警告（内部网络环境）
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


@dataclass
class ReferenceInfo:
    """参考文献信息"""
    document_name: str
    document_id: str
    page: List[int] = field(default_factory=list)
    content: str = ""
    image_id: str = ""
    positions: List = field(default_factory=list)


@dataclass
class SubAnswer:
    """子问题答案"""
    question: str
    answer: str
    references: List[ReferenceInfo]
    chunks: List[Dict]


class EnhancedKnowledgeAgent:
    """增强版医学知识问答Agent

    继承 V1 版本的四阶段处理能力：
    1. 流式返回回答
    2. 生成参考文献列表
    3. 异步获取引文截图或引文片段（通过 WebSocket）
    4. 生成病例检索关键词

    深度思考模式（deep_think）：
    - 问题分类和拆分
    - 并行子问题查询
    - 结构化报告生成
    """

    # 引用标记正则表达式：##数字$$
    CITATION_PATTERN = re.compile(r"##(\d+)\$\$")

    def __init__(self):
        self.name = "EnhancedKnowledgeAgent"
        # 使用自定义HTTP客户端避免SSL问题
        import httpx
        http_client = httpx.Client(
            base_url=settings.xinference_url,
            verify=False,  # 禁用SSL验证（内部HTTP服务）
            timeout=httpx.Timeout(60.0)
        )
        self.llm = ChatOpenAI(
            base_url=settings.xinference_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=0.3,
            max_tokens=4096,
            http_client=http_client,
        )
        self.rag_tool = RAGSearchTool()
        self.base_url = settings.ragflow_url.rstrip('/').replace('/api', '')
        self.executor = ThreadPoolExecutor(max_workers=4)

    async def ask_enhanced(
        self,
        question: str,
        dataset: str = "放射学",
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        thinking_mode: Optional[ThinkingMode] = None,
        connection_manager=None,
        chat_name: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """增强版问答 - 根据思考模式选择不同处理流程

        Args:
            question: 用户问题
            dataset: 知识库名称（V1中对应chat_name）
            session_id: 会话ID
            user_id: 用户ID
            thinking_mode: 思考模式
            connection_manager: WebSocket连接管理器
            chat_name: 聊天助手名称（V1版本使用）

        Yields:
            {
                'stage': 'answer' | 'references' | 'keywords' | 'complete',
                'type': 'chunk' | 'complete',
                'data': {...}
            }
        """
        session_id = session_id or str(uuid.uuid4())
        user_id = user_id or "anonymous"

        # V1版本使用chat_name，默认为"小影"
        chat_name = "小影"

        # 根据思考模式选择处理流程
        if thinking_mode == ThinkingMode.DEEP_THINK:
            # 深度思考模式：使用 V1 的 long_think 逻辑
            async for event in self._deep_think_process(
                question, chat_name, session_id, user_id, connection_manager
            ):
                yield event
        else:
            # 标准/快速模式：简化流程
            async for event in self._standard_process(
                question, chat_name, session_id, user_id, thinking_mode, connection_manager
            ):
                yield event

    async def _deep_think_process(
        self,
        question: str,
        chat_name: str,
        session_id: str,
        user_id: str,
        connection_manager
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """深度思考模式 - 问题拆分 + 并行查询 + 结构化报告"""

        # ===== 步骤1: 判断是否需要RAG =====
        need_rag = await self._decide_rag_usage(question)

        if not need_rag:
            # 不需要RAG，直接回答
            async for event in self._direct_answer(question, session_id):
                yield event
            return

        # ===== 步骤2: 问题分类（简单/复杂）=====
        classification = await self._classify_question(question)

        if classification.get("type") == "简单":
            # 简单问题：单次RAG查询
            print("【简单问题】")
            async for event in self._standard_process(
                question, chat_name, session_id, user_id, ThinkingMode.THINK, connection_manager
            ):
                yield event
            return

        # ===== 步骤3: 复杂问题拆分 =====
        print("【复杂问题 - 深度思考】")
        sub_questions = await self._split_question(question)

        # 输出问题拆分流
        yield {
            'stage': 'thinking',
            'type': 'chunk',
            'data': {'content': f"## 您的问题:\n- {question}\n\n## 思考过程:\n\n"}
        }

        # ===== 步骤4: 并行查询子问题 =====
        tasks = [
            self._query_subquestion(q, chat_name)
            for q in sub_questions
        ]
        sub_answers = await asyncio.gather(*tasks, return_exceptions=True)

        # 过滤掉异常结果和低质量信息
        valid_answers = []
        for q, ans in zip(sub_questions, sub_answers):
            if isinstance(ans, Exception):
                continue
            if ans and not re.search(r"知识库[中]未", ans.answer):
                valid_answers.append(ans)

        # ===== 步骤5: 生成结构化报告 =====
        sequence_number = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
        all_references = []
        all_images = []

        for idx, sub_answer in enumerate(valid_answers):
            # 生成子问题的结构化报告
            sub_report = await self._generate_sub_report(sub_answer, all_images)

            # 收集引用（去重）
            for ref in sub_answer.references:
                if ref.image_id and ref.image_id not in [r.image_id for r in all_images]:
                    all_images.append(ref)
                if ref.document_id not in [r.document_id for r in all_references]:
                    all_references.append(ref)

            # 输出子问题标题和内容
            section_header = f'<div><h3 style="color:#8B0000;">{sequence_number[idx]}. {sub_answer.question}</h3></div><br>'

            yield {
                'stage': 'answer',
                'type': 'chunk',
                'data': {'content': section_header + sub_report + "\n"}
            }

        # ===== 步骤6: 生成图例 =====
        if all_images:
            graphs_section = "\n### 图例\n"
            for img_ref in all_images:
                graphs_section += f"**{img_ref.document_name}**\n"
                # 这里可以添加图片base64
                graphs_section += f"【图片说明】{img_ref.content[:200]}...\n\n"

            yield {
                'stage': 'answer',
                'type': 'chunk',
                'data': {'content': graphs_section}
            }

        # ===== 步骤7: 生成最终总结 =====
        summary_prompt = f"""## 背景：你是一个经验丰富的主任医师，请根据以下分析回答问题：

## 问题：{question}

## 知识库：
```
{json.dumps([{"子问题": a.question, "回答": re.sub(r'##\d+\$\$', '', a.answer)} for a in valid_answers], ensure_ascii=False)}
```

## 要求：请使用序号列出要点，使用中文Markdown格式，保持专业的医学风格，尽可能简短"""

        yield {
            'stage': 'answer',
            'type': 'chunk',
            'data': {'content': "\n## 总结\n"}
        }

        messages = [
            SystemMessage(content="你是医学知识问答专家/no_think"),
            HumanMessage(content=summary_prompt)
        ]

        async for chunk in self.llm.astream(messages):
            content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if content:
                content = self._clean_thinking_tags(content)
                yield {
                    'stage': 'answer',
                    'type': 'chunk',
                    'data': {'content': content}
                }

        # 阶段1完成
        yield {
            'stage': 'answer',
            'type': 'complete',
            'data': {'content': ''}
        }

        # ===== 步骤8: 参考文献 =====
        reference_markdown = self._format_references(all_references)
        if reference_markdown:
            yield {
                'stage': 'references',
                'type': 'complete',
                'data': {
                    'markdown': reference_markdown,
                    'references': [
                        {
                            'document_name': r.document_name,
                            'document_id': r.document_id,
                            'page': r.page
                        }
                        for r in all_references
                    ]
                }
            }

        # 异步发送引文内容
        if connection_manager and all_references:
            asyncio.create_task(
                self._send_references_async(all_references, connection_manager, user_id)
            )

        # ===== 步骤9: 病例检索关键词 =====
        # 基于所有子问题的回答生成关键词
        combined_answer = " ".join([a.answer for a in valid_answers])
        keywords = await self._generate_probe_keywords(combined_answer)

        # 构建病例搜索URL (V2版本使用 /v2/list_case API)
        search_url = None
        if keywords:
            # 优先使用环境变量中的API地址，否则使用相对路径
            base_url = getattr(settings, 'host_ip', 'localhost:6082')
            if base_url.startswith('0.0.0.0'):
                base_url = 'localhost:6082'
            search_url = f"http://{base_url}/v2/list_case?keywords={keywords.replace(' ', '%20')}"

        yield {
            'stage': 'keywords',
            'type': 'complete',
            'data': {
                'keywords': keywords,
                'search_url': search_url
            }
        }

        # 完成
        yield {
            'stage': 'complete',
            'type': 'complete',
            'data': {
                'session_id': session_id,
                'sub_question_count': len(valid_answers),
                'reference_count': len(all_references)
            }
        }

    async def _standard_process(
        self,
        question: str,
        chat_name: str,
        session_id: str,
        user_id: str,
        thinking_mode: Optional[ThinkingMode],
        connection_manager
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """标准处理流程 - 使用RAGFlow Chat（类似V1的Query_steam）"""

        # ===== 阶段1: 使用RAGFlow Chat获取流式回答 =====
        # 使用类似V1的方式：调用RAGFlow Chat，获取带引用的回答
        full_answer = ""
        last_reference = []  # 保存最后的reference

        async for chunk_data in self._ragflow_chat_stream(
            question=question,
            chat_name=chat_name,
            thinking_mode=thinking_mode,
            user_id=user_id
        ):
            if chunk_data.get('type') == 'content':
                # 流式内容
                content = chunk_data.get('data', '')
                if content:
                    full_answer += content
                    yield {
                        'stage': 'answer',
                        'type': 'chunk',
                        'data': {'content': content}
                    }
            elif chunk_data.get('type') == 'reference':
                # 保存引用信息
                last_reference = chunk_data.get('data', [])

        # 阶段1完成
        yield {
            'stage': 'answer',
            'type': 'complete',
            'data': {'content': full_answer}
        }

        # ===== 阶段2: 处理参考文献 =====
        # V1逻辑：保留被大模型选用的引文或者包含图片的引文
        reference_markdown, send_references = await self._process_references_v1(
            full_answer, last_reference
        )

        if reference_markdown:
            yield {
                'stage': 'references',
                'type': 'complete',
                'data': {
                    'markdown': reference_markdown,
                    'references': [
                        {
                            'document_name': r['document_name'],
                            'document_id': r['document_id'],
                            'page': r.get('page', [])
                        }
                        for r in send_references
                    ]
                }
            }

        # 异步发送引文内容（通过WebSocket）
        if connection_manager and send_references:
            asyncio.create_task(
                self._send_references_v1_async(send_references, connection_manager, user_id)
            )

        # ===== 阶段3: 病例检索关键词 =====
        keywords = await self._generate_probe_keywords(full_answer)

        # 构建病例搜索URL (V2版本使用 /v2/list_case API)
        search_url = None
        if keywords:
            # 优先使用环境变量中的API地址，否则使用相对路径
            base_url = getattr(settings, 'host_ip', 'localhost:6082')
            if base_url.startswith('0.0.0.0'):
                base_url = 'localhost:6082'
            search_url = f"http://{base_url}/v2/list_case?keywords={keywords.replace(' ', '%20')}"

        yield {
            'stage': 'keywords',
            'type': 'complete',
            'data': {
                'keywords': keywords,
                'search_url': search_url
            }
        }

        # 完成
        yield {
            'stage': 'complete',
            'type': 'complete',
            'data': {
                'session_id': session_id,
                'answer_length': len(full_answer),
                'reference_count': len(send_references)
            }
        }

    async def _direct_answer(
        self,
        question: str,
        session_id: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """直接回答（不需要RAG）"""

        intro = getattr(settings, 'agent_introduction', '你是放射科医生的专业知识助手')

        messages = [
            SystemMessage(content=intro),
            HumanMessage(content=f"请回答以下问题：{question}")
        ]

        answer = ""
        async for chunk in self.llm.astream(messages):
            content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if content:
                content = self._clean_thinking_tags(content)
                answer += content
                yield {
                    'stage': 'answer',
                    'type': 'chunk',
                    'data': {'content': content}
                }

        yield {
            'stage': 'answer',
            'type': 'complete',
            'data': {'content': answer}
        }

        # 完成
        yield {
            'stage': 'complete',
            'type': 'complete',
            'data': {
                'session_id': session_id,
                'answer_length': len(answer),
                'reference_count': 0
            }
        }

    # ========== RAGFlow Chat 方法 ==========

    async def _ragflow_chat_stream(
        self,
        question: str,
        chat_name: str,
        thinking_mode: Optional[ThinkingMode],
        user_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        使用RAGFlow Chat获取流式回答（类似V1的Query_steam）

        Yields:
            {'type': 'content', 'data': '流式内容'}
            {'type': 'reference', 'data': [引用列表]}
        """
        try:
            # 导入RAGFlow SDK（V1版本的SDK）
            import sys
            sys.path.insert(0, '/home/wmx/work/python/LLM_with_RAG')
            from RAGFLOW_SDK import Query_steam, Create_session

            # 应用思考模式前缀
            if thinking_mode == ThinkingMode.NO_THINK:
                question = "/no_think\n" + question

            # 使用V1版本的Query_steam获取流式回答
            # chat_name是聊天助手的名字（如"小影"）
            answer_generator = Query_steam(question, chat_name, user_id)

            full_content = ""
            final_reference = []

            # 流式获取回答
            for ans in answer_generator:
                if hasattr(ans, 'content'):
                    # 计算新增内容
                    new_content = ans.content[len(full_content):]
                    if new_content:
                        full_content = ans.content
                        yield {'type': 'content', 'data': new_content}

                # 保存引用（最后会返回完整的引用列表）
                if hasattr(ans, 'reference') and ans.reference:
                    final_reference = ans.reference

            # 最后返回引用信息
            if final_reference:
                yield {'type': 'reference', 'data': final_reference}

        except Exception as e:
            print(f"RAGFlow Chat错误: {e}")
            # 降级：使用RAG搜索
            async for chunk in self._fallback_rag_stream(question, chat_name):
                yield chunk

    async def _fallback_rag_stream(
        self,
        question: str,
        chat_name: str
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """降级处理：当RAGFlow Chat失败时使用RAG搜索"""
        rag_result = await self.rag_tool.execute({
            "query": question,
            "dataset": chat_name,
            "top_k": 8
        })

        chunks = []
        if rag_result.success and rag_result.data:
            chunks = rag_result.data.get("chunks", [])

        context = self._build_context(chunks)
        prompt = self._build_prompt(question, context)

        messages = [
            SystemMessage(content="你是医学知识问答专家，回答时请使用 ##数字$$ 格式标注引用来源。"),
            HumanMessage(content=prompt)
        ]

        answer = ""
        async for chunk in self.llm.astream(messages):
            content = chunk.content if hasattr(chunk, 'content') else str(chunk)
            if content:
                answer += content
                yield {'type': 'content', 'data': content}

        # 构造假的reference格式
        fake_refs = [
            {
                'document_name': c.get('document_name', ''),
                'document_id': c.get('document_id', ''),
                'content': c.get('content', ''),
                'image_id': c.get('image_id', ''),
                'positions': c.get('positions', [])
            }
            for c in chunks
        ]
        yield {'type': 'reference', 'data': fake_refs}

    async def _process_references_v1(
        self,
        answer: str,
        reference_list: List[Dict]
    ) -> Tuple[str, List[Dict]]:
        """
        V1版本的参考文献处理方法
        保留被大模型选用的引文或者包含图片的引文
        """
        if not reference_list:
            return "", []

        # 从回答中提取引用标记 ##数字$$
        reference_index = re.findall(r"##(\d+)\$\$", answer)
        if reference_index:
            reference_index = [int(x) for x in reference_index]

        # 筛选引用：被引用的或包含图片的前2个
        reference_chunks = []
        for index, ref in enumerate(reference_list):
            if isinstance(ref, dict):
                if (index + 1 in reference_index) or (ref.get('image_id') and index < 2):
                    reference_chunks.append(ref)

        # 合并同一文件的多个页码
        merged_docs = {}
        send_references = []

        for doc in reference_chunks:
            try:
                doc['page'] = list(set([int(x[0]) for x in doc.get('positions', [])]))
            except:
                doc['page'] = []

            send_references.append(doc)
            doc_id = doc.get('document_id', '')

            if doc_id not in merged_docs:
                merged_docs[doc_id] = doc.copy()
            else:
                merged_docs[doc_id]['page'].extend(doc['page'])
                merged_docs[doc_id]['page'] = sorted(list(set(merged_docs[doc_id]['page'])))

        reference_chunks = list(merged_docs.values())

        # 格式化参考文献
        references = "\n### 参考文献\n"
        index = 1
        for chunk in reference_chunks:
            extension = os.path.splitext(chunk.get('document_name', ''))[1]
            extension = extension[1:] if extension else ""

            if extension in ['xlsx', 'xls', 'ppt', 'pptx']:
                # 下载链接
                link = f"{self.base_url}/v1/document/get/{chunk.get('document_id')}"
            else:
                # 预览链接
                link = f"{self.base_url}/document/{chunk.get('document_id')}?ext={extension}&prefix=document"

            page_str = str(chunk.get('page', ''))
            references += f"- [{index}] [{chunk.get('document_name', '')}]({link}){page_str}\n"
            index += 1

        return references, send_references

    async def _send_references_v1_async(
        self,
        reference_chunks: List[Dict],
        connection_manager,
        user_id: str
    ):
        """V1版本的异步发送参考文献"""
        # 如果回答中包含"知识库中未"，不发送参考文献
        # 这个检查应该在外层做，这里简化处理

        for chunk in reference_chunks:
            try:
                extension = os.path.splitext(chunk.get('document_name', ''))[1][1:]  # 去掉点
                content = None

                # 根据文件类型获取内容
                if extension == "pdf":
                    content = await self._get_pdf_content(chunk)
                elif extension == "pptx":
                    content = await self._get_ppt_content(chunk)
                else:
                    content = await self._get_other_content(chunk)

                if content:
                    await connection_manager.send_message({
                        'type': extension,
                        'name': chunk.get('document_name', ''),
                        'content': content
                    }, user_id)

            except Exception as e:
                print(f"文献发送失败: {e}")

    async def _get_pdf_content(self, chunk: Dict) -> str:
        """获取PDF内容（简化版）"""
        # 这里可以扩展为实际获取PDF片段
        return chunk.get('content', '')[:500]

    async def _get_ppt_content(self, chunk: Dict) -> str:
        """获取PPT内容（简化版）"""
        # 这里可以扩展为实际获取PPT片段
        return chunk.get('content', '')[:500]

    async def _get_other_content(self, chunk: Dict) -> str:
        """获取其他类型内容"""
        return chunk.get('content', '')[:500]

    # ========== 深度思考辅助方法 ==========

    async def _decide_rag_usage(self, question: str) -> bool:
        """判断是否需要使用RAG"""
        prompt = f"""判断问题是否需要使用医学知识库回答。
如果是闲聊或不需要医学专业知识的，返回"不需要"，否则返回"需要"。不要解释，不要评论/no_think

问题："{question}"""

        messages = [
            SystemMessage(content="你是问题分类专家"),
            HumanMessage(content=prompt)
        ]

        response = await self.llm.ainvoke(messages)
        content = response.content if hasattr(response, 'content') else str(response)
        content = self._clean_thinking_tags(content)

        return "不需要" not in content

    async def _classify_question(self, question: str) -> Dict[str, str]:
        """问题分类器 - 简单/复杂"""
        prompt = f"""判断问题复杂度："{question}"
返回JSON格式：{{"reason":"分类依据","type":"简单|复杂"}}
/no_think"""

        messages = [
            SystemMessage(content="你是问题分类专家"),
            HumanMessage(content=prompt)
        ]

        response = await self.llm.ainvoke(messages)
        content = response.content if hasattr(response, 'content') else str(response)
        content = self._clean_thinking_tags(content)

        try:
            # 尝试提取JSON
            if "json" in content.lower():
                match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
            return json.loads(content)
        except:
            # 降级处理
            if "简单" in content:
                return {"reason": "包含简单关键词", "type": "简单"}
            return {"reason": "默认复杂", "type": "复杂"}

    async def _split_question(self, question: str) -> List[str]:
        """问题拆分器 - 将复杂问题拆分为子问题"""
        prompt = f"""你是一个经验丰富的放射科主任医师，你需要拆分复杂问题："{question}"
生成2-4个独立子问题，每个子问题必须围绕复杂问题展开，你的拆分必须有助于更深入地理解复杂问题

输出格式：每个子问题单独一行，不要解释，不要评论"""

        messages = [
            SystemMessage(content="你是医学问题分析专家"),
            HumanMessage(content=prompt)
        ]

        response = await self.llm.ainvoke(messages)
        content = response.content if hasattr(response, 'content') else str(response)
        content = self._clean_thinking_tags(content)

        questions = [q.strip() for q in content.split("\n") if q.strip()]
        print(f"已拆分为 {len(questions)} 个子问题")
        return questions[:4]  # 最多4个子问题

    async def _query_subquestion(self, question: str, chat_name: str) -> SubAnswer:
        """查询子问题 - 使用RAGFlow Chat"""
        # 使用RAGFlow Chat流式获取回答
        full_answer = ""
        last_reference = []

        async for chunk_data in self._ragflow_chat_stream(
            question=question,
            chat_name=chat_name,
            thinking_mode=ThinkingMode.THINK,
            user_id=None
        ):
            if chunk_data.get('type') == 'content':
                full_answer += chunk_data.get('data', '')
            elif chunk_data.get('type') == 'reference':
                last_reference = chunk_data.get('data', [])

        # 将V1格式的引用转换为ReferenceInfo对象
        references = []
        for ref in last_reference:
            if isinstance(ref, dict):
                try:
                    pages = list(set([int(x[0]) for x in ref.get('positions', [])]))
                except:
                    pages = []

                ref_info = ReferenceInfo(
                    document_name=ref.get('document_name', ''),
                    document_id=ref.get('document_id', ''),
                    page=pages,
                    content=ref.get('content', ''),
                    image_id=ref.get('image_id', ''),
                    positions=ref.get('positions', [])
                )
                references.append(ref_info)

        # 构造假的 chunks 格式用于兼容
        chunks = [
            {
                'document_name': r.document_name,
                'document_id': r.document_id,
                'content': r.content,
                'image_id': r.image_id,
                'positions': r.positions
            }
            for r in references
        ]

        return SubAnswer(
            question=question,
            answer=full_answer,
            references=references,
            chunks=chunks
        )

    async def _generate_sub_report(self, sub_answer: SubAnswer, existing_images: List[ReferenceInfo]) -> str:
        """生成子问题的结构化报告"""
        # 替换引用标记为蓝色索引
        content = sub_answer.answer
        ref_index = 1
        refs = re.findall(r"##\d+\$\$", content)

        for r in refs:
            if r:
                content = content.replace(r, f'<span style="color:blue;">[{ref_index}]</span>')
                ref_index += 1

        # 添加图例（去重）
        graphs = ""
        for chunk in sub_answer.chunks:
            if chunk.get('image_id') and chunk.get('image_id') not in [img.image_id for img in existing_images]:
                graphs += f"\n**{chunk.get('document_name', '未知文档')}**\n"
                graphs += f"【图片说明】{chunk.get('content', '')[:150]}...\n"

        if graphs:
            graphs = "\n### 相关图片\n" + graphs

        # 添加该子问题的参考文献
        sub_refs = self._format_references(sub_answer.references)
        if sub_refs:
            content += "\n" + sub_refs

        return content + graphs

    # ========== 通用辅助方法 ==========

    def _build_context(self, chunks: List[Dict]) -> str:
        """构建检索上下文"""
        context_parts = []
        for i, chunk in enumerate(chunks, 1):
            content = chunk.get('content', '')
            doc_name = chunk.get('document_name', '未知文档')
            context_parts.append(f"[{i}] {content}\n（来源：{doc_name}）")
        return "\n\n".join(context_parts)

    def _build_prompt(self, question: str, context: str) -> str:
        """构建Prompt"""
        return f"""请基于以下参考资料回答问题，使用 ##数字$$ 格式标注引用来源：

参考资料：
{context}

问题：{question}

请提供详细的回答，并在引用参考资料时使用 ##数字$$ 格式标注来源。"""

    def _clean_thinking_tags(self, content: str) -> str:
        """清理思考过程标签"""
        if not content:
            return content
        cleaned = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
        return cleaned.strip()

    def _extract_references(self, answer: str, chunks: List[Dict]) -> List[ReferenceInfo]:
        """从回答中提取引用的参考文献"""
        citation_indices = set()
        for match in self.CITATION_PATTERN.finditer(answer):
            citation_indices.add(int(match.group(1)))

        references = []
        used_docs = {}

        for idx in citation_indices:
            if idx <= 0 or idx > len(chunks):
                continue

            chunk = chunks[idx - 1]
            doc_id = chunk.get('document_id', '')
            doc_name = chunk.get('document_name', '未知文档')
            positions = chunk.get('positions', [])
            image_id = chunk.get('image_id', '')

            pages = []
            try:
                pages = list(set([int(x[0]) for x in positions]))
            except:
                pass

            if doc_id in used_docs:
                used_docs[doc_id]['page'].extend(pages)
                used_docs[doc_id]['page'] = sorted(list(set(used_docs[doc_id]['page'])))
            else:
                ref_info = ReferenceInfo(
                    document_name=doc_name,
                    document_id=doc_id,
                    page=pages,
                    content=chunk.get('content', ''),
                    image_id=image_id,
                    positions=positions
                )
                used_docs[doc_id] = {'ref': ref_info, 'page': pages}
                references.append(ref_info)

        for ref in references:
            if ref.document_id in used_docs:
                ref.page = used_docs[ref.document_id]['page']

        return references

    def _format_references(self, references: List[ReferenceInfo]) -> str:
        """格式化参考文献为 Markdown"""
        if not references:
            return ""

        lines = ["\n### 参考文献\n"]
        for i, ref in enumerate(references, 1):
            doc_name = ref.document_name
            file_ext = os.path.splitext(doc_name)[1].lower()
            page_str = str(ref.page) if ref.page else ""

            if file_ext in ['.xlsx', '.xls', '.ppt', '.pptx']:
                link = f"{self.base_url}/v1/document/get/{ref.document_id}"
            else:
                ext = file_ext[1:] if file_ext else ""
                link = f"{self.base_url}/document/{ref.document_id}?ext={ext}&prefix=document"

            lines.append(f"- [{i}] [{doc_name}]({link}){page_str}")

        return "\n".join(lines)

    async def _send_references_async(
        self,
        references: List[ReferenceInfo],
        connection_manager,
        user_id: str
    ):
        """异步发送参考文献内容（通过WebSocket）"""
        for ref in references:
            try:
                content = await self._get_reference_content(ref)
                if content:
                    await connection_manager.send_message({
                        'type': 'reference_content',
                        'data': {
                            'document_name': ref.document_name,
                            'document_id': ref.document_id,
                            'content': content,
                            'page': ref.page
                        }
                    }, user_id)
            except Exception as e:
                print(f"发送参考文献失败: {e}")

    async def _get_reference_content(self, ref: ReferenceInfo) -> str:
        """获取参考文献内容"""
        ext = os.path.splitext(ref.document_name)[1].lower()
        return ref.content[:500] if ref.content else ""

    async def _generate_probe_keywords(self, answer: str) -> str:
        """生成病例检索关键词 - 完全按照V1版本逻辑"""
        try:
            # 尝试读取prompt文件
            prompt_path = os.path.join(
                os.path.dirname(__file__), '..', 'prompt', 'probe_prompt.txt'
            )
            if not os.path.exists(prompt_path):
                # 使用默认prompt（与V1版本一致）
                probe_prompt = """### 请严格按照以下步骤处理文本：
- 用一句话总结医学文本，必须包含关键信息
- 从总结中提取1-5个有代表性意义的英文关键词，关键词必须包含主题信息，必须是学术性的专业英语
- 精简英文单词数量，精简后的词语必须契合主题
### 输出格式
- 第一行输出总结，第二行输出英语关键词，第三行把英语单词精简为1-3个
- 英语单词以空格分开,不要使用标点符号
- 使用纯文本，不要用markdown格式
- 不要解释，不要评论
### 医学文本:
```
{answer}
```"""
            else:
                with open(prompt_path, 'r', encoding='utf-8') as f:
                    probe_prompt = f.read()

            probe_prompt = probe_prompt.replace("{answer}", answer)

            messages = [
                SystemMessage(content="你是一个经验丰富的医学专业英语编辑，帮助用户处理医学文本/no_think"),
                HumanMessage(content=probe_prompt)
            ]

            parser = StrOutputParser()

            # 最多尝试3次
            for i in range(3):
                try:
                    result = await asyncio.to_thread(
                        lambda: parser.invoke(self.llm.invoke(messages))
                    )

                    # 清理思考标签
                    result = self._clean_thinking_tags(result)

                    # 按行分割并过滤空行
                    sentence = result.replace("_", " ").split("\n")
                    sentence = [x for x in sentence if x.strip()]

                    # V1逻辑：第二行是长关键词，第三行是短关键词
                    if len(sentence) >= 3:
                        long_keywords = [x for x in sentence[1].split(" ") if x != '']
                        short_keywords = [x for x in sentence[2].split(" ") if x != '']

                        # 如果长关键词超过5个，使用短关键词
                        if len(long_keywords) > 5:
                            keywords = short_keywords
                        else:
                            keywords = long_keywords

                        # 检查是否为字母数字
                        if "".join(keywords).isalnum():
                            return " ".join(keywords)
                        else:
                            raise ValueError("输出格式错误：包含非字母数字字符")
                    else:
                        raise ValueError(f"输出格式错误：只有{len(sentence)}行，需要至少3行")

                except Exception as e:
                    print(f"关键词格式提取有误，第{i+1}遍重新提取: {e}")
                    if i < 2:  # 如果不是最后一次，添加修正消息
                        messages.append(
                            AIMessage(content=result if 'result' in locals() else "")
                        )
                        messages.append(
                            HumanMessage(content="你没有按照格式要求输出, 请重新输出。")
                        )
                    else:
                        # 最后一次尝试失败，返回空字符串
                        return ""

            return ""

        except Exception as e:
            print(f"生成关键词失败: {e}")
            return ""
