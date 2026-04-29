"""
响应解析管理器
"""
from typing import Type
from ....models import ProtocolConfig
from typing import Type
from ..base import IResponseParser
from ..builder.factory import CommandBuilderFactory

from logging import Logger
logger = Logger(__name__)

class ResponseParserFactory:
    """响应解析器工厂（单例模式）"""
    _parsers: dict[str, IResponseParser] = {}
    
    @classmethod
    def get(cls, protocol_config: 'ProtocolConfig') -> IResponseParser:
        """获取或创建解析器实例"""
        config_hash = CommandBuilderFactory.generate_config_hash(protocol_config)
        
        if config_hash not in cls._parsers:
            parser_class = cls._select_parser_class(protocol_config.protocol_type)
            cls._parsers[config_hash] = parser_class(protocol_config)
        
        return cls._parsers[config_hash]
    
    @classmethod
    def delete(cls, config_hash:str) -> None:
        """删除解析器实例"""
        if config_hash in cls._parsers:
            del cls._parsers[config_hash]

    @classmethod
    def _select_parser_class(cls, protocol_type: str) -> Type[IResponseParser]:
        """根据协议类型选择解析器类"""
        from . import (
            AsciiResponseParser,
            # ModbusResponseParser
        )
        
        parser_map:dict[str, Type[IResponseParser]] = {
            'tcp': AsciiResponseParser,
            # 'modbus_tcp': ModbusResponseParser,
            # 'modbus_rtu': AsciiResponseParser
        }
        return parser_map.get(protocol_type, AsciiResponseParser)