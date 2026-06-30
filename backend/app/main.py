# backend/app/main.py
import time
from contextlib import asynccontextmanager
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .models.system_config import settings

from .api import devices, data, ws
from .services import device_manager, polling_service, db_service, ws_service, file_watcher

# 配置日志
(settings.ROOT_PATH / 'logs').mkdir(parents=True, exist_ok=True)    # 确保日志目录存在

logging.basicConfig(
    filename=f"{settings.ROOT_PATH / 'logs' / settings.APP_NAME}_{time.strftime('%Y%m%d%H%M%S')}.log",  # 日志文件路径
    filemode='a',
    level=getattr(logging, settings.LOG_LEVEL.upper()),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 静态文件目录
STATIC_DIR = Path(__file__).parent.parent.parent / "frontend" / "static"

async def device_components_init():
    #初始化设备
    logger.info("初始化设备...")
    await device_manager.initialize_devices()
    # 启动轮询服务
    logger.info("启动轮询服务...")
    if not polling_service.is_running:
        await polling_service.start_polling()
    else:
        logger.info("轮询服务已在运行")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动
    logger.info(f"启动 {settings.APP_NAME}")
    
    try:
        # 连接数据库
        logger.info("连接数据库...")
        await db_service.connect()
        
        # 初始化设备组件
        await device_components_init()
        
        # 启动文件监听服务
        logger.info("启动文件监听服务...")
        file_watcher.start()

        # 启用配置文件热重载
        logger.info("启用配置文件热重载...")
        settings.enable_hot_reload()
        
        # 启用协议配置文件热重载
        logger.info("启用协议配置文件热重载...")
        device_manager.enable_protocol_hot_reload()
        
        # 将服务实例存储到app.state
        app.state.device_manager = device_manager
        app.state.db_service = db_service
        app.state.polling_service = polling_service
        app.state.ws_service = ws_service
        
        logger.info("应用启动完成")
        
    except Exception as e:
        logger.error(f"应用启动失败: {e}")
        raise
    
    yield
    
    # 关闭
    try:
        if hasattr(app.state, "polling_service"):
            await app.state.polling_service.stop()

        if hasattr(app.state, "db_service"):
            await app.state.db_service.close_all()
        
        # 停止文件监听服务
        file_watcher.stop()
        
        logger.info(f"关闭 {settings.APP_NAME}")
        
    except Exception as e:
        logger.error(f"应用关闭时出错: {e}")

# 创建FastAPI应用
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 包含路由
app.include_router(ws.router, prefix='/ws', tags=["websocket"])
app.include_router(devices.router, prefix="/api/v1", tags=["devices"])
app.include_router(data.router, prefix="/api/v1", tags=["data"])
# 未启用的alerts模块
# app.include_router(alerts.router, prefix="/api/v1", tags=["alerts"])

# 挂载静态文件（如果存在）
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    logger.info(f"已挂载静态文件目录: {STATIC_DIR}")
else:
    logger.warning(f"静态文件目录不存在: {STATIC_DIR}")

@app.get("/favicon.ico", include_in_schema=False)
async def favicon() -> RedirectResponse:
    """网站图标"""
    return RedirectResponse("/static/favicon.ico")

@app.get("/", include_in_schema=False)
async def root():
    """根端点"""
    if STATIC_DIR.exists():
        return RedirectResponse("/static/index.html")

    return {
        "app": settings.APP_NAME,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "websocket_endpoint": "/ws/{device_id}"
    }

@app.get("/health")
async def health_check() -> dict[str, str]:
    """健康检查端点"""
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )