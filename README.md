# 医学智能问答系统 v2

基于 LangGraph 构建的医学 AI 系统，提供知识问答、诊断匹配、患者分析和数据查询等能力。

**⚡ 流式响应 | 🔒 离线部署 | 🎛️ 思考强度可控 | 📊 多模态交互**

---

## 项目概述

本系统是一个面向放射科医生的智能助手，通过整合大语言模型（LLM）和检索增强生成（RAG）技术，提供以下核心能力：

- **医学知识问答**：基于医学知识库回答疾病影像学表现、诊断标准、扫描技术等问题
- **诊断匹配分析**：对比放射诊断与病理/临床诊断的一致性
- **患者检查分析**：根据患者病史生成阅片要点和鉴别诊断建议
- **智能数据查询**：自然语言转 SQL，分析医疗数据

### 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI 服务层                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────┐ │
│  │  /v2/ask    │  │/v2/diagnosis│  │/v2/patient  │  │/v2/sql  │ │
│  │  知识问答   │  │  诊断匹配   │  │  患者分析   │  │数据查询 │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └────┬────┘ │
└─────────┼────────────────┼────────────────┼──────────────┼──────┘
          │                │                │              │
          └────────────────┴────────────────┴──────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   LangGraph Agent   │
                    │  ┌───────────────┐  │
                    │  │ Intent Analysis│  │
                    │  │    Planning    │  │
                    │  │   Execution    │  │
                    │  │   Reflection   │  │
                    │  └───────────────┘  │
                    └──────────┬──────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
   ┌──────▼──────┐    ┌────────▼────────┐  ┌──────▼──────┐
   │  RAGFlow    │    │   Xinference    │  │   MSSQL     │
   │  知识库     │    │   LLM服务       │  │  医疗数据库  │
   └─────────────┘    └─────────────────┘  └─────────────┘
```

---

## 核心特性

### 1. 智能思考模式

系统支持三种思考强度模式，适应不同场景需求：

| 模式 | 指令 | 适用场景 | 响应速度 |
|------|------|----------|----------|
| **快速响应** | `/no_think` | 简单问答、闲聊、确认类问题 | ⚡ 最快 |
| **标准推理** | `/think` | 一般医学问题、知识查询 | ⚡ 中等 |
| **深度推理** | `/deep_think` | 复杂病例分析、诊断匹配 | ⚡ 较慢 |

### 2. 四阶段知识问答流程

知识问答接口 (`/v2/ask`) 采用四阶段处理：

1. **流式回答**：实时返回生成的回答内容，包含引用标记
2. **参考文献**：生成带链接的参考文献列表
3. **异步引文**：通过 WebSocket 推送 PDF/PPT 等文档内容
4. **病例检索**：生成英文关键词，链接到相关病例图片

### 3. Agent 类型

| Agent | 功能 | 适用场景 |
|-------|------|----------|
| **KnowledgeAgent** | 医学知识检索问答 | 疾病影像学表现、扫描技术规范、鉴别诊断 |
| **RadiologyAgent** | 放射质控分析 | 诊断一致性检查、患者病史分析、阅片指导 |
| **SQLAnalysisAgent** | 数据智能分析 | 检查量统计、收入分析、效率评估 |

---

## 目录结构

```
LLM_with_RAG_v2/
├── agents/                    # Agent 实现
│   ├── base.py               # Agent 基类（LangGraph 封装）
│   ├── enhanced_knowledge_agent.py  # 增强版知识问答 Agent
│   ├── radiology_agent.py    # 放射质控 Agent
│   └── sql_analysis_agent.py # SQL 分析 Agent
├── api/                       # API 层
│   └── routes.py             # v2 路由定义
├── config/                    # 配置管理
│   ├── settings.py           # Pydantic Settings 配置
│   └── tls_compat.py         # TLS 兼容性配置
├── graph/                     # LangGraph 工作流
│   ├── state.py              # 状态定义
│   ├── nodes.py              # 节点实现
│   └── edges.py              # 边路由逻辑
├── tools/                     # 工具封装
│   ├── base.py               # 工具基类
│   ├── registry.py           # 工具注册中心
│   ├── ragflow_tools.py      # RAGFlow 检索工具
│   └── sql_agent.py          # SQL 生成与执行工具
├── prompt/                    # Prompt 模板
│   └── probe_prompt.txt      # 病例关键词生成 prompt
├── static/                    # 静态资源（Swagger UI）
├── legacy/                    # 兼容模块（独立运行）
├── sql_executor_subprocess.py # SQL 子进程执行器
├── main.py                    # 应用入口
├── start.sh                   # 启动脚本
├── requirements.txt           # 依赖列表
└── .env                       # 环境变量配置
```

---

## 安装部署

### 环境要求

- Python 3.10+
- Xinference LLM 服务（本地或远程）
- RAGFlow 知识库服务
- MSSQL 数据库（可选，用于数据查询功能）

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

**离线安装**：
```bash
# 在联网机器预下载依赖
pip download -r requirements.txt -d ./packages

