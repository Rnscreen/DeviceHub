# app/api/v1/devices.py
from fastapi import APIRouter, HTTPException, Query
from typing import Any, Dict, Optional
from pydantic import BaseModel

from ..models.device_config import DeviceConfig
from ..services import device_manager
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

class DeviceFunctionRequest(BaseModel):
    """设备功能调用请求模型"""
    parameters: Optional[Dict[str, Any]] = {}
    timeout: Optional[int] = 5  # 超时时间（秒）

class DeviceFunctionResponse(BaseModel):
    """设备功能调用响应模型"""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    execution_time: float

@router.get("/devices", response_model=Dict)
async def get_all_device_configs():
    """获取所有设备"""
    return device_manager.get_all_device_configs()


@router.get("/devices/{device_id}/state", response_model=Dict)
async def get_device_state(device_id: str):
    """获取设备状态"""
    state = device_manager.get_device_status(device_id)
    if not state:
        raise HTTPException(status_code=404, detail="设备未找到")
    
    return state


@router.post("/devices")
async def add_device(config: dict[str, Any]):
    """添加设备"""
    cfg = DeviceConfig(**config)
    device_manager.add_device(cfg)
    return {"message": "设备添加成功", "device_id": cfg.id}

@router.get("/devices/common/{function_name}/", response_model=DeviceFunctionResponse)
async def execute_common_function(
    function_name: str,
    params: Optional[str] = Query(None, alias="params")
):
    """
    GET方式执行设备功能（简单参数）
    
    Args:
        device_id: 设备ID
        function_name: 功能名称
        params: 参数字符串，格式为 "key1=value1&key2=value2"
    """
    import time
    import urllib.parse
    
    start_time = time.time()
    
    try:
        # 解析参数字符串
        parameters: dict[str, Any] = {}
        if params:
            # 解析查询字符串
            parsed_params = urllib.parse.parse_qs(params)
            for key, value in parsed_params.items():
                if len(value) == 1:
                    parameters[key] = value[0]
                else:
                    parameters[key] = value
        
        # 创建请求对象
        request = DeviceFunctionRequest(parameters=parameters)
        
        # 获取要执行的方法
        if not hasattr(device_manager, function_name):
            return DeviceFunctionResponse(
                success=False,
                error=f"系统不支持功能: {function_name}",
                execution_time=time.time() - start_time
            )
        
        method = getattr(device_manager, function_name)
        if not callable(method):
            return DeviceFunctionResponse(
                success=False,
                error=f"{function_name} 不是可调用的方法",
                execution_time=time.time() - start_time
            )
        
        # 准备参数
        args: dict[str, Any] = {}
        if request and request.parameters:
            args = request.parameters
        
        logger.info(f"执行设备功能: common.{function_name}({args})")
        
        # 执行方法
        if args:
            result = method(**args)
        else:
            result = method()
        
        execution_time = time.time() - start_time
        
        return DeviceFunctionResponse(
            success=True,
            data=result,
            execution_time=execution_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"执行设备功能失败: {str(e)}")
        execution_time = time.time() - start_time
        return DeviceFunctionResponse(
            success=False,
            error=str(e),
            execution_time=execution_time
        )
 
@router.delete("/devices/{device_id}")
async def remove_device(device_id: str):
    """移除设备"""
    device_manager.remove_device(device_id)
    return {"message": "设备移除成功"}

@router.get("/devices/{device_id}/functions")
async def get_device_functions(device_id: str):
    """获取设备支持的功能列表，包含参数信息"""
    try:
        result = device_manager.get_device_functions(device_id)
        if not result:
            raise HTTPException(404, detail=f"设备 {device_id} 未找到")
        
        # 正常返回功能数据
        return result

    
    except Exception as e:
        logger.error(f"获取设备功能列表失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取设备功能列表失败: {str(e)}")

# 设备执行-POST版本（推荐）
@router.post("/devices/{device_id}/{function_name}")
async def execute_device_function_post(device_id: str, function_name: str, request: Optional[DeviceFunctionRequest] = None):
    """POST方式执行设备功能"""
    params = request.parameters if request and request.parameters else {}
    return await _execute_device_command(device_id, function_name, params)

# 设备执行-GET版本
@router.get("/devices/{device_id}/{function_name}")
async def execute_device_function_get(
    device_id: str, 
    function_name: str, 
    params: Optional[str] = Query(None)
    ):
    """GET方式执行设备功能"""
    parameters: dict[str, Any] = {}
    if params:
        import urllib.parse
        parsed = urllib.parse.parse_qs(params)
        for key, value in parsed.items():
            parameters[key] = value[0] if len(value) == 1 else value
    
    return await _execute_device_command(device_id, function_name, parameters)

# 设备执行命令
async def _execute_device_command(device_id: str, function_name: str, parameters: dict[str, Any] = {}):
    """统一的设备命令执行逻辑"""
    import time
    start_time = time.time()
    
    try:
        # 设备检查
        device = device_manager.get_device(device_id)
        if not device:
            raise HTTPException(status_code=404, detail=f"设备 {device_id} 未找到")
        
        # 连接检查
        if not device.connected:
            try:
                await device.connect()
            except Exception as e:
                return DeviceFunctionResponse(
                    success=False,
                    error=f"设备连接失败: {str(e)}",
                    execution_time=time.time() - start_time
                )
        
        # 构建命令
        command_translated = device_manager.build_command(device_id, function_name, **parameters)
        
        # 执行命令
        result = await device_manager.execute_device_command(
            device_id=device_id,
            commands=[command_translated]
        )
        
        if result is None:
            return DeviceFunctionResponse(
                success=False,
                error="命令执行失败",
                execution_time=time.time() - start_time
            )
        
        execution_time = time.time() - start_time

        return DeviceFunctionResponse(
            success=True,
            data=result,
            execution_time=execution_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"执行设备功能失败: {str(e)}")
        return DeviceFunctionResponse(
            success=False,
            error=str(e),
            execution_time=time.time() - start_time
        )