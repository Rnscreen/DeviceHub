@REM 获取项目根目录
set "PROJECT_ROOT=%~dp0.."

@REM 进入后端目录
cd "%PROJECT_ROOT%\backend"

@REM python 版本检查 >=3.10
python --version
if %ERRORLEVEL% NEQ 0 (
    echo "Python 版本过低，需要 >=3.10"
    exit /b 1
)

@REM 创建虚拟环境
python -m venv venv

@REM 激活虚拟环境
call venv\Scripts\activate

@REM 安装依赖
pip install -r requirements.txt

@REM 将配置模板复制并去除 .example 后缀
cd "%PROJECT_ROOT%\config"
@REM copy protocols\protocol_v1.0.yaml.example protocols\protocol_v1.0.yaml
@REM 因为已经有mock协议，所以这里不复制原有的protocol_v1.0.yaml文件
copy PUMP_mock_v1.0.yaml.example PUMP_mock_v1.0.yaml
copy TC_mock_v1.0.yaml.example TC_mock_v1.0.yaml
copy devices.yaml.example devices.yaml
copy system.yaml.example system.yaml

@REM 提示用户完成安装
echo "按下任意键启动项目..."
pause

@REM 运行scripts/run.cmd 启动项目
call "%PROJECT_ROOT%\scripts\run.cmd"