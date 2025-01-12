# LLM_with_RAG
原大模型功能集成到一个项目中
## llm_func文件
- 大模型处理的函数集，包括意图判断，text2sql，符合率匹配，RAG四大类功能
- rag回复的格式![response](https://github.com/user-attachments/assets/d6434178-0fe1-4f04-84f4-27b1b1feb26f)
- rag回复的后面必须生成追问关键词，用户点击后查询病例知识库，并返回结果显示在新的页面上
- 生成关键词使用generate_probe函数，检索病例库使用search_case函数
## RAGFLOW_SDK文件
- 与RAGFLOW 0.14.1交互的SDK，包括文件上传、下载、检索等功能

## python_api_reference
- 官方文档
## process_docs文件
- 执行文件格式转化、分割的功能
  
## 尚未完成
- 文件上传和下载功能不能正常工作
- 与gradio界面的交互未完成
- 其他功能待完善
