"""新入口文件 - LLM_with_RAG_v2

基于LangGraph的智能Agent系统 - v2版本
完全独立运行，不依赖父目录
"""

import os
import secrets

# 自动配置TLS兼容性（必须在导入任何数据库相关模块之前）
# 解决OpenSSL 3.0与SQL Server 2012的TLS兼容性问题
from config.tls_compat import configure_tls_compatibility
configure_tls_compatibility()

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html, get_swagger_ui_oauth2_redirect_html
from contextlib import asynccontextmanager

from api.routes import router as v2_router
from api.adapter import legacy_adapter
from config.settings import settings

# 安全认证密码：优先从环境变量读取，否则使用默认值
# 生产环境强烈建议通过环境变量设置复杂密码
SECURITY_PASSWORD = os.getenv("SECURITY_PASSWORD", "hK9#mP2$vL5&sN8*tB1!")
security = HTTPBasic(auto_error=False)


def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    """验证访问密码"""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Basic"},
        )
    correct_password = secrets.compare_digest(credentials.password, SECURITY_PASSWORD)
    if not correct_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    print("=" * 60)
    print("LLM_with_RAG_v2 启动中...")
    print(f"LLM模型: {settings.llm_model}")
    print(f"RAGFlow: {settings.ragflow_url}")
    print("=" * 60)
    yield
    # 关闭时
    print("LLM_with_RAG_v2 关闭中...")


# 创建FastAPI应用 - 禁用默认docs，使用自定义
app = FastAPI(
    docs_url=None,  # 禁用默认Swagger UI
    redoc_url=None,  # 禁用默认ReDoc
    title="放射质控大模型服务 v2",
    version="2.0.0",
    lifespan=lifespan,
    dependencies=[Depends(get_current_username)],  # 全局认证
    description="""
<b>智能体接口文档 v2 - 基于LangGraph的自主规划Agent系统</b><br><br>

<b>🔥 新特性：</b><br>
• 自主规划能力 - Agent自动分析任务复杂度并制定执行计划<br>
• 思考强度控制 - 支持/no_think、/think、/deep_think三种模式<br>
• 流式响应 - 所有问答接口支持流式返回<br>
• 多Agent协作 - 知识Agent、放射Agent分工协作<br><br>

<b>📚 接口分类：</b><br>
• <b>知识问答</b>: /v2/ask - 医学知识库检索问答<br>
• <b>诊断质控</b>: /v2/diagnosis/match, /v2/diagnosis/complex-match<br>
• <b>患者分析</b>: /v2/patient/analyze<br>
• <b>思考模式</b>: /v2/thinking-modes - 查看支持的思考模式<br><br>

<b>⚙️ 配置说明：</b><br>
• Xinference: 运行LLM、Embedding、Rerank三个模型<br>
• RAGFlow(BASE_URL): 提供本地知识库服务<br>
• 思考模式: 通过thinking_mode参数控制(no_think/think/deep_think)<br><br>

<b>🔧 调试提示：</b><br>
• 简单问题使用 no_think 模式响应最快<br>
• 诊断匹配默认使用 deep_think 模式保证准确性<br>
• 流式接口返回text/plain格式<br>
"""
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件目录（本地Swagger UI资源）
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# 注册v2路由
app.include_router(v2_router)


# OAuth2重定向URL（FastAPI 0.100+兼容性修复）
OAUTH2_REDIRECT_URL = "/docs/oauth2-redirect"


# 自定义Swagger UI - 使用本地静态文件
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """自定义Swagger UI页面"""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=OAUTH2_REDIRECT_URL,
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
    )


@app.get(OAUTH2_REDIRECT_URL, include_in_schema=False)
async def swagger_ui_redirect():
    """Swagger UI OAuth2重定向"""
    return get_swagger_ui_oauth2_redirect_html()


# 健康检查（不需要认证）
@app.get("/health", include_in_schema=True)
async def health():
    """健康检查

    返回服务状态和版本信息
    """
    return {
        "status": "ok",
        "version": "2.0.0",
        "features": {
            "langgraph": True,
            "streaming": True,
            "multi_agent": True,
            "thinking_mode_control": True
        }
    }


# 兼容v1的健康检查
@app.get("/v1/health", include_in_schema=False)
async def health_v1():
    """v1兼容健康检查"""
    return {"status": "ok"}


# 主函数
if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="LLM_with_RAG_v2 Server")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=6082, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")

    args = parser.parse_args()

    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=1 if args.reload else 4,
        log_level="info"
    )
