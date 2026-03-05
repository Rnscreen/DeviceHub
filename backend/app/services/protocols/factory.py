# app/protocols/manager.py
"""
协议管理器 - 根据协议类型创建对应的协议类实例
"""
from typing import Type
from .base.idevice import IDeviceProtocol
from ...models import ProtocolType,ProtocolConfig, DeviceConfig
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
        # ProtocolType.ModbusTcp: ModbusTcpProtocol,
        # ProtocolType.Serial: SerialProtocol,
        # ProtocolType.ModbusRTU: ModbusRtuProtocol,
        # ProtocolType.USB: UsbProtocol,
        # 其他协议...
    }

    def create_protocol(self, device_config: DeviceConfig, protocol_config:ProtocolConfig)->IDeviceProtocol:
        try:                      
            # 创建协议实例
            protocol_class = self._protocol_classes.get(protocol_config.protocol_type)
            if not protocol_class:
                raise ValueError(f"不支持的协议类型: {protocol_config.protocol_type}")
                
            return protocol_class(device_config, protocol_config)
            
        except ValueError as ve:
            logger.error(f"配置验证失败: {ve}")
            raise
        except Exception as e:
            logger.error(f"协议初始化异常: {e}")
            raise