# -*- coding: utf-8 -*-
import json
import asyncio
import aiohttp
import os
import re
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
from RAGFLOW_SDK import Query_steam as query
from llm_func import get_img_base64

# 配置项
XINFERENCE = os.getenv('XINFERENCE')
LLM_NAME = os.getenv('LLM_NAME')
MAX_WORKERS = 8
CACHE_TTL = 3600
BASE_URL = os.getenv('BASE_URL')

class LLMClient:
    """直接调用模型API的客户端"""
    def __init__(self):
        self.session=None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            base_url=XINFERENCE.replace("/v1",""),
            headers={"Authorization": "EMPTY"},
            timeout=aiohttp.ClientTimeout(total=30)
        )
        return self 
    async def __aexit__(self,exc_type,exc_val,exc_tb):
        await self.close()
    
    async def chat_completion(self, messages,stream=False):
        """直接调用模型API"""
        if not self.session:
            raise RuntimeError("Session not initialized")
        if not stream:
            async with self.session.post(
                "/v1/chat/completions",
                json={
                    "model": LLM_NAME,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens":6144
                }
            ) as response:
                res= await response.json()
                return res['choices'][0]['message']['content']
        else:
            async with self.session.post(
                "/v1/chat/completions",
                json={
                    "model": LLM_NAME,
                    "messages": messages,
                    "temperature": 0.1,
                    "max_tokens":6144,
                    "stream":True
                }
            ) as response:
                async for line in response.content:
                    if line.strip():
                        chunk=json.loads(line.decode('utf-8'))
                        yield chunk
    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


class JSONProcessor:
    """JSON处理工具"""
    
    @staticmethod
    def extract_json(content: str):
        """提取并修正JSON"""
        for i in range(3):
            try:
                match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
                return json.loads(content)
            except json.JSONDecodeError:
                content = JSONProcessor.fix_json(content)
                print(f"json格式错误，正在修复第{i+1}次")
        return None
    
    @staticmethod
    async def fix_json(content: str):
        """异步修正JSON"""
        async with LLMClient() as client:
            response = await client.chat_completion([{
                "role": "user",
                "content": f"修正以下文本为标准JSON，不要解释：{content}"
            }])
        return response['choices'][0]['message']['content']

