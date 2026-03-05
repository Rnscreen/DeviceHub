# app/api/config.py
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from ..models.system_config import settings

router = APIRouter(prefix="/config", tags=["配置管理"])

@router.get("/devices")
async def get_device_config():
    """获取完整的设备配置"""
    return settings.DEVICE_CONFIG_PATH

@router.get("/devices/{device_id}")
async def get_single_device_config(device_id: str):
    """获取单个设备配置"""
    device = settings.DEVICE_CONFIG.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="设备未找到")
    return device

@router.put("/devices")
async def update_device_config(config: Dict[str, Any]):
    """更新设备配置"""
    save_device_config(config)
    return {"message": "配置已更新", "path": settings.DEVICE_CONFIG_PATH}