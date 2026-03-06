"""
Text2SQL Agent - 基于Agent理念重构的SQL查询系统

将原有的 monolithic 函数拆分为独立的、可组合的Agent组件：
- SQLGenerationAgent: 负责自然语言到SQL的转换
- SQLExecutor: 负责SQL执行和错误修复
- VisualizationAgent: 负责生成图表配置
- SQLAnalysisPipeline: 编排整个流程
"""

# =============================================================================
# 关键：必须在导入pandas/sqlalchemy之前配置TLS兼容性
# 解决OpenSSL 3.0与SQL Server 2012的TLS兼容性问题
# =============================================================================
import os
import tempfile

# 检测是否需要TLS兼容性配置
odbc_str = os.getenv('ODBC', '')
if not odbc_str:  # 如果环境变量未加载，尝试加载.env
    try:
        from dotenv import load_dotenv
        load_dotenv()
        odbc_str = os.getenv('ODBC', '')
    except ImportError:
        pass

if 'mssql' in odbc_str.lower() or 'sql' in odbc_str.lower():
    try:
        import ssl
        openssl_version = ssl.OPENSSL_VERSION
        version_parts = openssl_version.split()
        for part in version_parts:
            if part[0].isdigit():
                major_version = int(part.split('.')[0])
                if major_version >= 3 and not os.environ.get('OPENSSL_CONF'):
                    # 创建OpenSSL配置文件
                    openssl_config = """# OpenSSL配置允许遗留算法
openssl_conf = default_conf
[default_conf]
ssl_conf = ssl_sect
[ssl_sect]
system_default = system_default_sect
[system_default_sect]
CipherString = DEFAULT:@SECLEVEL=0
"""
                    config_path = os.path.join(tempfile.gettempdir(), 'openssl-legacy.cnf')
                    with open(config_path, 'w') as f:
                        f.write(openssl_config)
                    os.environ['OPENSSL_CONF'] = config_path
                    print(f"[TLS配置] tools/sql_agent.py 已设置OPENSSL_CONF: {config_path}")
                    break
    except Exception:
        pass  # 静默处理错误，不阻止正常导入

# 现在导入其他模块
import json
import re
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from enum import Enum

import pandas as pd
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from langchain_openai import ChatOpenAI

from config.settings import settings
from tools.base import BaseTool, ToolResult, ToolParameters


class SQLExecutionStatus(str, Enum):
    """SQL执行状态"""
    SUCCESS = "success"
    SYNTAX_ERROR = "syntax_error"
    EMPTY_RESULT = "empty_result"
    PERMISSION_DENIED = "permission_denied"
    CONNECTION_ERROR = "connection_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class SQLGenerationResult:
    """SQL生成结果"""
    sql: str
    explanation: str
    confidence: float
    examples_used: List[str]
    raw_response: str


@dataclass
class SQLExecutionResult:
    """SQL执行结果"""
    status: SQLExecutionStatus
    data: Optional[pd.DataFrame]
    row_count: int
    execution_time_ms: float
    error_message: Optional[str] = None
    retry_count: int = 0


@dataclass
class VisualizationConfig:
    """可视化配置"""
    chart_type: str  # bar, line, pie, table
    x_axis: Optional[str]
    y_axis: Optional[str]
    title: str
    description: str
    config: Dict[str, Any]


class SQLGenerationAgent:
    """
    SQL生成Agent - 专门负责自然语言到SQL的转换

    职责：
    1. 检索相似的SQL示例
    2. 构建优化的Prompt
    3. 调用LLM生成SQL
    4. 提取和验证SQL
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            base_url=settings.xinference_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=0.1,  # 低温度保证SQL准确性
            max_tokens=2048,
        )
        self.system_prompt = """你是一个专业的SQL工程师，擅长将自然语言问题转换为精确的SQL查询。

规则：
1. 只输出标准的SQL SELECT语句
2. 使用正确的表名和列名
3. 对检查类型使用标准缩写：DR(平片/X线)、CT、MR(磁共振)、US(超声/B超)、ES(内镜)、PS(病理)
4. 日期字段使用标准格式：StudyDate
5. 输出格式必须包含在 ```sql 和 ``` 之间

