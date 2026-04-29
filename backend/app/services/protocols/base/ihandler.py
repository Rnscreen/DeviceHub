# backend/app/services/handler/ihandler.py
from ...protocols.base.idevice import IDeviceProtocol
from ....models.data_point import DataCategory, DataType, DataTypeLayer
from typing import Any, Sequence
from typing import  Optional, Union
import logging
from abc import ABC, abstractmethod

from ....models import (ProtocolConfig, PollDataType, DeviceConfig, DataFrame, 
                        PollCommand, ControlCommand, BatchCommands, PollCommands, ControlCommands) # type: ignore
from .iconnection import IConnection
from .ibuilder import ICommandBuilder
from .iparser import IResponseParser

class IHandler(ABC):
    """协议处理器抽象基类 - 重新设计版本"""
    
    def __init__(self, 
                 device:IDeviceProtocol,
                 connection: IConnection,
                 builder: ICommandBuilder,
                 parser: IResponseParser,
                 protocol_config: ProtocolConfig,
                 device_config: DeviceConfig,
                 enabled_channels: Optional[dict[str, list[str]]] = None):
        
        self.connection = connection
        self.builder = builder
        self.parser = parser
        self.protocol_config = protocol_config
        self.device_config = device_config
        self.enabled_channels = enabled_channels or {}
        self.logger = logging.getLogger(f"IHandler.{device_config.id}")
        
        # 初始化数据缓存和状态
        self.data_cache = device.data_cache

        # 初始化数据项到数据类型的映射
        self.dataname_to_datatype = self.builder.dataname_to_datatype
        self.datatype_to_data_name = self.builder.datatype_to_data_name
        self.dataname_to_channels = self.builder.dataname_to_channels
        self.alarm_values = self.builder.alarm_values

    @abstractmethod
    async def execute_monitor(self, commands: PollCommands) -> DataFrame:
        """执行批量命令
        
        Args:
            commands: 命令序列
            - 每个元素为 (data_name, channel, value)
            - 如果 channel:str|list[str], 则执行单点/批量操作

        Returns:
            执行结果 数据帧
        
        Notes:
            需要根据协议实现具体的解析逻辑
            DataFrame需要传入设备id
        """

    @abstractmethod
    async def execute_control(self, commands: ControlCommands) -> Sequence[bool]:
        """执行批量命令
        
        Args:
            commands: 命令序列
            - 每个元素为 (control_name, channel, value)
            - channel: 通道名称， 必须指定, 无通道则默认为main
            - value: 要设置的值, 若为''则可能为开关操作如command:"STArt"则直接执行, 此时无{value}占位符的替换

        Returns:
            执行结果 布尔列表
        
        Notes:
            需要根据协议实现具体的解析逻辑
            # 1. 构建控制命令
            # 2. 发送命令
            # 3. 解析响应
            # 4. 返回结果列表
            # 5. 构建更新命令(调用builder.build_poll_command)
            # 6. 发送更新命令(调用_execute_monitor)
        """

    @abstractmethod
    async def _send_command(self, command: Any) -> Any:
        """发送命令并接收响应
        Args:
            command: 要发送的命令
        Returns:
            响应字符串
        """
    
    async def _handle_error(self, error: Exception, context: str) -> None:
        """处理错误
        
        Args:
            error: 异常对象
            context: 错误上下文描述
        """
        self.logger.error(f"{context}: {error}")
    
    def execute_query(self, commands: PollCommands) -> DataFrame:
        """从self.data_cache中查询数据
        
        Args:
            commands: 命令序列
            - 每个元素为 (data_name, channel)
            - 如果 channel:str|list[str], 则执行单点/批量查询操作

        Returns:
            执行结果 数据帧
        """
        data_frame = DataFrame(id=self.device_config.id)

        # 无命令则返回全部缓存数据
        if not commands:
            return self.data_cache
        
        # 构建data_frame
        for cmd in commands:
            data_name, channel = cmd.data_name, cmd.channel
            datatype = self.dataname_to_datatype[data_name].dt

            # 获取data_name和channel对应的DataCategory
            data_category = DataCategory(datatype, data_name)

            if channel is None:
                channel = self.enabled_channels.get(self.dataname_to_channels[data_name], 'main')
    
            if isinstance(channel, str):
                channel = [channel]
                
            for ch in channel:
                data_category[ch] = self.data_cache[datatype][data_name][ch]

            data_frame[datatype].add_category(data_name, data_category)

        return data_frame



    async def execute_batch(self, commands: BatchCommands) -> Sequence[Union[DataFrame, Sequence[bool]]]:
        """执行批量命令
        
        Args:
            commands: 命令序列
            - 每个元素为 (data_name, channel, value)
            - 如果 channel为空, 使用enabled通道
            - 如果 value为空, 执行查询操作, 否则执行控制操作

        Returns:
            执行结果
        """
        result:list[Union[DataFrame, Sequence[bool]]] = []

        # 命令分类，将查询和控制命令分开
        query_cache:PollCommands = []
        control_cache:ControlCommands = []
        last_is_control:Optional[bool] = None

        # 交错执行查询和控制命令

        for cmd in commands:
            # 分类查询和控制命令
            if isinstance(cmd, PollCommand):
                query_cache.append(cmd)
                this_is_control = False
            else: 
                # isinstance(cmd, ControlCommand)
                control_cache.append(cmd)
                this_is_control = True

            # 如果类型切换，执行上一个缓存
            if last_is_control is None or last_is_control!=this_is_control:
                if last_is_control:
                    result.append(await self.execute_control(control_cache))
                    control_cache.clear()
                else:
                    result.append(self.execute_query(query_cache))
                    query_cache.clear()
        
        # 处理剩余缓存
        if control_cache:
            result.append(await self.execute_control(control_cache))
        if query_cache:
            result.append(self.execute_query(query_cache))

        return result
    
    async def update_by_datatype(self, data_type: PollDataType) -> DataTypeLayer:
        """根据数据类型更新数据
        
        Args:
            data_type: 数据类型
            
        Returns:
            更新后的DataTypeLayer
        """
        data_names = self.datatype_to_data_name[data_type]
        commands = [
            PollCommand(data_name, self.enabled_channels.get(
                self.dataname_to_channels[data_name], 
                'main'))
            for data_name in data_names
        ]

        result = (await self.execute_monitor(commands))[data_type.dt]

        # 如果是状态数据, 对比与self.data_cache是否有变化, 只有变化才更新
        if data_type.dt == DataType.STATUS:
            new_result = DataTypeLayer(DataType.STATUS)
            old_status = self.data_cache[DataType.STATUS]
            for data_name in self.datatype_to_data_name[PollDataType.STATUS]:
                if result.get_category(data_name) != old_status.get_category(data_name):
                    new_result.add_category(data_name, result.get_category(data_name))

            result = new_result

        else:
            self.data_cache[data_type.dt].update(result)
            
        return result

    async def update_by_dataname(self, data_name: str) -> DataCategory:
        """根据数据名称更新数据
        
        Args:
            data_name: 数据项名称
            
        Returns:
            更新后的DataCategory
        """
        data_type = self.dataname_to_datatype[data_name]
        commands = [
            PollCommand(data_name, self.enabled_channels.get(self.dataname_to_channels[data_name], 'main'))
        ]

        layer = (await self.execute_monitor(commands))[data_type.dt]

        self.data_cache[data_type.dt].update(layer)

        return layer.get_category(data_name)

    def _updatedata_cache(self, data_type: DataType, new_data: DataCategory):
        """更新DataFrame缓存中的DataTypeLayer"""
        layer = self.data_cache[data_type]
        layer.add_category(new_data.category, new_data)
