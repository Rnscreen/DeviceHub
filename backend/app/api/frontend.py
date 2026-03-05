from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

base_dir = Path(__file__).resolve().parent.parent.parent.parent
frontend_dir = base_dir / "frontend"
static_dir = frontend_dir / "static"
js_dir = frontend_dir / "js"
css_dir = frontend_dir / "css"

logger.info(f"前端目录: {frontend_dir}")
logger.info(f"静态文件目录: {static_dir}")
logger.info(f"JS 目录: {js_dir}")

# 挂载目录
# router.mount("/js", StaticFiles(directory=js_dir), name="js")
# router.mount("/static", StaticFiles(directory=static_dir), name="static")
# router.mount("/css", StaticFiles(directory=css_dir), name="css")

# 首页路由
@router.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = static_dir / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=404, detail="首页文件不存在")
    return FileResponse(index_path)

# 其他页面路由
@router.get("/dashboard")
async def dashboard():
    return FileResponse(static_dir / "dashboard.html")

@router.get("/monitor/{page}")
async def monitor_pages(page: str):
    return FileResponse(static_dir / f"{page}.html")

@router.get("/{page_name}", response_class=HTMLResponse)
async def serve_page(page_name: str):
    """动态页面路由"""
    page_extensions = ['.html', '']
    
    for ext in page_extensions:
        page_path = static_dir / f"{page_name}{ext}"
        if page_path.exists():
            return FileResponse(page_path)
    
    # 如果找不到对应的 HTML 文件，返回 404
    index_path = static_dir / "index.html"
    if index_path.exists():
        # 对于 SPA 应用，返回首页让前端路由处理
        return FileResponse(index_path)
    else:
        raise HTTPException(status_code=404, detail="页面不存在")

