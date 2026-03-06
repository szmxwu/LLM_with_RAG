"""工具基类"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass
from pydantic import BaseModel
import asyncio
import time


class ToolParameters(BaseModel):
    """工具参数基类"""
    pass


@dataclass
class ToolResult:
    """工具结果"""
    success: bool
    data: Any
    error_message: Optional[str] = None
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseTool(ABC):
    """工具基类"""

    name: str = ""
    description: str = ""
    parameters_schema: type = ToolParameters

    # 性能配置
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 1.0

    def __init__(self, cache=None):
        self.cache = cache

    @abstractmethod
    async def _execute(self, params: Dict) -> ToolResult:
        """实际执行逻辑（子类实现）"""
        pass

    async def execute(self, params: Dict) -> ToolResult:
        """带保护的执行（重试、超时）"""
        # 参数验证
        try:
            validated = self._validate_params(params)
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"参数验证失败: {str(e)}"
            )

        # 检查缓存
        if self.cache:
            cache_key = self._make_cache_key(validated)
            cached = await self.cache.get(cache_key)
            if cached:
                return ToolResult(
                    success=True,
                    data=cached,
                    metadata={"cached": True}
                )

        # 执行（带重试）
        last_error = None
        for attempt in range(self.max_retries):
            try:
                start_time = time.time()
                result = await asyncio.wait_for(
                    self._execute(validated),
                    timeout=self.timeout
                )
                latency = time.time() - start_time

                # 缓存成功的结果
                if result.success and self.cache:
                    await self.cache.set(cache_key, result.data)

                # 添加元数据
                result.metadata.update({
                    "latency_ms": latency * 1000,
                    "attempt": attempt + 1
                })

                return result

            except asyncio.TimeoutError:
                last_error = f"执行超时({self.timeout}s)"
            except Exception as e:
                last_error = str(e)

            # 等待后重试
            if attempt < self.max_retries - 1:
                await asyncio.sleep(self.retry_delay * (2 ** attempt))

        # 所有重试都失败
        return ToolResult(
            success=False,
            data=None,
            error_message=f"重试{self.max_retries}次后仍失败: {last_error}"
        )

    def _validate_params(self, params: Dict) -> Dict:
        """验证参数"""
        if self.parameters_schema != ToolParameters:
            validated = self.parameters_schema(**params)
            return validated.model_dump()
        return params

    def _make_cache_key(self, params: Dict) -> str:
        """生成缓存键"""
        import hashlib
        import json
        param_str = json.dumps(params, sort_keys=True)
        # 使用SHA-256替代MD5（MD5已被证明不安全，仅用于缓存键生成场景风险较低）
        return f"{self.name}:{hashlib.sha256(param_str.encode()).hexdigest()[:32]}"

    def get_schema(self) -> Dict:
        """获取工具schema（用于LLM）"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema.schema() if hasattr(self.parameters_schema, 'schema') else {"type": "object", "properties": {}}
            }
        }
