# -*- coding: utf-8 -*-
from langchain.prompts import ChatPromptTemplate
from langchain.schema.runnable import RunnableLambda, RunnableParallel
from langchain.tools import tool
from langchain_openai import ChatOpenAI
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
import asyncio
import json
from RAGFLOW_SDK import Query_steam as query
from dotenv import load_dotenv
from llm_func import get_img_base64
import os
import re
load_dotenv()
# 初始化配置
XINFERENCE = os.getenv('XINFERENCE')  # 本地推理服务地址
LLM_NAME = os.getenv('LLM_NAME')            
MAX_WORKERS = 8                       # 并行处理线程数
CACHE_TTL = 3600                      # 缓存有效期
BASE_URL= os.getenv('BASE_URL')
INTRODUCTION="""你叫做小语，是放射科医生的专业知识助手，帮助医生进行专业知识检索，诊断辅助决策。"""
try:
    with open('prompt\\introduction.txt') as f:
        content=f.read()
    if content.trim().replace("\n","")!="":
        INTRODUCTION=content
except:
    pass
# 初始化LLM（带本地缓存）
llm = ChatOpenAI(
    base_url=XINFERENCE,
    model=LLM_NAME,
    api_key="EMPTY",
    max_retries=3,
    request_timeout=30
)
def get_json(content):
    for i in range(3):
        try:
            if "json" in content:
                match = re.search(r'```json\n(.*?)\n```', content, re.DOTALL)
                if match:
                    # 提取json字符串
                    json_str = match.group(1)
                    return json.loads(json_str)
            else:
                return json.loads(content)
        except:
            prompt = ChatPromptTemplate.from_template("""
                修正以下文本为标准的json格式，确保你的输出能被json.loads读取，不要解释，不要评论
                "{content}" 
            """)
            chain = prompt | llm
            result = chain.ainvoke({"content": content})
            content=result.content
            print(f"第{i+1}次修正json错误")

async def generate_report(answer:tuple)->str:
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
        # print(chunk)
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
        if chunk['image_id'] and 'ppt' not in  extension:
            graphs+=f"**{chunk['document_name']}**\n"
            image_base64=get_img_base64(chunk['image_id'])
            await asyncio.sleep(0)
            # image_base64=""
            graphs += f'<img src="data:image/png;base64,{image_base64}" alt="图片" style="width: 800px;height:auto;image-rendering: crisp-edges; "><br>'
            graphs+="【图片说明】"+chunk['content']+"\n"
    return content+"\n"+graphs+references

# ================= 核心工具 =================
# @tool
def Query_steam(question: str,chat_name:str) -> str:
    """增强版RAG问答工具（带本地缓存）"""
    @lru_cache(maxsize=1024)
    def _rag_query(q: str,chat_name:str):
        # 实际RAG系统调用逻辑
        answer=query(q,chat_name)
        for ans in answer:
            #print(ans.content[len(cont):], end='', flush=True)
            pass
        reference_index = re.findall(r"##(\d+)\$\$", ans.content)
        if reference_index:
            reference_index = [int(x) for x in reference_index]
        reference_chunks = []
        for index, ref in enumerate(ans.reference):
            if index in reference_index:
                reference_chunks.append(ref)
        # print(f"【子问题】{q}\n【回答】{ans.content}")
        return ans.content,reference_chunks
    
    return _rag_query(question,chat_name)

