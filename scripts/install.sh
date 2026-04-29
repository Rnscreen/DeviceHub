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
echo "安装完成！正在复制配置模板..."

# 将配置模板复制并去除 .example 后缀
cd "$PROJECT_ROOT/config"
# cp protocols\protocol_v1.0.yaml.example protocols\protocol_v1.0.yaml
# 因为已经有mock协议，所以这里不复制原有的protocol_v1.0.yaml文件
cp PUMP_mock_v1.0.yaml.example PUMP_mock_v1.0.yaml
cp TC_mock_v1.0.yaml.example TC_mock_v1.0.yaml
cp devices.yaml.example devices.yaml
cp system.yaml.example system.yaml

echo "配置模板复制完成！按任意键启动项目..."
read

# 运行 scripts/run.sh 启动项目
bash "$PROJECT_ROOT/scripts/run.sh"
