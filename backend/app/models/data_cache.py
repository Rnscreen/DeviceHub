"""
定义设备缓存数据结构
"""
# /backend/app/models/data_cache.py
from typing import  Any

from .data_point import DataFrame
from .device_config import DeviceConfig, EnabledChannels
from .protocol_config import ProtocolConfig

class DataCache(DataFrame):
    """设备数据缓存 - 带初始化"""
    def __init__(self, protocol_config: Any, device_config: Any):
        super().__init__()
        self._init_from_config(protocol_config, device_config)

    def init_enabled_channels(self, protocol_config:ProtocolConfig, device_config:DeviceConfig)->EnabledChannels:
        """根据协议和设备配置初始化数据结构"""
        # 1. 初始化enabled_channels
        enabled_channels:EnabledChannels = {}
        
        # 2. 从protocol_config获取channel组
        for group_name, channel_group in protocol_config.channels.items():

            single_channels:list[str]=[]

            # 如果为抽象通道
            if isinstance(channel_group,str):
                enabled_channels[group_name] = [channel_group]
                continue

            # 获取该通道组启用的通道:
            if device_config.enabled_channels is None or \
                device_config.enabled_channels == {}:
                # 从协议配置中获取所有通道
                single_channels = protocol_config.channels.all_channels[group_name]
            else:
                # 如果定义了enabled_channels, 判断enabled_channels中是否有该通道组
                if group_name in device_config.enabled_channels:
                    single_channels = device_config.enabled_channels[group_name]
                # 否则从协议配置中获取该组通道
                else:
                    single_channels = protocol_config.channels.all_channels[group_name]

            enabled_channels[group_name] = single_channels
        
        return enabled_channels

    def _init_from_config(self, protocol_config:ProtocolConfig, device_config:DeviceConfig):
        """根据协议和设备配置初始化数据结构"""

        # 0. 初始化id
        self.id = device_config.id

        # 1. 初始化enabled_channels
        device_config.enabled_channels = self.init_enabled_channels(protocol_config, device_config)

        # 2. 从协议获取data定义
        for poll_data_type, categories in protocol_config.data.items():
            data_type = poll_data_type.dt
            layer = self[data_type]

            channelkeys:dict[str,list[str]]={}

            for category, data_def in categories.items():
                
                # 获取通道组
                channelkeys={
                    category:device_config.enabled_channels[data_def.channel_group]
                }
                # 创建category
                layer.get_category(category, channelkeys)

