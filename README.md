## agent_server
- 为符合率和RAG提供后端FASTAPI服务
- rag对话并返回文献图片，所有图片改为以base64编码发送
- 列出知识库中所有文档的状态
- 上传文件夹
- 删除文档
- 通过关键词检索病例库的病例并返回

# agent_server
主服务文件
## llm_func文件
- 大模型处理的函数集，包括意图判断，text2sql，符合率匹配，RAG四大类功能
- rag回复的格式![response](https://github.com/user-attachments/assets/d6434178-0fe1-4f04-84f4-27b1b1feb26f)
## RAGFLOW_SDK文件
- 与RAGFLOW 0.15交互的SDK，包括文件上传、下载、检索等功能，已修改官方bug

## process_docs文件
- 执行文件格式转化、分割的功能
  
## simple_agent
- 简单对话智能体，有短期记忆和自我认知

## knownlege_agent
- 知识智能体，能拆解复杂问题，查询rag并汇总回答
