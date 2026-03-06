"""配置管理 - 使用Pydantic Settings"""

import os
from typing import Optional, List
from enum import Enum
from pydantic import Field
from pydantic_settings import BaseSettings


class ThinkingMode(str, Enum):
    """思考强度模式 - Qwen模型支持/no_think和/think指令"""
    NO_THINK = "no_think"      # /no_think - 非推理模式，快速响应
    THINK = "think"            # /think - 标准推理模式（默认）
    DEEP_THINK = "deep_think"  # /think + 额外提示 - 深度推理模式


class Settings(BaseSettings):
    """应用配置"""

    # LLM配置
    xinference_url: str = Field(default="http://192.0.0.193:9997/v1", alias="XINFERENCE")
    llm_model: str = Field(default="qwen3-30b", alias="LLM_NAME")
    llm_api_key: str = Field(default="EMPTY", alias="LLM_KEY")
    embedding_model: str = Field(default="bge-large-zh-v1.5", alias="EMBEDDING")

    # 外部重排序服务配置（独立Xinference服务）
    rerank_url: str = Field(default="http://192.0.0.188:9997/v1", alias="RERANK_URL")
    rerank_model: str = Field(default="bge-reranker-v2-m3", alias="RERANK_MODEL")
    # 旧版兼容
    rerank_id: str = Field(default="bge-reranker-v2-m3", alias="RERANK_ID")

    # RAGFlow配置
    ragflow_url: str = Field(default="http://192.0.0.193:6080", alias="BASE_URL")
    ragflow_api_key: str = Field(default="ragflow-key", alias="API_KEY")
    agent_id: str = Field(default="", alias="AGENT_ID")

    # 数据库配置
    odbc_connection: str = Field(default="", alias="ODBC")

    # 默认数据集
    default_dataset: str = Field(default="放射学", alias="DEFAUT_DATA")
    default_case_dataset: str = Field(default="病例", alias="DEFAUT_CASE")

    # 服务端配置
    host_ip: str = Field(default="0.0.0.0:6081", alias="HOST_IP")
    endpoint_ip: str = Field(default="http://localhost:3000", alias="ENDPOINT_IP")
    max_file_upload_mb: int = Field(default=2048, alias="MAX_FILE_UPLOAD")

    # Agent配置
    max_plan_steps: int = 10
    max_retry_count: int = 3
    timeout_seconds: float = 60.0

    # 思考强度控制
    default_thinking_mode: ThinkingMode = Field(
        default=ThinkingMode.THINK,
        description="默认思考模式: no_think(快速), think(标准), deep_think(深度)"
    )

    # 不同任务的默认思考模式
    simple_task_thinking: ThinkingMode = ThinkingMode.NO_THINK   # 简单任务快速响应
    moderate_task_thinking: ThinkingMode = ThinkingMode.THINK    # 中等任务标准推理
    complex_task_thinking: ThinkingMode = ThinkingMode.DEEP_THINK # 复杂任务深度推理

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# 全局配置实例
settings = Settings()