# 复制到离线环境安装
pip install --no-index --find-links=./packages -r requirements.txt
```

### 2. 配置环境变量

创建 `.env` 文件：

```env
# ===========================================
# LLM 配置（Xinference 服务）
# ===========================================
XINFERENCE=http://192.0.0.193:9997/v1
LLM_NAME=qwen3-30b
LLM_KEY=EMPTY

# ===========================================
# 外部重排序服务配置（独立 Xinference 服务）
# ===========================================
RERANK_URL=http://192.0.0.188:9997/v1
RERANK_MODEL=bge-reranker-v2-m3

# ===========================================
# RAGFlow 配置
# ===========================================
BASE_URL=http://192.0.0.193:6080
API_KEY=ragflow-key
AGENT_ID=your-agent-id

# ===========================================
# 数据库配置（MSSQL）
# ===========================================
ODBC=mssql+pyodbc://RIS:RIS@172.17.250.190:1433/GCRIS2?driver=ODBC+Driver+17+for+SQL+Server&connect_timeout=30&Encrypt=no&TrustServerCertificate=yes

# ===========================================
# 默认数据集配置
# ===========================================
DEFAUT_DATA=放射学
DEFAUT_CASE=病例

# ===========================================
# 服务端配置
# ===========================================
HOST_IP=0.0.0.0:6082
ENDPOINT_IP=http://localhost:3000

# ===========================================
# 安全配置
# ===========================================
DOCS_PASSWORD=hK9#mP2$vL5&sN8*tB1!
```

### 3. 启动服务

```bash
# 开发模式（热重载）
python main.py --reload

# 生产模式
python main.py --host 0.0.0.0 --port 6082 --workers 4

# 或使用启动脚本
./start.sh --host 0.0.0.0 --port 6082
```

### 4. 访问接口文档

启动后访问 Swagger UI：

```
http://localhost:6082/docs
```

默认认证密码：`hK9#mP2$vL5&sN8*tB1!`

---

## API 接口文档

### 接口概览

| 接口 | 方法 | 描述 | 流式 |
|------|------|------|------|
| `/v2/ask` | POST | 知识问答 | ✅ |
| `/v2/diagnosis/match` | POST | 放射-病理诊断匹配 | ❌ |
| `/v2/diagnosis/complex-match` | POST | 复杂诊断匹配（多模态） | ❌ |
| `/v2/patient/analyze` | POST | 患者检查分析 | ✅ |
| `/v2/sql/analyze` | POST | SQL 数据分析 | ✅ |
| `/v2/sql/simple` | POST | 简单 SQL 查询 | ❌ |
| `/v2/list_case` | GET | 病例图片搜索 | ❌ |
| `/v2/thinking-modes` | GET | 获取思考模式说明 | ❌ |
| `/v2/ws/{user_id}` | WebSocket | 异步引文推送 | ✅ |

---

## 前端对接指南

### 1. 认证方式

所有 API 接口（除 `/docs` 外）使用 HTTP Basic 认证：

