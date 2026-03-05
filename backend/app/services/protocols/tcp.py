from typing import Optional
from .base.idevice import IDeviceProtocol
from ...models import DeviceConfig, ProtocolConfig
from .base.iconnection import IConnection
from .base.ihandler import IHandler
from .base.ibuilder import ICommandBuilder
from .base.iparser import IResponseParser
from .connetion.tcp import TcpConnection
from .handler.tcp import TcpHandler
from .builder.factory import CommandBuilderFactory
from .parser.factory import ResponseParserFactory

class TcpProtocol(IDeviceProtocol):
    """TCP设备协议基类"""
    def __init__(self, config: DeviceConfig, protocol: ProtocolConfig):
        super().__init__(config=config, protocol=protocol)

        # 初始化连接
        self._connection: Optional[IConnection] = TcpConnection(config.connection)
        
        # 初始化构建器和解析器
        self._builder: Optional[ICommandBuilder] = CommandBuilderFactory.get(protocol)
        self._parser: Optional[IResponseParser] = ResponseParserFactory.get(protocol)
        
        # 初始化处理器
        self._handler: Optional[IHandler] = TcpHandler(
            device=self,
            connection=self._connection,
            builder=self._builder,
            parser=self._parser,
            protocol_config=protocol,
            device_config=config,
            enabled_channels=self.enabled_channels
        )
        
        # 注册组件到基类
        self._init_components(
            connection=self._connection,
            builder=self._builder,
            parser=self._parser,
            handler=self._handler
        )
