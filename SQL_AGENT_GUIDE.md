# SQL分析Agent使用指南

## 概述

新的SQL分析Agent采用先进的Agent架构，支持复杂查询的多步骤执行、Python代码处理和流式输出。

## 核心特性

### 1. 多步骤执行
- 自动分析查询复杂度，决定单步或多步执行
- 中间结果保存，支持步骤间数据传递
- 支持Python代码执行连接中间结果

### 2. 安全沙箱
- Python代码在受限环境中执行
- 只允许导入白名单模块（pandas, json, re等）
- 禁止危险操作（文件删除、网络访问等）

### 3. 流式输出
- 实时返回执行进度
- 每个步骤的开始、进度、完成都有通知
- 支持长连接（SSE）

### 4. 图表生成
- 自动生成柱状图PNG（base64编码）
- 根据数据特征智能选择图表类型
- 支持自定义图表配置

## API接口

### 1. 流式分析接口（推荐）

```http
POST /v2/sql/analyze
Content-Type: application/json

{
    "question": "统计上个月各科室CT检查的人次和收入",
    "session_id": "可选的会话ID"
}
```

返回：`text/event-stream` (SSE)

事件类型：
- `plan`: 执行计划生成
- `step_start`: 步骤开始
- `step_complete`: 步骤完成
- `analysis`: 数据分析中
- `final`: 最终结果
- `error`: 错误

示例响应流：
```json
data: {"type": "plan", "data": {"status": "generating", "message": "..."}}
data: {"type": "plan", "data": {"status": "complete", "steps_count": 2, "steps": [...]}}
data: {"type": "step_start", "data": {"step_id": "step_1", "step_type": "sql", "description": "..."}}
data: {"type": "step_complete", "data": {"step_id": "step_1", "status": "success", "row_count": 10}}
data: {"type": "final", "data": {"sql": "...", "data": [...], "chart_png_base64": "..."}}
```

### 2. 简单查询接口

```http
POST /v2/sql/simple
Content-Type: application/json

{
    "question": "统计CT检查数量"
}
```

返回：JSON（非流式）

## 架构设计

```
SQLAnalysisAgent
├── SQLGenerationAgent    # 生成SQL
├── SQLExecutor          # 执行SQL（带重试）
├── VisualizationAgent   # 生成图表配置
├── PythonSandbox        # 安全执行Python
└── _generate_execution_plan  # 规划执行步骤
```

执行流程：
```
1. 分析需求 → 生成执行计划（单步/多步）
2. 依次执行每个步骤
   - SQL步骤：执行查询，保存DataFrame
   - Python步骤：处理DataFrame，生成新结果
3. 最终步骤结果 → 生成图表
4. 返回数据 + 图表PNG(base64)
```

## 使用示例

### JavaScript/TypeScript

```typescript
const eventSource = new EventSource('/v2/sql/analyze', {
    method: 'POST',
    body: JSON.stringify({
        question: '统计各科室CT检查数量'
    })
});

eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data);

    switch (data.type) {
        case 'step_start':
            console.log(`开始执行: ${data.data.description}`);
            break;
        case 'step_complete':
            console.log(`执行完成: ${data.data.row_count} 行`);
            break;
        case 'final':
            // 显示图表
            const img = document.createElement('img');
            img.src = `data:image/png;base64,${data.data.chart_png_base64}`;
            document.body.appendChild(img);
            break;
    }
};
```

### Python

```python
import requests
import json

response = requests.post(
    'http://localhost:6082/v2/sql/analyze',
    json={'question': '统计各科室CT检查数量'},
    stream=True
)

for line in response.iter_lines():
    if line.startswith(b'data: '):
        event = json.loads(line[6:])
        print(f"[{event['type']}] {event['data']}")
```

## 安全注意事项

1. SQL执行使用只读权限（SELECT ONLY）
2. Python代码在沙箱中执行，禁止：
   - 文件操作（open, remove等）
   - 网络访问
   - 系统调用（os.system等）
   - 危险内置函数（eval, exec等）
3. 执行超时限制（默认30秒）
4. 只允许导入白名单模块

## 与传统get_LLM_SQL的区别

| 特性 | 旧版get_LLM_SQL | 新版SQL Agent |
|------|----------------|---------------|
| 架构 | 单一函数 | Agent架构 |
| 复杂查询 | 单条SQL | 支持多步骤分解 |
| Python处理 | 不支持 | 支持 |
| 流式输出 | 不支持 | 支持SSE |
| 图表生成 | JSON配置 | PNG(base64) |
| 安全性 | 一般 | 沙箱执行 |
| 错误处理 | 简单重试 | 步骤级错误处理 |

## 迁移指南

从旧版迁移：

```python
# 旧版
sql, fig_config, df = get_LLM_SQL("统计CT检查数量")

# 新版（异步流式）
async for event in agent.analyze("统计CT检查数量"):
    if event['type'] == 'final':
        sql = event['data']['sql']
        df = pd.DataFrame(event['data']['data'])
        chart_png = event['data']['chart_png_base64']
```