注意：数据库是MSSQL，使用T-SQL语法。"""

    def _retrieve_examples(self, question: str, top_k: int = 3) -> List[str]:
        """检索相似的SQL示例"""
        try:
            from legacy.RAGFLOW_SDK import Retrieve_chunks
            examples = Retrieve_chunks(question, 'SQL', "rmyy_DB.xlsx", top_k)
            return [d.content.replace("\\n", "").replace("\n", "").replace("\'", "'")
                    for d in examples]
        except Exception as e:
            print(f"检索SQL示例失败: {e}")
            return []

    def _normalize_check_type(self, sql: str) -> str:
        """标准化检查类型名称"""
        replacements = {
            r'B超|超声|彩超': 'US',
            r'病理|免疫组化': 'PS',
            r'内镜|胃肠镜|胃镜|肠镜|阴道镜|宫腔镜': 'ES',
            r'磁共振|MRI|核磁|核磁共振': 'MR',
            r'平片|普放|X片|X线片|X线': 'DR',
        }
        for pattern, replacement in replacements.items():
            sql = re.sub(pattern, replacement, sql, flags=re.IGNORECASE)
        return sql

    async def generate_sql(self, question: str) -> SQLGenerationResult:
        """
        生成SQL查询

        Args:
            question: 自然语言问题

        Returns:
            SQLGenerationResult 包含生成的SQL和元数据
        """
        # 1. 检索示例
        examples = self._retrieve_examples(question)
        examples_text = "\n\n".join(examples) if examples else "无示例"

        # 2. 构建Prompt
        prompt = f"""请根据以下示例，将问题转换为SQL查询。

示例：
{examples_text}

用户问题：
{question}

请生成SQL查询，并简要解释你的思路。
"""

        # 3. 调用LLM
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt)
        ]

        response = await self.llm.ainvoke(messages)
        raw_response = response.content

        # 4. 提取SQL
        sql = self._extract_sql(raw_response)
        sql = self._normalize_check_type(sql)

        # 5. 提取解释
        explanation = self._extract_explanation(raw_response)

        # 6. 计算置信度（简单启发式）
        confidence = self._calculate_confidence(sql, examples)

        return SQLGenerationResult(
            sql=sql,
            explanation=explanation,
            confidence=confidence,
            examples_used=examples,
            raw_response=raw_response
        )

    def _extract_sql(self, text: str) -> str:
        """从响应中提取SQL"""
        # 尝试提取代码块
        patterns = [
            r'```sql(.*?)```',
            r'```(.*?)```',
            r'SELECT.*?;',
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                sql = match.group(1) if 'sql' in pattern or '```' in pattern else match.group(0)
                return sql.strip()
        return text.strip()

    def _extract_explanation(self, text: str) -> str:
        """提取解释部分"""
        # 移除SQL代码块后剩余的部分
        text_without_sql = re.sub(r'```sql.*?```', '', text, flags=re.DOTALL)
        return text_without_sql.strip()[:200]  # 限制长度

    def _calculate_confidence(self, sql: str, examples: List[str]) -> float:
        """计算置信度分数"""
        score = 0.5

        # 有示例增加置信度
        if examples:
            score += 0.2

        # 包含SELECT增加置信度
        if 'SELECT' in sql.upper():
            score += 0.15

        # 包含FROM增加置信度
        if 'FROM' in sql.upper():
            score += 0.15

        return min(score, 1.0)


class SQLExecutor:
    """
    SQL执行器 - 负责执行SQL和错误修复

    职责：
    1. 执行SQL查询
    2. 捕获和处理错误
    3. 自动修复SQL错误（有限次数重试）
    4. 返回结构化结果
    """

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
        self.llm = ChatOpenAI(
            base_url=settings.xinference_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=0.1,
            max_tokens=2048,
        )

    def _get_engine(self):
        """获取数据库引擎"""
        import sqlalchemy as sql
        return sql.create_engine(settings.odbc_connection)

    def _classify_error(self, error: Exception) -> SQLExecutionStatus:
        """分类错误类型"""
        error_str = str(error).lower()

        if 'syntax' in error_str or 'incorrect' in error_str:
            return SQLExecutionStatus.SYNTAX_ERROR
        elif 'permission' in error_str or 'access' in error_str:
            return SQLExecutionStatus.PERMISSION_DENIED
        elif 'connection' in error_str or 'timeout' in error_str:
            return SQLExecutionStatus.CONNECTION_ERROR
        else:
            return SQLExecutionStatus.UNKNOWN_ERROR

    async def _repair_sql(self, sql: str, error: str, question: str) -> str:
        """修复SQL错误"""
        prompt = f"""以下SQL查询执行出错，请修复后重新输出。

原始问题：{question}

当前SQL：
```sql
{sql}
```

错误信息：
{error}

