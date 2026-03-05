#!/bin/bash

# 获取项目根目录
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# 进入后端目录
cd "$PROJECT_ROOT/backend"

# Python 版本检查 >=3.10
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]); then
    echo "Python 版本过低，需要 >=3.10"
    exit 1
fi

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 提示用户完成安装
echo "安装完成！按下 Enter 键启动项目..."
read

# 运行 scripts/run.sh 启动项目
bash "$PROJECT_ROOT/scripts/run.sh"
