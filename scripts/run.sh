#!/bin/bash

# 获取项目根目录
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 进入后端目录
cd "$PROJECT_ROOT/backend"

# 激活虚拟环境
source venv/bin/activate

# 启动 FastAPI 应用
uvicorn app.main:app --host 0.0.0.0 --port 8000

echo "项目已启动，请访问 http://localhost:8000 查看后端接口"
echo "按下 Ctrl+C 关闭项目..."