# ================= 优化组件 =================
class OptimizedProcessor:
    """性能优化处理器"""
    
    @staticmethod
    async def classify_question(question: str) -> dict:
        """带缓存的问题分类器"""
        prompt = ChatPromptTemplate.from_template("""
            判断问题复杂度："{question}" 
            返回JSON：{{"type":"简单|复杂", "reason":"分类依据"}}
        """)
        chain = prompt | llm.with_fallbacks([llm]*2)  # 故障转移
        result=await chain.ainvoke({"question": question})
        return get_json(result.content)
    @staticmethod
    async def decide_rag_usage(question: str)->bool:
        """判断是否需要使用RAG"""
        prompt = ChatPromptTemplate.from_template("""
                    判断问题是否需要使用医学知识库回答。
                    如果是闲聊或不需要医学专业知识的，返回"不需要"，否则返回"需要"。不要解释，不要评论
                    问题："{question}"
                """)
        chain = prompt | llm.with_fallbacks([llm]*2)  # 故障转移
        response=await chain.ainvoke({"question": question})
        if "不需要" in response.content:
            return  False
        else:
            return True
    
    @staticmethod
    async def split_question(question: str) -> list:
        """异步问题拆分器"""
        prompt = ChatPromptTemplate.from_template("""
            你是一个经验丰富的放射科主任医师，你需要拆分复杂问题："{question}" 
            生成2-4个独立子问题，每个子问题必须围绕复杂问题提到的人体器官展开
            输出格式：每个子问题单独一行，不要解释，不要评论
        """)
        chain = prompt | llm
        result = await chain.ainvoke({"question": question})
        questions=result.content.split("\n")
        questions.append(question)
        return questions
    
    @staticmethod
    async def aggregate_answers(question: str, sub_answers: list):
        """增强版答案聚合器（包含子问题详情）"""
        structured_data = {
            "原始问题": question,
            "子问题分析": [{"子问题": q, "回答": a[0]} for q, a in sub_answers],
        }

        # 生成初始报告部分
        report = f"## 您的问题:\n- {question}\n## 思考过程:\n"
        sequence_number = ['一', '二', '三', '四', '五', '六', '七', '八', '九', '十']
        sub_index = 0
        
        # 流式输出初始报告
        yield report
        images=[]
        # 流式输出每个子问题的分析
        for q, a in sub_answers:
            #对image去重
            content=a[0]
            reference_chunks=a[1]
            for index in range(len(reference_chunks)):
                if reference_chunks[index]['image_id'] in images:
                    reference_chunks[index]['image_id']=None
            images.extend([chunk['image_id'] for chunk in reference_chunks if chunk['image_id']])
            #生成结构化的报告
            sub_report = await generate_report((content,reference_chunks))
            section = '<div><h3 style="color:#8B0000;">'+sequence_number[sub_index]+". "+ q+"</h3></div><br>"
            # print(section)
            section+=sub_report+"\n"
            sub_index += 1
            for line in section.split("\n"):
                yield line + "\n"
                await asyncio.sleep(0.01)  # 模拟流式输出间隔
            

        # 生成最终总结部分
        prompt = ChatPromptTemplate.from_template("""
            结构化整合报告生成要求：
            1. 按以下格式组织：
            - 分析过程：
              {{按顺序列出每个子问题及其回答的要点，使用编号列表}}
            - 综合总结：[包含关键点提炼和对比分析]
            
            输入数据：
            {structured_data}
            
            请生成完整的总结报告，使用中文Markdown格式，保持专业医学风格
        """)
        chain = prompt | llm
        async for chunk in chain.astream({"structured_data": json.dumps(structured_data, ensure_ascii=False)},
                                        config={"max_tokens": 8192}):
            yield chunk.content
        # print(images)

# ================= 主Agent =================
class KnowledgeAgent:
    """增强型知识服务Agent"""
    
    def __init__(self):
        self.processor = OptimizedProcessor()
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
        
    async def process_complex(self, question: str,chat_name:str) :
        """改进后的复杂问题处理流水线"""
        try:
            sub_questions = await self.processor.split_question(question)
            
            # 获取子问题答案对
            tasks = [asyncio.wait_for(
                self._query_async(q,chat_name), 
                timeout=100
            ) for q in sub_questions]
            
            answers = await asyncio.gather(*tasks)
            sub_answers = list(zip(sub_questions, answers))  # 配对子问题和答案
            sub_answers=[sub for sub in sub_answers if re.search("知识库[中]未" ,sub[1][0]) is None] #过滤低质量信息
            async for chunk in self.processor.aggregate_answers(question, sub_answers):
                yield chunk
            
        except asyncio.TimeoutError:
            yield "处理超时，请简化您的问题"
    
    async def _query_async(self, question: str,chat_name:str) -> str:
        """异步查询执行器"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor, 
            Query_steam, 
            question,chat_name
        )
    
    async def main_chain(self, question: str,chat_name:str="小影") :
        """主处理链"""
        rag=await self.processor.decide_rag_usage(question)
        global INTRODUCTION
        if not rag:
            prompt = ChatPromptTemplate.from_template("""{INTRODUCTION}
                                                      请问答以下问题：
                                                      '{question}'""")
            chain = prompt | llm
            async for chunk in chain.astream({"question": question,"INTRODUCTION":INTRODUCTION}):
                yield chunk.content
        else:
            classification = await self.processor.classify_question(question)
            if classification["type"] == "简单":
                print("【简单问题】")
                result= Query_steam(question,chat_name)
                yield await generate_report(result) 
            else:
                print("【复杂问题】")
                async for chunk in self.process_complex(question,chat_name):
                    yield chunk

# ================= 使用示例 =================
if __name__ == "__main__":
    async def stream_output():
        agent = KnowledgeAgent()
        chat_name="小影"
        question = "肠梗阻分哪些类型？"
        question = "介绍你自己"
        # 关键修改：直接迭代main_chain返回的生成器
        async for chunk in agent.main_chain(question,chat_name):
            print(chunk, end='', flush=True)
            # pass

    asyncio.run(stream_output())
