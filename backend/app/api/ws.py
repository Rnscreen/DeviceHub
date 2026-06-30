# app/api/v1/ws.py
import json
import logging
from typing import Any
from fastapi import WebSocket, WebSocketDisconnect, APIRouter
from ..services import ws_service
router = APIRouter()
logger = logging.getLogger(__name__)

@router.websocket("/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str) -> None:
    """WebSocket端点"""
    await ws_service.connect(websocket, device_id)
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            
            try:
                message:dict[str, Any] = json.loads(data)
                
                # 检查是否为控制命令（新格式）
                if "command" in message:
                    # 处理控制命令
                    await ws_service.handle_control_command(
                        websocket, device_id, message
                    )
                # 兼容旧格式
                elif message.get("type") == "control":
                    await ws_service.handle_control_command(
                        websocket, device_id, message.get("data", {})
                    )
                elif message.get("type") == "ping":
                    # 心跳响应
                    await websocket.send_json({"type": "pong"})
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "未知的消息格式"
                    })
                    
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "无效的JSON格式"
                })
            except Exception as e:
                logger.error(f"处理WebSocket消息失败: {e}")
                await websocket.send_json({
                    "type": "error",
                    "message": f"处理消息失败: {str(e)}"
                })
                
    except WebSocketDisconnect:
        logger.info(f"设备 {device_id} 的WebSocket连接已断开")
    finally:
        await ws_service.disconnect(websocket, device_id)
