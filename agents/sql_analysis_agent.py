"""
SQL分析Agent - 基于工具调用的简化架构

设计特点：
1. 提供预定义工具（数据库查询、Excel读写、数据合并）
2. LLM只负责生成SQL和决策，不生成复杂Python代码
3. 工具执行由Agent控制，保证稳定性
4. 数据库查询使用子进程隔离，避免TLS问题
"""

import asyncio
import base64
import io
import json
import os
import subprocess
import sys
import time
import traceback
import tempfile
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Union
import uuid

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config.settings import settings


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any
    error_message: Optional[str] = None
    row_count: int = 0
    execution_time_ms: float = 0


class DatabaseTool:
    """数据库查询工具 - 使用子进程隔离TLS问题"""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string

    async def execute(self, sql: str, timeout: int = 30) -> ToolResult:
        """执行SQL查询"""
        start_time = time.time()

        try:
            script_path = os.path.join(
                os.path.dirname(__file__), '..', 'sql_executor_subprocess.py'
            )
            script_path = os.path.abspath(script_path)

            proc = await asyncio.create_subprocess_exec(
                sys.executable, script_path, self.connection_string, sql,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            execution_time = (time.time() - start_time) * 1000

            if proc.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace')[:500]
                return ToolResult(
                    success=False,
                    data=None,
                    error_message=f"子进程执行失败: {error_msg}",
                    execution_time_ms=execution_time
                )

            stdout_text = stdout.decode('utf-8', errors='replace')

            # 检查子进程是否有错误输出
            if stderr:
                stderr_text = stderr.decode('utf-8', errors='replace')
                if stderr_text.strip():
                    print(f"[SQL Subprocess STDERR] {stderr_text[:500]}")

            try:
                result = json.loads(stdout_text)
            except json.JSONDecodeError as e:
                print(f"[SQL Subprocess JSON Error] {e}, stdout: {stdout_text[:500]}")
                return ToolResult(
                    success=False,
                    data=None,
                    error_message=f"子进程输出解析失败: {e}",
                    execution_time_ms=execution_time
                )

            if not result.get('success'):
                error_msg = result.get('error', '未知错误')
                print(f"[SQL Subprocess Error] {error_msg[:500]}")
                return ToolResult(
                    success=False,
                    data=None,
                    error_message=error_msg,
                    execution_time_ms=execution_time
                )

            df = pd.DataFrame(result.get('data', []), columns=result.get('columns', []))
            return ToolResult(
                success=True,
                data=df,
                row_count=len(df),
                execution_time_ms=execution_time
            )

        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                data=None,
                error_message="SQL执行超时",
                execution_time_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )


class ExcelTool:
    """Excel文件操作工具"""

    @staticmethod
    def read(file_path: str) -> ToolResult:
        """读取Excel文件"""
        start_time = time.time()
        try:
            df = pd.read_excel(file_path)
            return ToolResult(
                success=True,
                data=df,
                row_count=len(df),
                execution_time_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"读取Excel失败: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000
            )

    @staticmethod
    def write(df: pd.DataFrame, file_path: str) -> ToolResult:
        """写入Excel文件"""
        start_time = time.time()
        try:
            df.to_excel(file_path, index=False)
            return ToolResult(
                success=True,
                data=file_path,
                row_count=len(df),
                execution_time_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"写入Excel失败: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000
            )


