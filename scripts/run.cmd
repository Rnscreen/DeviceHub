set "PROJECT_ROOT=%~dp0.."

cd "%PROJECT_ROOT%\backend"

call venv\Scripts\activate

uvicorn app.main:app --host 0.0.0.0 --port 8000

echo "项目已启动，访问 http://localhost:8000 查看监控界面"
echo "按下任意键关闭项目..."
pause