```javascript
// 用户名随意，密码为配置的 DOCS_PASSWORD
const headers = {
  'Authorization': 'Basic ' + btoa('any:hK9#mP2$vL5&sN8*tB1!'),
  'Content-Type': 'application/json'
};
```

### 2. 知识问答接口（/v2/ask）

**接口描述**：医学知识库检索问答，支持流式输出和四阶段处理。

**请求方式**：`POST`

**请求参数**：

```typescript
interface AskRequest {
  question: string;           // 用户问题（必填）
  dataset?: string;           // 知识库名称，默认"放射学"
  user_id?: string;           // 用户标识，用于会话隔离
  session_id?: string;        // 会话ID，用于保持上下文
  thinking_mode?: 'no_think' | 'think' | 'deep_think';  // 思考模式
}
```

**响应格式**：`text/plain` 流式文本

响应分为多个阶段，每个阶段以 `[STAGE:xxx]` 标记：

```
[STAGE:answer]          // 阶段1开始：流式回答内容
肝癌的影像学表现主要包括以下几个方面：...

[STAGE:answer_complete] // 阶段1结束

[STAGE:references]      // 阶段2：参考文献
### 参考文献
- [1] [肝癌影像学诊断.pdf](http://.../document/xxx)[1, 3, 5]
- [2] [肝脏病变CT表现.pptx](http://.../v1/document/get/yyy)[2]

[STAGE:keywords]        // 阶段4：病例检索关键词
关键词: liver cancer imaging CT MRI
<a href="http://.../v2/list_case?keywords=liver%20cancer%20imaging" target="_blank" style="font-size:18px; color:darkred;">相关病例图片</a>

[STAGE:complete]        // 全部完成
```

**前端实现示例**：

```javascript
async function askQuestion(question) {
  const response = await fetch('http://localhost:6082/v2/ask', {
    method: 'POST',
    headers: {
      'Authorization': 'Basic ' + btoa('any:hK9#mP2$vL5&sN8*tB1!'),
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      question: question,
      thinking_mode: 'think',
      user_id: 'user-001'
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let currentStage = null;
  let answerContent = '';
  let referencesHtml = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = decoder.decode(value, { stream: true });

    // 检测阶段标记
    if (text.includes('[STAGE:answer]')) {
      currentStage = 'answer';
      continue;
    }
    if (text.includes('[STAGE:answer_complete]')) {
      currentStage = null;
      continue;
    }
    if (text.includes('[STAGE:references]')) {
      currentStage = 'references';
      continue;
    }
    if (text.includes('[STAGE:keywords]')) {
      currentStage = 'keywords';
      continue;
    }
    if (text.includes('[STAGE:complete]')) {
      // 处理完成
      break;
    }

    // 处理各阶段内容
    switch (currentStage) {
      case 'answer':
        answerContent += text;
        // 实时显示回答内容
        document.getElementById('answer').innerHTML += text;
        break;
      case 'references':
        referencesHtml += text;
        break;
      case 'keywords':
        // 显示病例链接
        document.getElementById('cases').innerHTML = text;
        break;
    }
  }

  // 显示参考文献
  document.getElementById('references').innerHTML = referencesHtml;
}
```

### 3. WebSocket 连接（异步引文）

**接口描述**：建立 WebSocket 连接，接收异步推送的引文内容（PDF/PPT 解析结果）。

**连接方式**：`WebSocket`

**连接地址**：`ws://localhost:6082/v2/ws/{user_id}`

**消息类型**：

```typescript
// 客户端发送心跳
{ "type": "ping" }

// 客户端订阅会话
{ "type": "subscribe", "session_id": "xxx" }

// 服务端返回心跳响应
{ "type": "pong" }

// 服务端推送引文内容
{
  "type": "reference_content",
  "data": {
    "document_name": "肝癌诊断指南.pdf",
    "document_id": "xxx",
    "content": "...",
    "page": [1, 2, 3]
  }
}
```

**前端实现示例**：