class DataTool:
    """数据处理工具"""

    @staticmethod
    def merge(left_df: pd.DataFrame, right_df: pd.DataFrame,
              left_on: str, right_on: str = None,
              how: str = 'left') -> ToolResult:
        """合并两个DataFrame，确保保留left_df的所有行"""
        start_time = time.time()
        try:
            right_on = right_on or left_on

            # 如果right_df有重复，先按left_on去重（保留第一条）
            if right_df.duplicated(subset=[right_on]).any():
                print(f"[DataTool] 检测到数据库结果中有重复{right_on}，进行去重")
                right_df = right_df.drop_duplicates(subset=[right_on], keep='first')

            merged = left_df.merge(
                right_df, left_on=left_on, right_on=right_on, how=how
            )

            # 确保合并后行数与left_df相同
            if len(merged) != len(left_df):
                print(f"[DataTool] 警告: 合并后行数({len(merged)})与原始Excel({len(left_df)})不一致")

            return ToolResult(
                success=True,
                data=merged,
                row_count=len(merged),
                execution_time_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"合并数据失败: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000
            )

    @staticmethod
    def add_column(df: pd.DataFrame, column_name: str, values: List) -> ToolResult:
        """添加列到DataFrame"""
        start_time = time.time()
        try:
            df_copy = df.copy()
            df_copy[column_name] = values
            return ToolResult(
                success=True,
                data=df_copy,
                row_count=len(df_copy),
                execution_time_ms=(time.time() - start_time) * 1000
            )
        except Exception as e:
            return ToolResult(
                success=False,
                data=None,
                error_message=f"添加列失败: {str(e)}",
                execution_time_ms=(time.time() - start_time) * 1000
            )


class SQLAnalysisAgent:
    """
    SQL分析Agent - 基于工具调用架构

    核心能力：
    1. Excel读取：使用ExcelTool.read
    2. 数据库查询：使用DatabaseTool.execute（子进程隔离）
    3. 数据合并：使用DataTool.merge/add_column
    4. Excel写入：使用ExcelTool.write
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            base_url=settings.xinference_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=0.1,
            max_tokens=4096,
        )
        self.db_tool = DatabaseTool(settings.odbc_connection)
        self._db_schema = self._load_db_schema()

    def _load_db_schema(self) -> str:
        """加载数据库结构提示词"""
        try:
            prompt_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                'prompt', 'sql_prompt.json'
            )
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt_data = json.load(f)
                template = prompt_data.get('template', '')
                # 提取数据库信息部分
                if '## 数据库信息:' in template:
                    schema = template.split('## 数据库信息:')[1].split('## 生成SQL的步骤:')[0]
                    return schema.strip()
                return template
        except Exception as e:
            print(f"[Warning] 无法加载数据库结构: {e}")
            # 返回基础表结构
            return """
### 检查信息表(tRegorder)
- `AccNo`: 字符串类型，检查流水号
- `CurPatientName`: 字符串类型，患者中文名字
- `ApplyDept`: 字符串类型，申请科室名称
- `OrderGuid`: 字符串类型，检查信息的全局唯一标识符

### 检查报告表(tReport)
- `ReportGuid`: 字符串类型，报告全局唯一标识符
- `WYSText`: 字符串类型，检查报告中的描述内容
- `WYGText`: 字符串类型，检查报告中的结论内容
- `CreateDt`: 时间戳类型，报告提交时间

### 检查流程表(tRegProcedure)
- `OrderGuid`: 字符串类型，关联tRegorder
- `ReportGuid`: 字符串类型，关联tReport
- `CheckingItem`: 字符串类型，检查部位项目名称
- `ModalityType`: 字符串类型，设备类型[DR,CT,MR,MG]
"""

    def _extract_file_path(self, question: str) -> Optional[str]:
        """从question中提取文件路径"""
        import re
        # 匹配常见的文件路径模式
        patterns = [
            r'读取Excel文件[：:]\s*(\S+)',
            r'文件路径[：:]\s*(\S+)',
            r'([\w/\\]+\.xlsx?)',
            r'([\w/\\]+\.csv)',
        ]
        for pattern in patterns:
            match = re.search(pattern, question)
            if match:
                return match.group(1)
        return None

    def _parse_uploaded_file(self, question: str) -> tuple:
        """从question中解析上传文件信息"""
        import re

        file_path = None
        original_name = None

        # 匹配上传文件信息
        path_match = re.search(r'文件路径:\s*(\S+)', question)
        name_match = re.search(r'原始文件名:\s*(\S+)', question)

        if path_match:
            file_path = path_match.group(1)
        if name_match:
            original_name = name_match.group(1)

        return file_path, original_name

    async def _analyze_task(self, question: str) -> Dict[str, Any]:
        """
        分析任务，生成执行计划

        LLM只负责：
        1. 判断需要哪些步骤
        2. 指定表名、列名、文件路径（简单字符串）
        3. 不生成复杂SQL，只指定查询条件
        """
        # 解析上传文件信息
        uploaded_file, original_name = self._parse_uploaded_file(question)

        # 确定输出路径
        if uploaded_file:
            # 使用上传文件所在目录作为输出目录
            import uuid
            output_dir = os.path.dirname(uploaded_file)
            output_path = os.path.join(output_dir, f"{uuid.uuid4().hex}_result.xlsx")
            file_path = uploaded_file
        else:
            # 从question中提取文件路径或使用默认路径
            file_path = self._extract_file_path(question) or ""
            output_path = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}_result.xlsx")

        prompt = f"""你是一个数据分析助手。请分析用户需求，生成执行计划。

