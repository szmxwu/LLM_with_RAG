from typing import Dict, Generator
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferWindowMemory
from langchain_core.messages import HumanMessage, AIMessage,SystemMessage
from dotenv import load_dotenv
import os
load_dotenv()
# 访问环境变量
PATH_MATCH_REPLACE_FILE = 'documents/match_replace.xlsx'
LLM_NAME = os.getenv('LLM_NAME')
XINFERENCE = os.getenv('XINFERENCE')
ODBC = os.getenv('ODBC')
RERANK_ID = os.getenv('RERANK_ID')
EMBEDDING = os.getenv('EMBEDDING')
INTRODUCTION="""你叫做小语，是放射科医生的专业知识助手，帮助医生进行专业知识检索，诊断辅助决策。"""
try:
    with open('prompt\\introduction.txt') as f:
        content=f.read()
    if content.trim().replace("\n","")!="":
        INTRODUCTION=content
except:
    pass
class ChatAgent:
    def __init__(self):
        self.llm = ChatOpenAI(
            base_url=XINFERENCE,  # 本地模型API地址
            model=LLM_NAME,            # 模型名称
            temperature=0.1,
            max_tokens=4096,                    # 每次生成的最大token数
            api_key="EMPTY",
            streaming=True                      # 启用流式输出
        )
        self.memories: Dict[str, ConversationBufferWindowMemory] = {}
        self.system_prompt=INTRODUCTION

    def _get_memory(self, user_id: str) -> ConversationBufferWindowMemory:
        """获取指定用户的记忆存储"""
        if user_id not in self.memories:
             memory= ConversationBufferWindowMemory(
                llm=self.llm,
                k=10,
                return_messages=True
            )
             memory.chat_memory.add_message(SystemMessage(content=self.system_prompt))
             self.memories[user_id]=memory
        return self.memories[user_id]

    async def generate(self, user_id: str, query: str):
        """处理用户输入并生成流式响应"""
        memory = self._get_memory(user_id)
        
        # 构建对话历史
        history = memory.load_memory_variables({})["history"]
        messages = history + [HumanMessage(content=query)]
        
        # 流式生成响应
        response = ""
        for chunk in self.llm.stream(messages):
            response_chunk = chunk.content
            response += response_chunk
            yield response_chunk
        
        # 更新记忆存储
        memory.save_context(
            {"input": query},
            {"output": response}
        )

# 使用示例
if __name__ == "__main__":
    agent = ChatAgent()
    user_id = "user_001"
    
    # 模拟对话
    def mock_conversation():
        queries = [
            "你好，请介绍一下你自己",
            "能说说你的主要功能吗？",
            "请用Python写个快速排序算法"
        ]
        
        for query in queries:
            print(f"\n[用户] {query}")
            print("[AI] ", end="", flush=True)
            
            # 流式输出处理
            response = ""
            for token in agent.generate(user_id, query):
                print(token, end="", flush=True)
                response += token
            
            # 等待用户输入（模拟真实交互）
            input("\n\n按回车继续...")

    mock_conversation()