请输出修复后的SQL（仅输出SQL，不要解释）："""

        messages = [
            SystemMessage(content="你是一个SQL调试专家。只输出修复后的SQL代码，不要解释。"),
            HumanMessage(content=prompt)
        ]

        response = await self.llm.ainvoke(messages)

        # 提取SQL
        sql_pattern = r'```sql(.*?)```'
        match = re.search(sql_pattern, response.content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # 如果没有代码块，尝试直接返回
        return response.content.strip()

    async def execute(
        self,
        sql: str,
        question: str,
        retry_count: int = 0
    ) -> SQLExecutionResult:
        """
        执行SQL查询 - 使用子进程隔离执行以避免TLS配置问题

        Args:
            sql: SQL查询字符串
            question: 原始问题（用于错误修复）
            retry_count: 当前重试次数

        Returns:
            SQLExecutionResult 包含执行结果和元数据
        """
        import time
        import asyncio
        import subprocess
        import json
        import os
        import sys

        start_time = time.time()

        try:
            # 在子进程中执行SQL（避免主进程的TLS配置问题）
            script_path = os.path.join(os.path.dirname(__file__), '..', 'sql_executor_subprocess.py')
            script_path = os.path.abspath(script_path)

            proc = await asyncio.create_subprocess_exec(
                sys.executable, script_path, settings.odbc_connection, sql,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace') or stdout.decode('utf-8', errors='replace')
                execution_time = (time.time() - start_time) * 1000
                return SQLExecutionResult(
                    status=SQLExecutionStatus.CONNECTION_ERROR,
                    data=None,
                    row_count=0,
                    execution_time_ms=execution_time,
                    error_message=f"子进程执行失败: {error_msg[:200]}",
                    retry_count=retry_count
                )

            result = json.loads(stdout.decode('utf-8'))

            if not result.get('success'):
                execution_time = (time.time() - start_time) * 1000
                error_msg = result.get('error', '未知错误')
                return SQLExecutionResult(
                    status=self._classify_error(Exception(error_msg)),
                    data=None,
                    row_count=0,
                    execution_time_ms=execution_time,
                    error_message=error_msg,
                    retry_count=retry_count
                )

            # 转换结果为DataFrame
            df = pd.DataFrame(result.get('data', []), columns=result.get('columns', []))
            execution_time = (time.time() - start_time) * 1000

            # 检查结果是否为空
            if df.empty:
                return SQLExecutionResult(
                    status=SQLExecutionStatus.EMPTY_RESULT,
                    data=df,
                    row_count=0,
                    execution_time_ms=execution_time,
                    retry_count=retry_count
                )

            return SQLExecutionResult(
                status=SQLExecutionStatus.SUCCESS,
                data=df,
                row_count=result.get('row_count', 0),
                execution_time_ms=execution_time,
                retry_count=retry_count
            )

        except asyncio.TimeoutError:
            execution_time = (time.time() - start_time) * 1000
            return SQLExecutionResult(
                status=SQLExecutionStatus.CONNECTION_ERROR,
                data=None,
                row_count=0,
                execution_time_ms=execution_time,
                error_message="SQL执行超时",
                retry_count=retry_count
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_type = self._classify_error(e)
            error_msg = str(e)

            # 尝试修复（如果是语法错误且未达到最大重试次数）
            if error_type == SQLExecutionStatus.SYNTAX_ERROR and retry_count < self.max_retries:
                print(f"SQL执行失败（第{retry_count + 1}次重试）: {error_msg[:100]}")
                repaired_sql = await self._repair_sql(sql, error_msg, question)
                return await self.execute(repaired_sql, question, retry_count + 1)

            return SQLExecutionResult(
                status=error_type,
                data=None,
                row_count=0,
                execution_time_ms=execution_time,
                error_message=error_msg,
                retry_count=retry_count
            )


class VisualizationAgent:
    """
    可视化Agent - 负责生成图表配置

    职责：
    1. 分析数据特征
    2. 推荐合适的图表类型
    3. 生成图表配置
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            base_url=settings.xinference_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=0.2,
            max_tokens=1024,
        )

    def _infer_chart_type(self, df: pd.DataFrame) -> str:
        """根据数据特征推断图表类型"""
        if df.empty or len(df) == 0:
            return "table"

        # 单列数据适合饼图
        if len(df.columns) == 1:
            return "pie"

        # 时间序列数据适合折线图
        time_keywords = ['date', 'time', 'year', 'month', 'day']
        for col in df.columns:
            if any(kw in col.lower() for kw in time_keywords):
                return "line"

        # 少量类别适合柱状图
        if len(df) <= 10:
            return "bar"

        # 默认表格
        return "table"

    async def generate_config(
        self,
        df: pd.DataFrame,
        question: str,
        sql: str
    ) -> VisualizationConfig:
        """
        生成可视化配置

        Args:
            df: 查询结果DataFrame
            question: 原始问题
            sql: 执行的SQL

        Returns:
            VisualizationConfig 图表配置
        """
        if df.empty:
            return VisualizationConfig(
                chart_type="table",
                x_axis=None,
                y_axis=None,
                title="查询结果",
                description="数据为空",
                config={}
            )

        # 推断图表类型
        chart_type = self._infer_chart_type(df)

        # 选择坐标轴
        columns = df.columns.tolist()
        x_axis = columns[0] if len(columns) > 0 else None
        y_axis = columns[1] if len(columns) > 1 else columns[0]

        # 生成标题
        title = self._generate_title(question, chart_type)

        # 构建配置
        config = {
            "data": df.to_dict(orient='records'),
            "columns": columns,
            "row_count": len(df)
        }

        return VisualizationConfig(
            chart_type=chart_type,
            x_axis=x_axis,
            y_axis=y_axis,
            title=title,
            description=f"基于查询生成的{chart_type}图表",
            config=config
        )

    def _generate_title(self, question: str, chart_type: str) -> str:
        """生成图表标题"""
        # 简化问题作为标题
        title = question[:30] + "..." if len(question) > 30 else question
        type_names = {
            "bar": "柱状图",
            "line": "趋势图",
            "pie": "饼图",
            "table": "数据表"
        }
        return f"{title} - {type_names.get(chart_type, chart_type)}"