可用工具：
1. read_excel(file_path) - 读取Excel文件
2. query_database(table, columns, filter_column) - 查询数据库
3. merge_data(left_var, right_var, on_column) - 合并数据
4. write_excel(file_path) - 保存Excel

用户需求：
{question}

请分析需求并输出JSON格式的执行计划：
{{
    "task_type": "excel_sql_merge",
    "file_path": "输入Excel文件路径",
    "output_path": "输出Excel文件路径",
    "tables": ["需要查询的数据库表名列表"],
    "columns": ["需要查询的列名"],
    "join_column": "用于关联的列名（如AccNo）"
}}

当前上下文：
- 输入文件路径: {file_path}
- 输出文件路径: {output_path}

注意：
- 只输出JSON，不要包含任何代码或解释
- 如果用户上传了文件，使用提供的输入文件路径
- 输出文件路径已提供，请在计划中使用
- 表名和列名使用原始名称"""

        messages = [
            SystemMessage(content="你是数据分析助手。只输出JSON格式的执行计划。"),
            HumanMessage(content=prompt)
        ]

        response = await self.llm.ainvoke(messages)

        try:
            content = response.content

            # 去除think标签
            if '<think>' in content and '</think>' in content:
                content = content.split('</think>')[1]

            # 提取JSON
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            plan = json.loads(content.strip())
            return plan

        except Exception as e:
            print(f"[Plan Error] {e}, raw: {response.content[:500]}")
            # 返回默认计划
            return {
                "task_type": "unknown",
                "steps": []
            }

    async def _generate_sql_for_accnos(self, accnos: List[str], columns_info: str) -> str:
        """
        为给定的AccNo列表生成批量查询SQL

        使用数据库结构提示词让LLM生成正确的SQL
        """
        # 构建IN子句（限制数量避免SQL过长）
        accnos_list = [f"'{a}'" for a in accnos[:300]]  # 最多300个，避免SQL过长
        in_clause = ', '.join(accnos_list)

        prompt = f"""根据以下数据库结构，生成SQL Server查询语句。

## 数据库结构:
{self._db_schema}

## 查询需求:
查询给定AccNo列表对应的数据。
需要查询的字段: {columns_info}
AccNo列表: {in_clause[:300]}...

## 重要规则:
1. 使用正确的表名和字段名
2. 如果涉及多个表，使用JOIN关联（tRegorder通过OrderGuid关联tRegProcedure，tRegProcedure通过ReportGuid关联tReport）
3. 使用IN子句筛选AccNo
4. **不要添加日期范围限制** - 因为已经提供了具体的AccNo列表，这些是唯一标识符，不需要再用日期筛选
5. 只输出SQL语句，不要解释