class QueryProcessor:
    """核心查询处理器"""
    
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    
    @lru_cache(maxsize=1024)
    def _rag_query(self, q: str, chat_name: str):
        """带缓存的RAG查询"""
        answer = query(q, chat_name)
        reference_chunks = []
        for ans in answer:
            indexes = re.findall(r"##(\d+)\$\$", ans.content)
            reference_chunks.extend(
                ans.reference[int(idx)] for idx in indexes
            )
        return ans.content, reference_chunks
    
    async def query_async(self, question: str, chat_name: str):
        """异步查询入口"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._rag_query,
            question,
            chat_name
        )

class KnowledgeAgent:
    """增强型知识服务Agent"""
    
    def __init__(self):
        self.query_processor = QueryProcessor()
        self.llm_client = None
    
    async def __aenter__(self):
        self.llm_client=LLMClient()
        await self.llm_client.__aenter__()
        return self
    async def __aexit__(self,exc_type,exc_val,exc_tb):
        await self.llm_client.close()
    
    async def process_complex(self, question: str, chat_name: str):
        """处理复杂问题的完整流程"""
        sub_questions = await self._split_question(question)
        tasks = [
            self.query_processor.query_async(q, chat_name)
            for q in sub_questions
        ]
        answers = await asyncio.gather(*tasks)
        sub_answers = list(zip(sub_questions, answers))  # 配对子问题和答案
        sub_answers=[sub for sub in sub_answers if "知识库中未找到" not in sub[1][0]] #过滤低质量信息
        async for chunk in self._aggregate_answers(question, sub_answers, chat_name):
            yield chunk
    
    async def _split_question(self, question: str):
        """问题拆分逻辑"""
        response = await self.llm_client.chat_completion([{
            "role": "user",
            "content": f"""拆分复杂问题：'{question}',生成2-5个独立子问题,每个问题一行。
                        不要解释，不要评论
                        """
        }])
        result = response.split("\n")
        result.append(question)
        return result
    
    async def generate_report(self,answer:tuple)->str:
        """生成规范的报告格式
        """
        content=answer[0]
        reference_chunks=answer[1]
        ref_index=1
        refs=re.findall(r"##\d+\$\$",content)
        for r in refs:
            if r:
                content=content.replace(r,f'<span style="color:blue;">[{ref_index}]</span>')
                ref_index+=1

        graphs="\n### 图例\n"
        references = "\n### 参考文献\n"
        index = 1
        for chunk in reference_chunks:
            extension = os.path.splitext(chunk['document_name'])[1]
            extension = extension[1:]
            try:
                chunk['page'] = list(set([int(x[0]) for x in chunk['positions']]))
            except:
                chunk['page'] = []
            if extension in ['xlsx', 'xls', 'ppt', 'pptx']:
                # 以上文件类型为下载链接
                references += f"- [{index}] [{chunk['document_name']}]({BASE_URL}/v1/document/get/{chunk['document_id']}){chunk['page']}\n"
            else:
                # 以上文件类型为预览链接
                references += f"- [{index}] [{chunk['document_name']}]({BASE_URL}/document/{chunk['document_id']}?ext={extension}&prefix=document){chunk['page']}\n"
            index += 1
            if chunk['image_id']:
                graphs+=f"**{chunk['document_name']}**\n"
                image_base64=get_img_base64(chunk['image_id'])
                await asyncio.sleep(0)
                # image_base64=""
                graphs += f'<img src="data:image/png;base64,{image_base64}" alt="图片" style="width: 800px;height:auto;image-rendering: crisp-edges; "><br>'
                graphs+="【图片说明】"+chunk['content']+"\n"
        return content+"\n"+graphs+references
    
    async def _aggregate_answers(self, question: str, sub_answers: list, chat_name: str):
        """增强版答案聚合器（包含子问题详情）"""
        structured_data = {
            "原始问题": question,
            "子问题分析": [{"子问题": q, "回答": a[0]} for q, a in sub_answers],
        }

        # 生成初始报告部分
        report = f"## 您的问题:\n- {question}\n## 思考过程:\n"
        sequence_number = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
        index = 0
        
        # 流式输出初始报告
        yield report
        
        # 流式输出每个子问题的分析
        for q, a in sub_answers:
            sub_report = await self.generate_report(a)
            section = '<div><h3 style="color:#8B0000;">'+sequence_number[index]+". "+ q+"</h3></div><br>"
            section+=sub_report+"\n"
            for line in section.split("\n"):
                yield line + "\n"
                await asyncio.sleep(0.01)  # 模拟流式输出间隔
            index += 1
        
        
         # 生成最终总结部分
        messages=[{
            "role": "user",
            "content": f"""
                    结构化整合报告生成要求：
                    1. 按以下格式组织：
                    - 分析过程：
                    {{按顺序列出每个子问题及其回答的要点，使用编号列表}}
                    - 综合总结：[包含关键点提炼和对比分析]
                    
                    输入数据：
                    {structured_data}
                    
                    请生成完整的技术报告，使用中文Markdown格式，保持专业医学风格
                    """
            }]
        async for chunk in self.llm_client.chat_completion(messages=messages,stream=True):
            if 'choices' in chunk:
                delta=chunk['choices'][0].get('delta',{}).get('content','')
                if delta:
                    yield delta


    async def _decide_rag_usage(self, question: str):
        """判断是否需要使用RAG"""
        response = await self.llm_client.chat_completion([{
            "role": "user",
            "content": f"""判断问题是否需要使用医学知识库回答。
                    如果是闲聊或不需要医学专业知识的，返回"不需要"，否则返回"需要"。不要解释，不要评论
                    问题："{question}"
                    """
        }])
        print("RAG:",response)
        if "不需要" in response:
            return  False
        else:
            return True

    async def main_chain(self, question: str, chat_name: str = "小影"):
        """主处理流程"""
        # 是否需要RAG判断
        need_rag = await self._decide_rag_usage(question)
        
        if not need_rag:
            # 直接生成对话回复
            response = await self.llm_client.chat_completion([{
                "role": "user",
                "content": question
            }])
            yield response
        else:
            # 问题复杂度判断
            response = await self.llm_client.chat_completion([{
                "role": "user",
                "content": f"根据是否能拆分子问题来判断问题复杂度：{question}。返回\"简单|复杂\"，不要解释，不要评论"
            }])
            
            print(f"【{response}】")
            if  '简单' in response:
                result = await self.query_processor.query_async(question, chat_name)
                yield result[0]
            else:
                async for chunk in self.process_complex(question, chat_name):
                    yield chunk

# 使用示例
if __name__ == "__main__":
    async def stream_output():
        async with KnowledgeAgent() as agent:
            async for chunk in agent.main_chain(
                question="来源于卵巢的，在MRI强化比较弱，弥散不受限的肿瘤可能有哪些？",
                chat_name="小影"
            ):
                print(chunk, end='', flush=True)
    
    # async def stream_output(messages):
    #     llm_client=LLMClient
    #     async for chunk in llm_client.chat_completion(messages,stream=True):
    #         if 'choices' in chunk:
    #             print(chunk)
    # messages={
    #     "role": "user",
    #     "content": f"介绍你自己"
    # }
    asyncio.run(stream_output())

            