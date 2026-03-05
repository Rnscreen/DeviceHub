# app/services/websocket.py
# import json    # type: ignore
import logging
from typing import Any, Optional
from fastapi import WebSocket
from datetime import datetime,timezone
from ..models.data_point import DataFrame

logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        
        if device_id not in self.active_connections:
            self.active_connections[device_id] = set()
        
        self.active_connections[device_id].add(websocket)
        logger.info(f"设备 {device_id} 的WebSocket连接已建立, 当前连接数: {len(self.active_connections[device_id])}")
        
        await self.send_device_update(device_id)
    
    def disconnect(self, websocket: WebSocket, device_id: str) -> None:
        if device_id in self.active_connections:
            self.active_connections[device_id].discard(websocket)
            
            if not self.active_connections[device_id]:
                del self.active_connections[device_id]
            
            logger.info(f"设备 {device_id} 的WebSocket连接已断开, 剩余连接数: {len(self.active_connections.get(device_id, []))}")
    
    async def send_device_update(self, device_id: str, data: Optional[DataFrame] = None) -> None:
        if device_id not in self.active_connections:
            return
        
        formatted_data: Optional[dict[str, Any]] = None

        try:
            if data is not None:
                formatted_data = data.to_dict()
                timestamp = data.timestamp
            else:
                timestamp = datetime.now(timezone.utc).isoformat()
                pass
            
            message: dict[str, Any] = {
                "type": "realtime_update",
                "device_id": device_id,
                "data": formatted_data,
                "timestamp": timestamp
            }
            
            await self._broadcast_to_device(device_id, message)
                
        except Exception as e:
            logger.error(f"发送设备 {device_id} 更新失败: {e}")
    
    # async def broadcast_to_device(self, device_id: str, data: dict[str, Any]) -> None:
    #     if device_id not in self.active_connections:
    #         return
        
    #     try:
    #         message: dict[str, Any] = {
    #             "type": "update_data",
    #             "device_id": device_id,
    #             "data": data}
            
    #         await self._broadcast_to_device(device_id, message)
    #         logger.debug(f"向设备 {device_id} 广播数据，连接数: {len(self.active_connections[device_id])}")
                
    #     except Exception as e:
    #         logger.error(f"向设备 {device_id} 广播数据失败: {e}")
    
    async def _broadcast_to_device(self, device_id: str, message: dict[str, Any]) -> None:

        if device_id not in self.active_connections:
            return
        
        dead_connections: list[WebSocket] = []
        for connection in self.active_connections[device_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"发送数据到WebSocket失败: {e}")
                dead_connections.append(connection)
        
        for dead_conn in dead_connections:
            self.disconnect(dead_conn, device_id)
    
    # async def broadcast_all(self, data: Optional[dict[str, DataFrame]] = None) -> None:
    #     tasks: list[asyncio.Task[None]] = []
        
    #     if data is not None:
    #         for device_id, device_data in data.items():
    #             if device_id in self.active_connections:
    #                 tasks.append(asyncio.create_task(self.broadcast_to_device(device_id, device_data.to_dict())))
    #     else:
    #         for device_id in list(self.active_connections.keys()):
    #             tasks.append(asyncio.create_task(self.send_device_update(device_id)))
        
    #     if tasks:
    #         await asyncio.gather(*tasks, return_exceptions=True)
    #         logger.debug(f"广播完成，涉及设备数: {len(tasks)}")

    # async def broadcast_data_type(
    #     self, 
    #     device_id: str, 
    #     data_type: DataType, 
    #     data: dict[str, Any]
    # ) -> None:
    #     pass

    async def handle_control_command(
        self, 
        websocket: WebSocket, 
        device_id: str, 
        command_data: dict[str, Any]
    ) -> None:
        try:
            command: Optional[str] = command_data.get("command")
            parameters: dict[str, Any] = command_data.get("parameters", {})
            request_id: Optional[str] = command_data.get("request_id")
            
            if not command:
                response: dict[str, Any] = {"type": "error", "message": "命令不能为空"}
                await websocket.send_json(response)
                return
            
            from ..services import device_manager
            
            command_translated = device_manager.build_command(device_id,
                                                               command, parameters)
            results: dict[str, Any] = await device_manager.execute_device_command(
                device_id=device_id,
                commands=[command_translated]
            )
            
            response = {
                "type": "command_response",
                "device_id": device_id,
                "request_id": request_id,
                "data": results
            }
            
            await websocket.send_json(response)
            
        except Exception as e:
            error_response: dict[str, Any] = {
                "type": "error",
                "message": f"处理命令失败: {str(e)}",
                "request_id": command_data.get("request_id")
            }
            await websocket.send_json(error_response)
    
    def get_connection_count(self, device_id: Optional[str] = None) -> int:
        if device_id:
            return len(self.active_connections.get(device_id, []))
        else:
            return sum(len(connections) for connections in self.active_connections.values())
    
    def get_connected_devices(self) -> list[str]:
        return list(self.active_connections.keys())
    
    def has_active_connection(self, device_id: str) -> bool:
        return device_id in self.active_connections and len(self.active_connections[device_id]) > 0