## SQL:"""

        messages = [
            SystemMessage(content="你是SQL Server专家。根据数据库结构生成正确的查询语句。"),
            HumanMessage(content=prompt)
        ]

        response = await self.llm.ainvoke(messages)
        content = response.content.strip()

        # 去除think标签（Qwen模型）
        if '<think>' in content and '</think>' in content:
            content = content.split('</think>')[1]

        # 提取SQL代码块
        if '```sql' in content:
            content = content.split('```sql')[1].split('```')[0]
        elif '```' in content:
            content = content.split('```')[1].split('```')[0]

        sql = content.strip()

        # 清理SQL中的注释和多余空白
        import re
        sql = re.sub(r'--.*?$', '', sql, flags=re.MULTILINE)  # 移除单行注释
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)  # 移除多行注释
        sql = ' '.join(sql.split())  # 规范化空白

        print(f"[Generated SQL] {sql[:300]}...")
        return sql

    async def analyze(
        self,
        question: str,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行分析流程（流式输出）
        """
        session_id = session_id or str(uuid.uuid4())

        # 步骤1: 分析任务
        yield {'type': 'analysis', 'data': {'stage': 'analyzing', 'message': '分析任务需求...'}}

        plan = await self._analyze_task(question)

        if not plan.get('file_path') or not plan.get('tables'):
            yield {'type': 'error', 'data': {'message': '无法生成执行计划'}}
            return

        # 构建执行步骤
        steps = [
            {'step': 1, 'tool': 'read_excel', 'desc': f"读取Excel: {plan.get('file_path', '')}"},
            {'step': 2, 'tool': 'query_database', 'desc': f"查询数据库表: {', '.join(plan.get('tables', []))}"},
            {'step': 3, 'tool': 'merge_data', 'desc': f"合并数据（关联列: {plan.get('join_column', '')}）"},
            {'step': 4, 'tool': 'write_excel', 'desc': f"保存Excel: {plan.get('output_path', '')}"}
        ]

        yield {
            'type': 'plan',
            'data': {
                'status': 'complete',
                'steps_count': len(steps),
                'steps': steps
            }
        }

        # 步骤2: 执行各步骤
        context = {}  # 存储中间结果
        total_time = 0

        # Step 1: 读取Excel
        yield {'type': 'step_start', 'data': {'step_id': '1', 'tool': 'read_excel', 'description': '读取Excel文件'}}

        result = ExcelTool.read(plan['file_path'])
        total_time += result.execution_time_ms

        if not result.success:
            yield {'type': 'step_complete', 'data': {'step_id': '1', 'status': 'error', 'error_message': result.error_message}}
            yield {'type': 'error', 'data': {'message': f"读取Excel失败: {result.error_message}"}}
            return

        df_excel = result.data
        context['df_excel'] = df_excel

        # 获取AccNo列表
        join_column = plan.get('join_column', 'AccNo')
        if join_column in df_excel.columns:
            context['accnos'] = df_excel[join_column].dropna().unique().tolist()
        else:
            context['accnos'] = []

        yield {'type': 'step_complete', 'data': {'step_id': '1', 'status': 'success', 'row_count': result.row_count, 'execution_time_ms': result.execution_time_ms}}

        # Step 2: 查询数据库（让LLM生成正确的SQL）
        yield {'type': 'step_start', 'data': {'step_id': '2', 'tool': 'query_database', 'description': '查询数据库'}}

        accnos = context.get('accnos', [])[:300]  # 限制数量避免SQL过长

        if not accnos:
            yield {'type': 'step_complete', 'data': {'step_id': '2', 'status': 'error', 'error_message': '没有有效的AccNo用于查询'}}
            yield {'type': 'error', 'data': {'message': 'Excel文件中没有有效的AccNo'}}
            return

        # 根据问题内容决定查询哪些字段
        columns_info = "AccNo"
        question_lower = question.lower()
        if any(k in question_lower for k in ['报告', '结论', '诊断', 'wys', 'wyg']):
            columns_info += ", 报告描述(WYSText)和报告结论(WYGText)"
        if any(k in question_lower for k in ['检查时间', '检查日期', '时间']):
            columns_info += ", 检查时间(CreateDt或ExamineDt)"
        if any(k in question_lower for k in ['患者', '姓名', '病人']):
            columns_info += ", 患者姓名(CurPatientName)"
        if any(k in question_lower for k in ['科室', '申请']):
            columns_info += ", 申请科室(ApplyDept)"

        # 让LLM生成正确的SQL
        sql = await self._generate_sql_for_accnos(accnos, columns_info)
        print(f"[SQL] {sql[:300]}...")

        result = await self.db_tool.execute(sql)
        total_time += result.execution_time_ms

        if not result.success:
            yield {'type': 'step_complete', 'data': {'step_id': '2', 'status': 'error', 'error_message': result.error_message}}
            yield {'type': 'error', 'data': {'message': f"数据库查询失败: {result.error_message}"}}
            return

        context['df_db'] = result.data

        yield {'type': 'step_complete', 'data': {'step_id': '2', 'status': 'success', 'row_count': len(context['df_db']), 'execution_time_ms': total_time}}

        # Step 3: 合并数据
        yield {'type': 'step_start', 'data': {'step_id': '3', 'tool': 'merge_data', 'description': '合并Excel和数据库数据'}}

        result = DataTool.merge(df_excel, context['df_db'], join_column, join_column, 'left')
        total_time += result.execution_time_ms

        if not result.success:
            yield {'type': 'step_complete', 'data': {'step_id': '3', 'status': 'error', 'error_message': result.error_message}}
            yield {'type': 'error', 'data': {'message': f"合并数据失败: {result.error_message}"}}
            return

        context['df_merged'] = result.data
        yield {'type': 'step_complete', 'data': {'step_id': '3', 'status': 'success', 'row_count': result.row_count, 'execution_time_ms': result.execution_time_ms}}

        # Step 4: 写入Excel
        yield {'type': 'step_start', 'data': {'step_id': '4', 'tool': 'write_excel', 'description': '保存结果到Excel'}}

        output_path = plan.get('output_path', '/tmp/output.xlsx')
        result = ExcelTool.write(context['df_merged'], output_path)
        total_time += result.execution_time_ms

        if not result.success:
            yield {'type': 'step_complete', 'data': {'step_id': '4', 'status': 'error', 'error_message': result.error_message}}
            yield {'type': 'error', 'data': {'message': f"保存Excel失败: {result.error_message}"}}
            return

        yield {'type': 'step_complete', 'data': {'step_id': '4', 'status': 'success', 'row_count': result.row_count, 'execution_time_ms': result.execution_time_ms}}

        # 步骤3: 返回最终结果
        final_df = context.get('df_merged')

        # 获取输出文件路径
        output_path = plan.get('output_path', '')

        if final_df is not None and isinstance(final_df, pd.DataFrame):
            # 生成图表
            chart_base64 = self._generate_chart(final_df)

            yield {
                'type': 'final',
                'data': {
                    'status': 'success',
                    'row_count': len(final_df),
                    'columns': final_df.columns.tolist(),
                    'data': final_df.head(100).to_dict(orient='records'),
                    'output_file': output_path,
                    'chart_png_base64': chart_base64,
                    'execution_summary': {
                        'total_steps': len(steps),
                        'total_execution_time_ms': total_time
                    }
                }
            }
        else:
            yield {
                'type': 'final',
                'data': {
                    'status': 'success',
                    'message': '任务完成',
                    'execution_summary': {
                        'total_steps': len(steps),
                        'total_execution_time_ms': total_time
                    }
                }
            }

    def _generate_chart(self, df: pd.DataFrame) -> Optional[str]:
        """生成图表"""
        try:
            if df.empty or len(df.columns) < 2:
                return None

            plt.clf()
            plt.close('all')

            fig, ax = plt.subplots(figsize=(10, 6))

            # 简单柱状图
            numeric_cols = df.select_dtypes(include=['number']).columns
            if len(numeric_cols) > 0:
                y_col = numeric_cols[0]
                x_col = df.columns[0] if df.columns[0] != y_col else df.columns[1]

                if x_col in df.columns and y_col in df.columns:
                    df.head(20).plot(x=x_col, y=y_col, kind='bar', ax=ax)
                    ax.set_title('数据分析')
                    plt.xticks(rotation=45, ha='right')
                    plt.tight_layout()

                    buffer = io.BytesIO()
                    fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
                    buffer.seek(0)
                    image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
                    plt.close(fig)
                    return image_base64

            return None
        except Exception as e:
            print(f"[Chart Error] {e}")
            return None


# 向后兼容的简化接口
async def analyze_sql_query(question: str, session_id: Optional[str] = None):
    """简化接口"""
    agent = SQLAnalysisAgent()
    async for event in agent.analyze(question, session_id):
        yield event