```javascript
const userId = 'user-' + Math.random().toString(36).substr(2, 9);
const ws = new WebSocket(`ws://localhost:6082/v2/ws/${userId}`);

ws.onopen = () => {
  console.log('WebSocket 连接成功');
  // 订阅特定会话
  ws.send(JSON.stringify({
    type: 'subscribe',
    session_id: 'session-xxx'
  }));
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);

  switch (message.type) {
    case 'reference_content':
      // 显示引文内容
      displayReference(message.data);
      break;
    case 'pong':
      // 心跳响应
      break;
  }
};

// 定时发送心跳
setInterval(() => {
  if (ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'ping' }));
  }
}, 30000);
```

### 4. 诊断匹配接口（/v2/diagnosis/match）

**接口描述**：判断放射诊断与病理诊断是否相符。

**请求方式**：`POST`

**请求参数**：

```typescript
interface DiagnosisMatchRequest {
  radiology_result: string;    // 放射诊断结论
  pathology_result: string;    // 病理诊断结论
  session_id?: string;         // 会话ID
  thinking_mode?: 'no_think' | 'think' | 'deep_think';
}
```

**响应格式**：`application/json`

```typescript
interface DiagnosisMatchResponse {
  result: string;              // 符合/基本符合/不符合/无法判断
  confidence: string;          // 高/中/低
  reason: string;              // 判断理由
  key_findings: string[];      // 关键发现
  suggestions: string;         // 建议
}
```

**前端实现示例**：

```javascript
async function matchDiagnosis(radiology, pathology) {
  const response = await fetch('http://localhost:6082/v2/diagnosis/match', {
    method: 'POST',
    headers: {
      'Authorization': 'Basic ' + btoa('any:password'),
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      radiology_result: radiology,
      pathology_result: pathology,
      thinking_mode: 'deep_think'  // 诊断匹配建议使用深度思考
    })
  });

  const result = await response.json();

  // 显示结果
  document.getElementById('match-result').innerHTML = `
    <div class="result-${result.result === '符合' ? 'success' : 'warning'}">
      <h3>匹配结果：${result.result}</h3>
      <p>置信度：${result.confidence}</p>
      <p>判断理由：${result.reason}</p>
      <ul>
        ${result.key_findings.map(f => `<li>${f}</li>`).join('')}
      </ul>
      <p>建议：${result.suggestions}</p>
    </div>
  `;
}
```

### 5. 患者分析接口（/v2/patient/analyze）

**接口描述**：根据患者历史检查生成阅片要点。

**请求方式**：`POST`

**请求参数**：

```typescript
interface PatientAnalysisRequest {
  patient_history: string;     // 患者病史（JSON格式数组）
  modality: string;            // 检查设备类型（CT/MR/US等）
  study_part: string;          // 检查部位
  previous_reports?: string;   // 近期相同部位检查结果
  user_id?: string;
  session_id?: string;
  thinking_mode?: string;
}
```

**响应格式**：`text/plain` 流式 Markdown

**前端实现示例**：

```javascript
async function analyzePatient(history, modality, part) {
  const response = await fetch('http://localhost:6082/v2/patient/analyze', {
    method: 'POST',
    headers: {
      'Authorization': 'Basic ' + btoa('any:password'),
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      patient_history: JSON.stringify(history),
      modality: modality,
      study_part: part,
      thinking_mode: 'think'
    })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = decoder.decode(value, { stream: true });
    // 实时显示 Markdown 内容
    document.getElementById('analysis').innerHTML += text;
  }
}
```

### 6. SQL 数据分析接口（/v2/sql/analyze）

**接口描述**：自然语言转 SQL，执行数据分析并生成图表。

**请求方式**：`POST`

**请求参数**：

```typescript
interface SQLAnalysisRequest {
  question: string;            // 自然语言问题
  session_id?: string;
}
```

**响应格式**：`text/event-stream` (SSE)

事件类型：
- `plan`: 执行计划生成
- `step_start`: 步骤开始
- `step_complete`: 步骤完成
- `analysis`: 分析中
- `final`: 最终结果（包含数据和图表）

```javascript
async function analyzeSQL(question) {
  const response = await fetch('http://localhost:6082/v2/sql/analyze', {
    method: 'POST',
    headers: {
      'Authorization': 'Basic ' + btoa('any:password'),
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ question })
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    const text = decoder.decode(value, { stream: true });

    // SSE 格式解析
    const lines = text.split('\n');
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const event = JSON.parse(line.substring(6));

        switch (event.type) {
          case 'plan':
            displayPlan(event.data);
            break;
          case 'step_start':
            showStepStart(event.data);
            break;
          case 'step_complete':
            showStepComplete(event.data);
            break;
          case 'final':
            // 显示数据和图表
            displayChart(event.data.chart_png_base64);
            displayTable(event.data.data);
            break;
        }
      }
    }
  }
}
```

### 7. 病例图片搜索接口（/v2/list_case）

**接口描述**：根据关键词搜索病例库中的相关病例图片。

**请求方式**：`GET`

**请求参数**：

```typescript
interface ListCaseRequest {
  keywords: string;            // 搜索关键词（英文或中文）
}
```

**响应格式**：`application/json`

```typescript
interface ListCaseResponse {
  keywords: string;            // 实际使用的关键词
  cases: string[];             // HTML 格式的病例内容数组
  count: number;               // 病例数量
}
```

**前端实现示例**：

```javascript
async function searchCases(keywords) {
  const response = await fetch(
    `http://localhost:6082/v2/list_case?keywords=${encodeURIComponent(keywords)}`,
    {
      headers: {
        'Authorization': 'Basic ' + btoa('any:password')
      }
    }
  );

  const result = await response.json();

  // 显示病例
  const container = document.getElementById('cases');
  result.cases.forEach((caseHtml, index) => {
    const caseDiv = document.createElement('div');
    caseDiv.className = 'case-item';
    caseDiv.innerHTML = caseHtml;
    container.appendChild(caseDiv);
  });
}
```

### 8. 思考模式查询接口（/v2/thinking-modes）

**接口描述**：获取支持的思考模式说明。

**请求方式**：`GET`

**响应格式**：`application/json`

```javascript
async function getThinkingModes() {
  const response = await fetch('http://localhost:6082/v2/thinking-modes', {
    headers: {
      'Authorization': 'Basic ' + btoa('any:password')
    }
  });

  const result = await response.json();

  // 显示模式选择器
  const selector = document.getElementById('thinking-mode');
  result.modes.forEach(mode => {
    const option = document.createElement('option');
    option.value = mode.value;
    option.textContent = `${mode.label} - ${mode.description}`;
    selector.appendChild(option);
  });
}
```

---

## 错误处理

### 常见错误码

| HTTP 状态码 | 含义 | 处理建议 |
|-------------|------|----------|
| 401 | 认证失败 | 检查 Authorization 头是否正确 |
| 422 | 请求参数错误 | 检查请求体是否符合接口定义 |
| 500 | 服务器内部错误 | 查看服务器日志，联系管理员 |
| 503 | 外部服务不可用 | 检查 Xinference/RAGFlow 服务状态 |

### 错误响应格式

```json
{
  "detail": "错误描述信息"
}
```

---

## 注意事项

1. **流式响应处理**：知识问答、患者分析、SQL 分析接口返回流式响应，前端需要正确处理流式数据。

2. **WebSocket 重连**：网络中断时需要自动重连 WebSocket，并重新订阅会话。

3. **图片加载优化**：病例图片使用 base64 编码，数据量较大时建议分页加载。

4. **思考模式选择**：
   - 简单问答使用 `no_think` 模式，响应最快
   - 一般医学问题使用 `think` 模式（默认）
   - 诊断匹配等关键决策使用 `deep_think` 模式

5. **会话隔离**：多用户场景下，建议为每个用户分配唯一的 `user_id`，避免会话混淆。

---

## License

MIT License
