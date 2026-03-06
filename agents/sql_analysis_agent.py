"""
SQL分析Agent - 支持多步骤执行和Python代码执行

设计特点：
1. 支持复杂查询分解为多个简单步骤
2. 中间结果保存到临时表
3. Python代码执行能力用于连接中间结果
4. 流式输出执行过程
5. 最终生成图表PNG(base64)

安全机制：
1. 代码沙箱执行（受限环境）
2. SQL只读权限（SELECT ONLY）
3. 执行超时控制
4. 资源使用限制
"""

import ast
import base64
import io
import json
import os
import re
import sys
import time
import traceback
import tempfile
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Union
import uuid

# =============================================================================
# 关键：必须在导入任何数据库模块之前配置TLS兼容性
# 解决OpenSSL 3.0与SQL Server 2012的TLS兼容性问题
# =============================================================================

# 1. 先加载环境变量
from dotenv import load_dotenv
load_dotenv()

# 2. 检测是否需要TLS兼容性配置
odbc_str = os.getenv('ODBC', '')
if 'mssql' in odbc_str.lower() or 'sql' in odbc_str.lower():
    import ssl
    openssl_version = ssl.OPENSSL_VERSION
    version_parts = openssl_version.split()
    for part in version_parts:
        if part[0].isdigit():
            major_version = int(part.split('.')[0])
            if major_version >= 3:
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
                print(f"[TLS配置] 已设置OPENSSL_CONF以兼容SQL Server 2012: {config_path}")
                break

# 3. 现在导入数据库相关模块
# 从config.tls_compat导入其他可能需要的配置
from config.tls_compat import configure_tls_compatibility
configure_tls_compatibility()

import matplotlib
matplotlib.use('Agg')  # 非交互式后端
import matplotlib.pyplot as plt
import pandas as pd
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config.settings import settings


@dataclass
class ExecutionStep:
    """执行步骤"""
    step_id: str
    step_type: str  # 'sql' | 'python' | 'analysis'
    description: str
    code: str  # SQL或Python代码
    depends_on: List[str] = field(default_factory=list)

@dataclass
class StepResult:
    """步骤执行结果"""
    step_id: str
    status: str  # 'success' | 'error' | 'skipped'
    output: Any  # DataFrame或Python执行结果
    execution_time_ms: float
    error_message: Optional[str] = None
    stdout: str = ""  # Python标准输出
    row_count: int = 0


