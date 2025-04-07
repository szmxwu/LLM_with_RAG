# agent_server
主服务文件
## llm_func文件
- 大模型处理的函数集：text2sql，符合率匹配，RAG，文件处理等
## RAGFLOW_SDK文件
- 与RAGFLOW 0.15交互的SDK，包括文件上传、下载、检索等功能，已修改官方bug

## process_docs文件
- 执行文件格式转化、分割的功能
  
## simple_agent
- 简单对话智能体，有短期记忆和自我认知

## knownlege_agent
- 知识智能体，能拆解复杂问题，查询rag并汇总回答
