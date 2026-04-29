# app/protocols/manager.py
"""
协议管理器 - 根据协议类型创建对应的协议类实例
"""
from typing import Type
from .base.idevice import IDeviceProtocol
from ...models import ProtocolType
from ...models import settings
from .builder.factory import CommandBuilderFactory
from .parser.factory import ResponseParserFactory
from typing import Type
from .tcp  import TcpProtocol
# from .modbus_tcp import ModbusTcpProtocol
# from .modbus_rtu import ModbusRtuProtocol
# from .serial import SerialProtocol

from logging import Logger
logger = Logger(__name__)

class ProtocolFactory:
    _protocol_classes:dict[ProtocolType,Type[IDeviceProtocol]] = {
        ProtocolType.TCP: TcpProtocol,
        # ProtocolType.MODBUS_TCP: ModbusTcpProtocol,
        # ProtocolType.ModbusRTU: ModbusRtuProtocol,
        # ProtocolType.Serial: SerialProtocol,
        # 其他协议...
    }
    def reload_protocol(self, device_id:str)->IDeviceProtocol:
        device_config = settings.device_configs[device_id]
        protocol_name = f"{device_config.model}_{device_config.version}".lower()
        protocol_config = settings.protocol_configs[protocol_name]
        
        config_hash = CommandBuilderFactory.generate_config_hash(protocol_config)
        
        CommandBuilderFactory().delete(config_hash)
        ResponseParserFactory().delete(config_hash)

        return self.create_protocol(device_id)

    def create_protocol(self, device_id:str)->IDeviceProtocol:
        try:                      
            # 创建协议实例
            device_config = settings.device_configs[device_id]
            protocol_name = f"{device_config.model}_{device_config.version}".lower()
            protocol_config = settings.protocol_configs[protocol_name]

            protocol_class = self._protocol_classes[protocol_config.protocol_type]

            if not protocol_class:
                raise ValueError(f"不支持的协议类型: {protocol_config.protocol_type}")
                
            return protocol_class(device_config, protocol_config)
            
        except ValueError as ve:
            logger.error(f"配置验证失败: {ve}")
            raise
        except Exception as e:
            logger.error(f"协议初始化异常: {e}")
            raise