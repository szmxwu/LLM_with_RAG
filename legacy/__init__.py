"""Legacy模块 - 兼容旧项目的代码

包含从原项目迁移的依赖代码，用于保持兼容性。
这些代码将逐步被新架构替代。
"""

import sys
import os

# 将legacy目录添加到路径，以便内部模块间能正常进行绝对导入
# 注意：这仅添加当前目录(legacy/)，不依赖父目录，确保模块独立性
_legacy_dir = os.path.dirname(os.path.abspath(__file__))
if _legacy_dir not in sys.path:
    sys.path.insert(0, _legacy_dir)

# 导出常用的函数和类，方便导入
try:
    from llm_func import (
        Match_result_LLM,
        Match_complex_result,
        get_LLM_SQL,
        Query_steam,
        generate_probe,
        search_case,
    )

    from RAGFLOW_SDK import (
        Retrieve_chunks,
        Download_document,
        List_documents,
        Upload_documents,
        List_datasets,
        Create_dataset,
        Delete_documents,
        Parse_documents,
        Stop_parsing,
        BASE_URL,
        Agent_chat,
        Show_all_datasets,
        Show_all_docs,
        List_chunks,
        init_chat_agent,
        Query_steam as RAGQuery_steam,
        upload_single_file,
        Create_session,
    )
except ImportError as e:
    # 如果导入失败，打印警告但不做处理
    # 这允许在没有所有依赖的情况下部分使用
    import warnings
    warnings.warn(f"Legacy模块部分导入失败: {e}")

    # 定义占位函数
    def _placeholder(*args, **kwargs):
        raise NotImplementedError("Legacy模块未完全加载")

    Match_result_LLM = _placeholder
    Match_complex_result = _placeholder
    get_LLM_SQL = _placeholder
    Query_steam = _placeholder
    generate_probe = _placeholder
    search_case = _placeholder
    Retrieve_chunks = _placeholder
    init_chat_agent = _placeholder
    Create_session = _placeholder
    upload_single_file = _placeholder

__all__ = [
    # llm_func
    "Match_result_LLM",
    "Match_complex_result",
    "get_LLM_SQL",
    "Query_steam",
    "generate_probe",
    "search_case",
    # RAGFLOW_SDK
    "Retrieve_chunks",
    "Download_document",
    "List_documents",
    "Upload_documents",
    "List_datasets",
    "Create_dataset",
    "Delete_documents",
    "Parse_documents",
    "Stop_parsing",
    "BASE_URL",
    "Agent_chat",
    "Show_all_datasets",
    "Show_all_docs",
    "List_chunks",
    "init_chat_agent",
    "RAGQuery_steam",
    "upload_single_file",
    "Create_session",
]
