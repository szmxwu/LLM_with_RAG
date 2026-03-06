#!/bin/bash
# LLM_with_RAG_v2 启动脚本
# 用于离线环境启动服务

# 设置Python路径
export PYTHONPATH="${PYTHONPATH}:$(pwd)"

# 检查 .env 文件是否存在
if [ ! -f ".env" ]; then
    echo "警告: .env 文件不存在，将使用默认配置"
    echo "请复制 .env.example 到 .env 并修改配置"
fi

# 默认配置
HOST=${HOST:-"0.0.0.0"}
PORT=${PORT:-"6082"}
WORKERS=${WORKERS:-"4"}

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --host)
            HOST="$2"
            shift 2
            ;;
        --port)
            PORT="$2"
            shift 2
            ;;
        --reload)
            RELOAD="--reload"
            WORKERS=1
            shift
            ;;
        --workers)
            WORKERS="$2"
            shift 2
            ;;
        --help)
            echo "用法: ./start.sh [选项]"
            echo ""
            echo "选项:"
            echo "  --host HOST       监听地址 (默认: 0.0.0.0)"
            echo "  --port PORT       监听端口 (默认: 6082)"
            echo "  --reload          开发模式热重载"
            echo "  --workers N       工作进程数 (默认: 4)"
            echo "  --help            显示此帮助信息"
            exit 0
            ;;
        *)
            echo "未知选项: $1"
            exit 1
            ;;
    esac
done

echo "========================================"
echo "  LLM_with_RAG_v2 服务启动"
echo "========================================"
echo "  监听地址: ${HOST}"
echo "  监听端口: ${PORT}"
echo "  工作进程: ${WORKERS}"
if [ -n "${RELOAD}" ]; then
    echo "  开发模式: 是"
else
    echo "  开发模式: 否"
fi
echo "========================================"
echo ""
echo "Swagger UI: http://${HOST}:${PORT}/docs"
echo "默认密码: hK9#mP2$vL5&sN8*tB1!"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 启动服务
if [ -n "${RELOAD}" ]; then
    python -m uvicorn main:app \
        --host ${HOST} \
        --port ${PORT} \
        --reload \
        --log-level info
else
    python -m uvicorn main:app \
        --host ${HOST} \
        --port ${PORT} \
        --workers ${WORKERS} \
        --log-level info
fi
