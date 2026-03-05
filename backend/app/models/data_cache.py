"""
定义设备缓存数据结构
"""
# /backend/app/models/data_cache.py
from typing import  Any

from .data_point import DataFrame
from .device_config import DeviceConfig
from .protocol_config import ProtocolConfig

class DataCache(DataFrame):
    """设备数据缓存 - 带初始化"""
    def __init__(self, protocol_config: Any, device_config: Any):
        super().__init__()
        self._init_from_config(protocol_config, device_config)

    def _get_channels_by_enabled(self,protocol_config:ProtocolConfig,
                                device_config:DeviceConfig,
                                channel_group:str):
        """根据数据类型, 通道名, 获取创建的通道"""
        
        channel = protocol_config.channels[channel_group]
        # 如果为抽象通道
        if isinstance(channel,str):
            return [channel]

        channels:list[str]=[]
        # 获取该通道组启用的通道
        if device_config.enabled_channels is not None:
            channels = device_config.enabled_channels[channel_group]
        else:
            from .protocol_config import ModbusChannel
            if isinstance(channel,ModbusChannel):
                channels = list(channel.keys())
            else:
                channels = channel

        return channels

    def _init_from_config(self, protocol_config:ProtocolConfig, device_config:DeviceConfig):
        """根据协议和设备配置初始化数据结构"""

        # 0. 初始化id
        self.id = device_config.id

        # 1. 从协议获取data定义
        for poll_data_type, categories in protocol_config.data.items():
            data_type = poll_data_type.dt
            layer = self[data_type]

            channelkeys:dict[str,list[str]]={}

            for category, data_def in categories.items():
                # 获取通道组
                channelkeys={
                    category:self._get_channels_by_enabled(
                        protocol_config,
                        device_config,
                        data_def.channel_group)
                    }
                # 创建category
                layer.get_category(category, channelkeys)

        # 2. 初始化controls
        channelkeys:dict[str,list[str]]={}
        for category, ctrl_def in protocol_config.controls.items():
            channelkeys={category:self._get_channels_by_enabled(
                        protocol_config,
                        device_config,
                        ctrl_def.channel_group
                        )}
            if self.controls is not None:
                self.controls.get_category(category, channelkeys)
