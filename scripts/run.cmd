set "PROJECT_ROOT=%~dp0.."

cd "%PROJECT_ROOT%"
"
@REM 在Project根目录下激活虚拟环境
call backend\venv\Scripts\activate

uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

echo "项目已启动，访问 http://localhost:8000 查看监控界面"
echo "按下任意键关闭项目..."
pause