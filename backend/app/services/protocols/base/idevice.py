from datetime import timezone

from ....models.protocol_config import BatchCommands
from ....models import ControlCommand
"""
动态基类协议
"""
from abc import abstractmethod  #type: ignore
from datetime import datetime
from logging import Logger
from typing import TYPE_CHECKING, Any, Optional, Sequence, Union

from ....models import (
    DataCategory,
    DataFrame,
    DataType,
    DataCache,
    DataTypeLayer,
    DeviceConfig,
    PollDataType,
    ProtocolConfig,
    EnabledChannels,
)

if TYPE_CHECKING:
    from .ibuilder import ICommandBuilder
    from .iconnection import IConnection
    from .ihandler import IHandler
    from .iparser import IResponseParser

class PollTime:
    """last poll time缓存"""
    monitor_fast: str
    monitor_slow: str
    status: str
    info: str

    def __init__(self) -> None:
        """初始化last poll time"""
        now = datetime.now(timezone.utc).isoformat()
        self.monitor_fast = now
        self.monitor_slow = now
        self.status = now
        self.info = now

class IDeviceProtocol:
    def __init__(self, config: DeviceConfig, protocol: ProtocolConfig) -> None:
        self.device_config = config
        self.protocol_config = protocol
        self.enabled = config.enabled

        self.logger = Logger(self.device_config.id)    # 生成日志

        # 初始化通道信息
        # 初始化缓存数据
        self._data_cache = DataCache(protocol, config)
        # 初始化启用通道信息
        # from ....utils.enabled_channel import init_enabled_channels
        # self.device_config.enabled_channels = init_enabled_channels(self.protocol_config,self.device_config)
        # 协议支持的所有通道
        self._channels = protocol.channels 
        # 启用通道信息
        self._enabled_channels = self.device_config.enabled_channels
        
        # 初始化轮询参数
        self._poll_counter:list[int] = [-1,-1]
        self._poll_config = config.poll
        self._last_poll_time = PollTime()
        self._is_ready:bool = True    #是否需要poll info信息

        # 初始化协议枚举键值
        self._enum = protocol.enums
        
        # 初始化连接、构建器、解析器和处理器(由子类实现)
        self._connection: Optional[IConnection] = None
        self._builder: Optional[ICommandBuilder] = None
        self._parser: Optional[IResponseParser] = None
        self._handler: Optional[IHandler] = None
    
    def _init_components(self, connection: IConnection, 
                        builder: ICommandBuilder, 
                        parser: IResponseParser,
                        handler: IHandler):
        """初始化组件(由子类调用)"""
        self._connection = connection   # 连接类型，绑定到设备
        self._builder = builder # builder类型可复用
        self._parser = parser   # parser类型可复用
        self._handler = handler # handler类型，绑定到设备
        self._data_cache = self._data_cache
    
    @property
    def data_cache(self) -> DataCache:
        """获取数据缓存"""
        return self._data_cache
    
    @property
    def enabled_channels(self) -> EnabledChannels:
        """获取通道信息"""
        return self._enabled_channels # type: ignore

    # ------------ 基于计数的轮询逻辑 ------------
    async def get_poll(self) -> DataFrame:
        """基于计数器的轮询入口"""
        try:
            now = datetime.now(timezone.utc).isoformat()
            self._data_cache.timestamp = now

            polldata = DataFrame(id=self.device_config.id, timestamp=now)

            # 1. 轮询info
            if self._is_ready and self.protocol_config.data.get(PollDataType.INFO,False):
                polldata.info = await self.update_by_datatype(PollDataType.INFO)
                self._last_poll_time.info = now
                self._is_ready = False

            # 2. 轮询status
            if self._should_poll_status():
                polldata.status = await self.update_by_datatype(PollDataType.STATUS)
                self._last_poll_time.status = now
                

            # 3. 轮询monitor_slow
            if self._should_poll_slow():
                polldata.monitor = await self.update_by_datatype(PollDataType.MONITOR_SLOW)
                self._last_poll_time.monitor_slow = now

            # 4. 轮询monitor_fast
            if self.protocol_config.data[PollDataType.MONITOR_FAST]:
                if polldata.monitor is None:
                    polldata.monitor = DataTypeLayer(data_type=DataType.MONITOR)
                polldata.monitor.update(await self.update_by_datatype(PollDataType.MONITOR_FAST))
                self._last_poll_time.monitor_fast = now

            return polldata
        except Exception:
            self.logger.error('轮询失败, 返回缓存数据', exc_info = True)
            return self._data_cache

    async def execute(self, commands: BatchCommands) -> Sequence[Union[DataFrame, Sequence[bool]]]:
        """批量执行命令"""
        if self._handler is None:
            raise RuntimeError("Handler not initialized")

        # 初始化返回DataFrame
        exec_data = await self._handler.execute_batch(commands)
                
        return exec_data

    def _should_poll_slow(self) -> bool:
        """基于计数的轮询判断"""
        self._poll_counter[0] = (self._poll_counter[0] + 1) % self._poll_config.poll_slow
        return self._poll_counter[0] == 0 and bool(self.protocol_config.data.get(PollDataType.MONITOR_SLOW,False))

    def _should_poll_status(self) -> bool:
        """基于计数的轮询判断"""
        self._poll_counter[1] = (self._poll_counter[1] + 1) % self._poll_config.poll_status
        return self._poll_counter[1] == 0 and bool(self.protocol_config.data.get(PollDataType.STATUS,False))

    async def update_by_datatype(self, poll_data_type: PollDataType) -> DataTypeLayer:
        """更新指定数据类型的所有数据项

        Args:
            data_type: 数据类型 (monitor_fast/monitor_slow/status/info/stream)
        """
        if self._handler is None:
            raise RuntimeError("Handler not initialized")
        return await self._handler.update_by_datatype(poll_data_type)

    async def update_by_dataname(self, data_name: str) -> DataCategory:
        """更新指定的数据项(根据data_name在data中查找)

        Args:
            data_name: 数据项名称，如 'temperature', 'power' 等
        """
        if self._handler is None:
            raise RuntimeError("Handler not initialized")

        return await self._handler.update_by_dataname(data_name)

    async def execute_control(
        self, control_name: str, channel: str, value: str
    ) -> bool:
        """执行控制命令

        Args:
            control_name: 控制项名称
            channel: 通道名称
            value: 要设置的值

        Returns:
            是否执行成功
        """
        if self._handler is None:
            raise RuntimeError("Handler not initialized")
        # 转换为ControlCommand
        control_cmd = ControlCommand(control_name, channel, value)

        return (await self._handler.execute_control([control_cmd]))[0]

    # ------------连接初始化------------
    async def connect(self) -> bool:
        """连接方法"""
        return await self._connection.connect() # type: ignore

    async def disconnect(self) -> None:
        """断开方法"""
        await self._connection.disconnect() # type: ignore

    @property
    def connected(self) -> bool:
        """是否已连接"""
        return self._connection.connected # type: ignore
    # --------- 安全方法 ----------
    async def __exit__(self, *exc:Any):
        await self.disconnect()

    # 
    def __del__(self):
        pass
       
