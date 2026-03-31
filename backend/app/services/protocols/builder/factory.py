# \backend\app\services\protocols\builder\factory.py
"""
命令构建管理器
"""
import logging
from typing import Type
from ....models import ProtocolConfig
from ....services.protocols.base.ibuilder import ICommandBuilder
from .ascii import AsciiCommandBuilder
from .modbus import ModbusCommandBuilder

logger = logging.getLogger(__name__)

class CommandBuilderFactory:
    """命令构建器工厂(单例模式)"""
    _builders: dict[str, ICommandBuilder] = {}
    
    @classmethod
    def get(cls, protocol_config: ProtocolConfig) -> ICommandBuilder:
        """获取或创建构建器实例"""
        config_hash = cls.generate_config_hash(protocol_config)
        
        if config_hash not in cls._builders:
            builder_class = cls._select_builder_class(protocol_config.protocol_type)
            cls._builders[config_hash] = builder_class(
                protocol_config=protocol_config,
            )
            logger.info(f"Created builder for protocol: {protocol_config.name}")
        
        return cls._builders[config_hash]
    
    @classmethod
    def generate_config_hash(cls, config: ProtocolConfig) -> str:
        """生成配置哈希"""
        return f"{config.name}_{config.version}_{config.protocol_type}"
    
    @classmethod
    def _select_builder_class(cls, protocol_type: str) -> Type[ICommandBuilder]:
        """根据协议类型选择构建器类"""
        builder_map: dict[str, Type[ICommandBuilder]] = {
            'tcp': AsciiCommandBuilder,
            'ascii': AsciiCommandBuilder,
            'modbus_tcp': ModbusCommandBuilder,
            'modbus_rtu': ModbusCommandBuilder,
            'serial': AsciiCommandBuilder,
            'usb': AsciiCommandBuilder,
        }
        return builder_map.get(protocol_type, AsciiCommandBuilder)