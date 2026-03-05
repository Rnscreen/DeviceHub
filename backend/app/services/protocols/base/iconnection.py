from abc import ABC, abstractmethod
from typing import Any

from ....models.device_config import ConnectionConfig

class IConnection(ABC):
    """连接抽象基类，处理物理层通信"""
    
    def __init__(self, config: ConnectionConfig):
        self.timeout = config.timeout
        self._connected = False

    @abstractmethod
    async def connect(self) -> bool:
        """建立连接
        Returns:
            bool: 是否成功连接
        Notes:
            - 连接成功后, 应设置self._connected为True
            - 需要使用self.timeout作为超时时间
        """
        pass
    
    @abstractmethod
    async def disconnect(self) -> None:
        """断开连接
        Notes:
            - 断开后, 应设置self._connected为False
        """
        pass
    
    @abstractmethod
    async def send(self, data: bytes) -> None:
        """发送原始数据"""
        pass

    @abstractmethod
    async def clear(self) -> None:
        """清除缓存"""
        pass
    
    @abstractmethod
    async def receive(self) -> Any:
        """接收数据直到超时
        Notes:
            - 需要使用self.timeout作为超时时间
        """
        pass

    async def send_command(self, data: Any) -> Any:
        """发送并接收响应（默认实现）"""
        await self.send(data)
        return await self.receive()
    
    @property
    def connected(self) -> bool:
        """是否已连接"""
        return self._connected
