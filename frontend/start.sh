#!/bin/bash
# 启动前端 HTTP 服务器

PORT=${CTF_PORT_FRONTEND:-8000}

# 检查是否在正确的目录
if [ ! -f "index.html" ]; then
    echo "❌ 错误：index.html 不存在"
    echo "   请确保在 frontend 目录下运行此脚本"
    exit 1
fi

# 使用改进的服务器脚本（如果存在），否则使用标准 http.server
if [ -f "http_server.py" ]; then
    echo "使用改进的 HTTP 服务器..."
    python3 http_server.py $PORT
else
    echo "使用标准 HTTP 服务器..."
    python3 -m http.server $PORT --bind 0.0.0.0
fi