class SQLAnalysisPipeline:
    """
    SQL分析流水线 - 编排整个Text2SQL流程

    使用方式：
        pipeline = SQLAnalysisPipeline()
        result = await pipeline.run("统计上个月CT检查数量")
    """

    def __init__(self):
        self.sql_agent = SQLGenerationAgent()
        self.executor = SQLExecutor(max_retries=3)
        self.viz_agent = VisualizationAgent()

    async def run(self, question: str) -> Dict[str, Any]:
        """
        执行完整的Text2SQL流程

        Args:
            question: 自然语言问题

        Returns:
            包含sql、data、visualization、metadata的字典
        """
        # 步骤1: 生成SQL
        generation_result = await self.sql_agent.generate_sql(question)

        # 步骤2: 执行SQL
        execution_result = await self.executor.execute(
            generation_result.sql,
            question
        )

        # 步骤3: 生成可视化配置（如果执行成功）
        viz_config = None
        if execution_result.status == SQLExecutionStatus.SUCCESS:
            viz_config = await self.viz_agent.generate_config(
                execution_result.data,
                question,
                generation_result.sql
            )

        # 构建返回结果
        return {
            "sql": generation_result.sql,
            "sql_explanation": generation_result.explanation,
            "sql_confidence": generation_result.confidence,
            "execution_status": execution_result.status.value,
            "data": execution_result.data.to_dict(orient='records') if execution_result.data is not None else [],
            "row_count": execution_result.row_count,
            "execution_time_ms": execution_result.execution_time_ms,
            "retry_count": execution_result.retry_count,
            "error_message": execution_result.error_message,
            "visualization": {
                "chart_type": viz_config.chart_type if viz_config else None,
                "title": viz_config.title if viz_config else None,
                "x_axis": viz_config.x_axis if viz_config else None,
                "y_axis": viz_config.y_axis if viz_config else None,
                "config": viz_config.config if viz_config else {}
            } if viz_config else None
        }


# 保持向后兼容的包装函数
async def get_LLM_SQL_async(question: str) -> Tuple[str, Optional[Dict], pd.DataFrame]:
    """
    异步版本的get_LLM_SQL（向后兼容）

    Returns:
        (sql_str, viz_config, df)
    """
    pipeline = SQLAnalysisPipeline()
    result = await pipeline.run(question)

    # 转换回旧的返回格式
    df = pd.DataFrame(result["data"]) if result["data"] else pd.DataFrame()
    viz_config = result["visualization"]["config"] if result["visualization"] else []

    return result["sql"], viz_config, df


def get_LLM_SQL(question: str) -> Tuple[str, Optional[Dict], pd.DataFrame]:
    """
    同步版本的get_LLM_SQL（向后兼容）
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(get_LLM_SQL_async(question))
