# app/services/websocket.py
import asyncio
import logging
from typing import Any, Optional
from fastapi import WebSocket
from datetime import datetime, timezone
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK  # 添加导入
from ..models.data_point import DataFrame

logger = logging.getLogger(__name__)


class WebSocketManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        self.active_connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()  # 添加锁，防止并发修改
        
    async def connect(self, websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        
        async with self._lock:  # 线程安全地添加连接
            if device_id not in self.active_connections:
                self.active_connections[device_id] = set()
            
            self.active_connections[device_id].add(websocket)
            connection_count = len(self.active_connections[device_id])
        
        logger.info(f"设备 {device_id} 的WebSocket连接已建立, 当前连接数: {connection_count}")
        
        await self.send_device_update(device_id)
    
    async def disconnect(self, websocket: WebSocket, device_id: str) -> None:
        connection_count = 0
        async with self._lock:  # 线程安全地移除连接
            if device_id in self.active_connections:
                self.active_connections[device_id].discard(websocket)
                
                if not self.active_connections[device_id]:
                    del self.active_connections[device_id]
                
                connection_count = len(self.active_connections.get(device_id, set()))
        
        logger.info(f"设备 {device_id} 的WebSocket连接已断开, 剩余连接数: {connection_count}")
    
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
            
            message: dict[str, Any] = {
                "type": "realtime_update",
                "device_id": device_id,
                "data": formatted_data,
                "timestamp": timestamp
            }
            
            await self._broadcast_to_device(device_id, message)
                
        except Exception as e:
            logger.error(f"发送设备 {device_id} 更新失败: {e}")
    
    async def _broadcast_to_device(self, device_id: str, message: dict[str, Any]) -> None:
        if device_id not in self.active_connections:
            return
        
        # 创建连接副本，避免在迭代过程中修改集合
        connections_copy = list(self.active_connections.get(device_id, set()))
        
        # 使用 gather 并行发送，设置超时避免阻塞
        send_tasks: list[asyncio.Task[bool]] = []
        for connection in connections_copy:
            send_tasks.append(asyncio.create_task(self._safe_send(connection, message, device_id)))
        
        if send_tasks:
            # 并行发送，忽略异常，设置总体超时
            results = await asyncio.gather(*send_tasks, return_exceptions=True)
            
            # 清理失败的连接
            await self._cleanup_failed_connections(results, connections_copy, device_id)
    
    async def _safe_send(self, connection: WebSocket, message: dict[str, Any], device_id: str) -> bool:
        """安全发送消息，返回是否成功"""
        try:
            # 设置发送超时为3秒，避免长时间阻塞
            await asyncio.wait_for(connection.send_json(message), timeout=3.0)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"向设备 {device_id} 发送消息超时")
            return False
        except (ConnectionClosedError, ConnectionClosedOK):
            logger.info(f"设备 {device_id} 的连接已关闭，准备清理")
            return False
        except Exception as e:
            logger.error(f"向设备 {device_id} 发送数据失败: {type(e).__name__}: {e}")
            return False
    
    async def _cleanup_failed_connections(self, results: list[Any], connections: list[WebSocket], device_id: str) -> None:
        """清理失败的连接"""
        for connection, result in zip(connections, results):
            if isinstance(result, Exception) or result is False:
                await self.disconnect(connection, device_id)
    
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
                await self._safe_send_single(websocket, response, device_id)
                return
            
            from ..services import device_manager
            
            command_translated = device_manager.build_command(device_id, command, parameters)
            results: Optional[list[dict[str, Any]]] = await device_manager.execute_device_command(
                device_id=device_id,
                commands=[command_translated]
            )
            
            if results is None:
                results = [{"message": "执行失败"}]
            
            response = {
                "type": "command_response",
                "device_id": device_id,
                "request_id": request_id,
                "data": results
            }
            
            await self._safe_send_single(websocket, response, device_id)
            
        except Exception as e:
            error_response: dict[str, Any] = {
                "type": "error",
                "message": f"处理命令失败: {str(e)}",
                "request_id": command_data.get("request_id")
            }
            await self._safe_send_single(websocket, error_response, device_id)
    
    async def _safe_send_single(self, websocket: WebSocket, message: dict[str, Any], device_id: str) -> None:
        """安全地向单个WebSocket发送消息"""
        try:
            await asyncio.wait_for(websocket.send_json(message), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning(f"向设备 {device_id} 的WebSocket发送消息超时")
        except (ConnectionClosedError, ConnectionClosedOK):
            logger.info(f"设备 {device_id} 的WebSocket连接已关闭")
            await self.disconnect(websocket, device_id)
        except Exception as e:
            logger.error(f"向设备 {device_id} 发送消息失败: {e}")
    
    def get_connection_count(self, device_id: Optional[str] = None) -> int:
        if device_id:
            return len(self.active_connections.get(device_id, set()))
        else:
            return sum(len(connections) for connections in self.active_connections.values())
    
    def get_connected_devices(self) -> list[str]:
        return list(self.active_connections.keys())
    
    def has_active_connection(self, device_id: str) -> bool:
        return device_id in self.active_connections and len(self.active_connections[device_id]) > 0