class PythonSandbox:
    """
    Python代码沙箱执行环境

    安全特性：
    1. 限制可用的内置函数
    2. 禁止危险操作（文件删除、网络等）
    3. 执行超时控制
    4. 资源使用监控
    """

    # 允许的内置函数白名单
    ALLOWED_BUILTINS = {
        'abs', 'all', 'any', 'bin', 'bool', 'bytearray', 'bytes',
        'chr', 'complex', 'dict', 'dir', 'divmod', 'enumerate',
        'filter', 'float', 'format', 'frozenset', 'hasattr', 'hash',
        'hex', 'int', 'isinstance', 'issubclass', 'iter', 'len',
        'list', 'map', 'max', 'min', 'next', 'oct', 'ord',
        'pow', 'print', 'range', 'repr', 'reversed', 'round',
        'set', 'slice', 'sorted', 'str', 'sum', 'tuple', 'type',
        'vars', 'zip', 'datetime', 'timedelta'
    }

    # 禁止的模块/函数模式
    FORBIDDEN_PATTERNS = [
        r'import\s+os\s+as',
        r'import\s+sys',
        r'import\s+subprocess',
        r'__import__',
        r'eval\s*\(',
        r'exec\s*\(',
        r'compile\s*\(',
        r'open\s*\(',
        r'file\s*\(',
        r'remove\s*\(',
        r'unlink\s*\(',
        r'rmdir\s*\(',
        r'system\s*\(',
        r'popen',
        r'fork',
        r'kill',
        r'execv',
    ]

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.globals_namespace = {}

    def _create_safe_import(self):
        """创建安全的导入函数"""
        allowed_modules = {'pandas', 'json', 're', 'datetime', 'collections', 'itertools', 'math', 'statistics'}

        def safe_import(name, *args, **kwargs):
            # 获取顶级模块名
            base_name = name.split('.')[0]
            if base_name in allowed_modules:
                return __import__(name, *args, **kwargs)
            raise ImportError(f"导入模块 '{name}' 不被允许")

        return safe_import

    def _create_safe_globals(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """创建安全的全局命名空间"""
        # 基础安全环境
        safe_builtins = {k: v for k, v in __builtins__.items()
                        if k in self.ALLOWED_BUILTINS}

        # 添加安全的__import__
        safe_builtins['__import__'] = self._create_safe_import()

        safe_globals = {
            '__builtins__': safe_builtins,
            'pd': pd,
            'json': json,
            're': re,
            'datetime': __import__('datetime'),
        }

        # 添加上下文变量（如前面步骤的结果）
        safe_globals.update(context)

        return safe_globals

    def _validate_code(self, code: str) -> Tuple[bool, str]:
        """验证代码安全性"""
        # 检查禁止模式
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, code, re.IGNORECASE):
                return False, f"代码包含禁止的操作模式: {pattern}"

        # 语法检查
        try:
            ast.parse(code)
        except SyntaxError as e:
            return False, f"语法错误: {str(e)}"

        return True, ""

    def execute(self, code: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        执行Python代码

        Args:
            code: Python代码字符串
            context: 上下文变量（如前面步骤的结果DataFrame）

        Returns:
            {
                'success': bool,
                'result': Any,  # 最后一个表达式的值或None
                'stdout': str,  # 标准输出捕获
                'stderr': str,  # 标准错误
                'error': str    # 错误信息（如果有）
            }
        """
        context = context or {}

        # 安全验证
        is_safe, error_msg = self._validate_code(code)
        if not is_safe:
            return {
                'success': False,
                'result': None,
                'stdout': '',
                'stderr': '',
                'error': f"安全验证失败: {error_msg}"
            }

        # 创建安全环境
        safe_globals = self._create_safe_globals(context)

        # 捕获输出
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        start_time = time.time()

        try:
            # 执行代码
            with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
                # 使用exec执行
                exec(code, safe_globals)

                # 尝试获取最后一个表达式的值（如果是表达式）
                result = None
                if code.strip():
                    try:
                        # 尝试作为表达式求值
                        result = eval(code.strip().split('\n')[-1], safe_globals)
                    except:
                        pass

            execution_time = (time.time() - start_time) * 1000

            return {
                'success': True,
                'result': result,
                'stdout': stdout_buffer.getvalue(),
                'stderr': stderr_buffer.getvalue(),
                'error': None,
                'execution_time_ms': execution_time
            }

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000

            return {
                'success': False,
                'result': None,
                'stdout': stdout_buffer.getvalue(),
                'stderr': stderr_buffer.getvalue(),
                'error': f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
            }


class SQLAnalysisAgent:
    """
    SQL分析Agent - 支持多步骤复杂查询

    核心能力：
    1. 查询分解：将复杂需求分解为多个简单SQL步骤
    2. 中间存储：使用临时表保存中间结果
    3. Python处理：使用Python连接、转换中间结果
    4. 流式输出：实时返回执行进度
    5. 图表生成：自动生成PNG图表（base64）
    """

    def __init__(self):
        self.llm = ChatOpenAI(
            base_url=settings.xinference_url,
            model=settings.llm_model,
            api_key=settings.llm_api_key,
            temperature=0.1,
            max_tokens=4096,
        )
        self.sandbox = PythonSandbox(timeout=30)
        self._steps_history: List[ExecutionStep] = []
        self._results_cache: Dict[str, StepResult] = {}

    async def _generate_execution_plan(self, question: str) -> List[ExecutionStep]:
        """
        生成执行计划

        分析用户需求，决定是单步执行还是多步执行
        """
        prompt = f"""你是一个SQL查询规划专家。请分析用户需求，决定如何执行。

用户需求：{question}

请判断：
1. 这个需求是否可以用单条SQL完成？
2. 如果需要多步，应该分解为哪些步骤？

输出格式（JSON）：
{{
    "is_complex": true/false,
    "reason": "为什么需要多步/单步",
    "steps": [
        {{
            "step_id": "step_1",
            "step_type": "sql",
            "description": "步骤描述",
            "code": "SQL代码"
        }},
        {{
            "step_id": "step_2",
            "step_type": "python",
            "description": "用Python处理上一步结果",
            "code": "Python代码，可以使用df_step_1访问上一步结果",
            "depends_on": ["step_1"]
        }}
    ]
}}

注意：
- 优先使用单条SQL，只有复杂需求才分解
- Python步骤可以使用前面SQL步骤的结果（变量名为 df_ + step_id）
- 最后一步应该生成最终分析结果"""

        messages = [
            SystemMessage(content="你是SQL查询规划专家。只输出JSON格式的执行计划。"),
            HumanMessage(content=prompt)
        ]

        response = await self.llm.ainvoke(messages)

        # 提取JSON
        try:
            content = response.content
            # 尝试提取JSON块
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0]
            elif '```' in content:
                content = content.split('```')[1].split('```')[0]

            plan = json.loads(content.strip())

            steps = []
            for step_data in plan.get('steps', []):
                steps.append(ExecutionStep(
                    step_id=step_data['step_id'],
                    step_type=step_data['step_type'],
                    description=step_data['description'],
                    code=step_data['code'],
                    depends_on=step_data.get('depends_on', [])
                ))

            return steps

        except Exception as e:
            # 降级：生成单步计划
            return [ExecutionStep(
                step_id="step_1",
                step_type="sql",
                description="直接查询",
                code="",  # 将在执行时生成
                depends_on=[]
            )]

    async def _execute_sql_step(
        self,
        step: ExecutionStep,
        context: Dict[str, Any]
    ) -> StepResult:
        """执行SQL步骤 - 使用子进程隔离执行以避免TLS配置问题"""
        import subprocess
        import asyncio

        start_time = time.time()

        try:
            # 如果code为空，需要生成SQL
            if not step.code.strip():
                from tools.sql_agent import SQLGenerationAgent
                sql_agent = SQLGenerationAgent()
                gen_result = await sql_agent.generate_sql(context.get('question', ''))
                sql_code = gen_result.sql
            else:
                sql_code = step.code

            # 替换上下文变量
            for var_name, var_value in context.items():
                if isinstance(var_value, pd.DataFrame):
                    placeholder = f"{{{{{var_name}}}}}"
                    if placeholder in sql_code:
                        pass

            # 在子进程中执行SQL（避免主进程的TLS配置问题）
            script_path = os.path.join(os.path.dirname(__file__), '..', 'sql_executor_subprocess.py')
            script_path = os.path.abspath(script_path)

            proc = await asyncio.create_subprocess_exec(
                sys.executable, script_path, settings.odbc_connection, sql_code,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='replace') or stdout.decode('utf-8', errors='replace')
                execution_time = (time.time() - start_time) * 1000
                return StepResult(
                    step_id=step.step_id,
                    status='error',
                    output=None,
                    execution_time_ms=execution_time,
                    error_message=f"子进程执行失败: {error_msg[:200]}",
                    row_count=0
                )

            result = json.loads(stdout.decode('utf-8'))

            if not result.get('success'):
                execution_time = (time.time() - start_time) * 1000
                return StepResult(
                    step_id=step.step_id,
                    status='error',
                    output=None,
                    execution_time_ms=execution_time,
                    error_message=result.get('error', '未知错误'),
                    row_count=0
                )

            # 转换结果为DataFrame
            df = pd.DataFrame(result.get('data', []), columns=result.get('columns', []))
            execution_time = (time.time() - start_time) * 1000

            return StepResult(
                step_id=step.step_id,
                status='success',
                output=df,
                execution_time_ms=execution_time,
                row_count=result.get('row_count', 0)
            )

        except asyncio.TimeoutError:
            execution_time = (time.time() - start_time) * 1000
            return StepResult(
                step_id=step.step_id,
                status='error',
                output=None,
                execution_time_ms=execution_time,
                error_message="SQL执行超时",
                row_count=0
            )

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            return StepResult(
                step_id=step.step_id,
                status='error',
                output=None,
                execution_time_ms=execution_time,
                error_message=str(e),
                row_count=0
            )

    async def _execute_python_step(
        self,
        step: ExecutionStep,
        context: Dict[str, Any]
    ) -> StepResult:
        """执行Python步骤"""
        start_time = time.time()

        # 准备上下文（前面步骤的结果）
        python_context = {}
        for var_name, var_value in context.items():
            if isinstance(var_value, pd.DataFrame):
                python_context[var_name] = var_value

        # 执行代码
        result = self.sandbox.execute(step.code, python_context)

        execution_time = (time.time() - start_time) * 1000

        # 获取结果（最后一个变量或result变量）
        output = result.get('result')
        if output is None and 'result' in result.get('globals', {}):
            output = result['globals']['result']

        return StepResult(
            step_id=step.step_id,
            status='success' if result['success'] else 'error',
            output=output,
            execution_time_ms=execution_time,
            error_message=result.get('error'),
            stdout=result.get('stdout', ''),
            row_count=len(output) if isinstance(output, pd.DataFrame) else 0
        )

    def _generate_chart_base64(self, df: pd.DataFrame, config: Dict[str, Any]) -> Optional[str]:
        """生成图表PNG并转为base64"""
        try:
            if df.empty or len(df) == 0:
                return None

            # 清除之前的图
            plt.clf()
            plt.close('all')

            # 创建新图
            fig, ax = plt.subplots(figsize=(10, 6))

            x_col = config.get('x_axis', df.columns[0] if len(df.columns) > 0 else None)
            y_col = config.get('y_axis', df.columns[1] if len(df.columns) > 1 else df.columns[0])

            if x_col and y_col and x_col in df.columns and y_col in df.columns:
                # 绘制柱状图
                df.plot(x=x_col, y=y_col, kind='bar', ax=ax)
                ax.set_title(config.get('title', '数据分析'))
                ax.set_xlabel(x_col)
                ax.set_ylabel(y_col)
                plt.xticks(rotation=45, ha='right')
                plt.tight_layout()

                # 转为base64
                buffer = io.BytesIO()
                fig.savefig(buffer, format='png', dpi=100, bbox_inches='tight')
                buffer.seek(0)
                image_base64 = base64.b64encode(buffer.read()).decode('utf-8')
                plt.close(fig)

                return image_base64

            return None

        except Exception as e:
            print(f"图表生成失败: {e}")
            return None

    async def analyze(
        self,
        question: str,
        session_id: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行分析流程（流式输出）

        Yields:
            {
                'type': 'plan' | 'step_start' | 'step_progress' | 'step_complete' | 'analysis' | 'chart' | 'final',
                'data': {...}
            }
        """
        session_id = session_id or str(uuid.uuid4())

        # 步骤1: 生成执行计划
        yield {
            'type': 'plan',
            'data': {
                'status': 'generating',
                'message': '正在分析需求并生成执行计划...'
            }
        }

        steps = await self._generate_execution_plan(question)

        yield {
            'type': 'plan',
            'data': {
                'status': 'complete',
                'steps_count': len(steps),
                'steps': [{'id': s.step_id, 'type': s.step_type, 'desc': s.description} for s in steps]
            }
        }

        # 步骤2: 依次执行每个步骤
        context = {'question': question}
        step_results = {}

        for step in steps:
            # 检查依赖
            for dep in step.depends_on:
                if dep not in step_results:
                    yield {
                        'type': 'error',
                        'data': {
                            'message': f"步骤 {step.step_id} 依赖 {dep} 未完成"
                        }
                    }
                    return

            # 开始执行
            yield {
                'type': 'step_start',
                'data': {
                    'step_id': step.step_id,
                    'step_type': step.step_type,
                    'description': step.description
                }
            }

            # 执行
            if step.step_type == 'sql':
                result = await self._execute_sql_step(step, context)
                # 保存结果到上下文
                context[f'df_{step.step_id}'] = result.output
            elif step.step_type == 'python':
                result = await self._execute_python_step(step, context)
                # 如果结果是DataFrame，保存到上下文
                if isinstance(result.output, pd.DataFrame):
                    context[f'df_{step.step_id}'] = result.output
            else:
                result = StepResult(
                    step_id=step.step_id,
                    status='error',
                    output=None,
                    execution_time_ms=0,
                    error_message=f"未知步骤类型: {step.step_type}"
                )

            step_results[step.step_id] = result

            # 输出结果
            yield {
                'type': 'step_complete',
                'data': {
                    'step_id': step.step_id,
                    'status': result.status,
                    'execution_time_ms': result.execution_time_ms,
                    'row_count': result.row_count,
                    'error_message': result.error_message,
                    'stdout': result.stdout if step.step_type == 'python' else None
                }
            }

            # 如果出错，停止执行
            if result.status == 'error':
                yield {
                    'type': 'error',
                    'data': {
                        'message': f"步骤 {step.step_id} 执行失败: {result.error_message}"
                    }
                }
                return

        # 步骤3: 获取最终结果
        final_step = steps[-1] if steps else None
        final_result = step_results.get(final_step.step_id) if final_step else None

        if final_result and isinstance(final_result.output, pd.DataFrame):
            df = final_result.output

            # 生成分析总结
            yield {
                'type': 'analysis',
                'data': {
                    'status': 'generating',
                    'message': '正在生成数据分析和可视化...'
                }
            }

            # 生成图表配置
            from tools.sql_agent import VisualizationAgent
            viz_agent = VisualizationAgent()
            viz_config = await viz_agent.generate_config(df, question, "")

            # 生成图表PNG
            chart_base64 = self._generate_chart_base64(df, {
                'x_axis': viz_config.x_axis,
                'y_axis': viz_config.y_axis,
                'title': viz_config.title
            })

            # 最终输出
            yield {
                'type': 'final',
                'data': {
                    'sql': '',  # 可以收集所有SQL步骤
                    'row_count': len(df),
                    'columns': df.columns.tolist(),
                    'data': df.head(100).to_dict(orient='records'),  # 限制返回行数
                    'visualization': {
                        'chart_type': viz_config.chart_type,
                        'title': viz_config.title,
                        'x_axis': viz_config.x_axis,
                        'y_axis': viz_config.y_axis
                    },
                    'chart_png_base64': chart_base64,
                    'execution_summary': {
                        'total_steps': len(steps),
                        'successful_steps': sum(1 for r in step_results.values() if r.status == 'success'),
                        'total_execution_time_ms': sum(r.execution_time_ms for r in step_results.values())
                    }
                }
            }
        else:
            yield {
                'type': 'error',
                'data': {
                    'message': '未获得有效的最终结果'
                }
            }


# 向后兼容的简化接口
async def analyze_sql_query(question: str, session_id: Optional[str] = None) -> AsyncGenerator[Dict[str, Any], None]:
    """
    简化接口：分析SQL查询（流式）

    使用示例：
        async for chunk in analyze_sql_query("统计各科室CT检查数量"):
            print(chunk)
    """
    agent = SQLAnalysisAgent()
    async for event in agent.analyze(question, session_id):
        yield event
