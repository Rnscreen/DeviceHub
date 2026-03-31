import asyncio
import logging
from typing import Optional, Union
from ..base.iconnection import IConnection
from ....models.device_config import ConnectionConfig

class TcpConnection(IConnection):
    """TCP连接实现类"""
    
    def __init__(self, config: ConnectionConfig):
        super().__init__(config)
        self.config = config
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected: bool = False
        self._connection_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self.logger = logging.getLogger(f"TcpConnection.{config.host}:{config.port}")
    
    async def connect(self) -> bool:
        """建立TCP连接"""
        async with self._connection_lock:
            if self._connected:
                self.logger.warning("Connection already established")
                return True
            
            try:
                await self.disconnect()
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(
                        host=self.config.host,
                        port=self.config.port
                    ),
                    timeout=self.timeout
                )
                self._connected = True
                self.logger.info(f"Connected to {self.config.host}:{self.config.port}")
                return True
            except asyncio.TimeoutError:
                raise ConnectionError(f"Connection timeout to {self.config.host}:{self.config.port}")
            except Exception as e:
                raise ConnectionError(f"Failed to connect to {self.config.host}:{self.config.port}: {e}")
    
    async def disconnect(self) -> None:
        """断开TCP连接"""
        if self._writer:
            try:
                self._writer.close()
                await asyncio.wait_for(self._writer.wait_closed(), timeout=self.timeout)
            except Exception as e:
                self.logger.warning(f"Error closing connection: {e}")
            finally:
                self._writer = None
                self._reader = None
                self._connected = False
                self.logger.info("Disconnected")
    
    async def clear(self) -> None:
        """清除reader缓存"""
        if self._reader:
            try:
                await asyncio.wait_for(
                    self._reader.read(1024),
                    timeout=self.timeout
                )
            except Exception as e:
                self.logger.warning(f"Error clearing cache: {e}")

    async def send(self, data: bytes) -> None:
        """发送原始数据"""
        if not self._connected or not self._writer:
            raise ConnectionError("Not connected")
        
        try:            
            self._writer.write(data)
            await self._writer.drain()
            self.logger.debug(f"Sent: {data}")
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Failed to send data: {e}")
    
    async def receive(self) -> bytes:
        """接收数据直到超时"""
        if not self._connected or not self._reader:
            raise ConnectionError("Not connected")
        
        try:
            data = await asyncio.wait_for(
                self._reader.read(4096),
                timeout=self.timeout
            )
            if not data:
                self._connected = False
                raise ConnectionError("Connection closed by peer")
            
            self.logger.debug(f"Received: {data}")
            return data
        except asyncio.TimeoutError:
            raise TimeoutError(f"Receive timeout after {self.timeout}s")
        except Exception as e:
            self._connected = False
            raise ConnectionError(f"Failed to receive data: {e}")

    async def read_until(self, terminator: Union[bytes, str] = b"\r\n") -> bytes:
        """读取直到遇到终止符 (用于ASCII协议)"""
        if not self._connected or not self._reader:
            raise ConnectionError("Not connected")
        
        if isinstance(terminator, str):
            terminator = terminator.encode('utf-8')
        
        buffer = bytearray()
        try:
            while True:
                chunk = await asyncio.wait_for(
                    self._reader.read(256),
                    timeout = self.timeout
                )
                if not chunk:
                    self._connected = False
                    raise ConnectionError("Connection closed by peer")
                
                buffer.extend(chunk)
                
                if terminator in buffer:
                    result = bytes(buffer)
                    # self.logger.debug(f"Read until terminator: {result}")
                    return result
                
                if len(buffer) > 8192:
                    raise BufferError("Response buffer overflow")
        except asyncio.TimeoutError:
            raise TimeoutError(f"Read until timeout after {self.timeout}s")
        
    @property
    def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected
