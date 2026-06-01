from typing import Optional
from .base.idevice import IDeviceProtocol
from ...models import DeviceConfig, ProtocolConfig
from .base.iconnection import IConnection
from .base.ihandler import IHandler
from .base.ibuilder import ICommandBuilder
from .base.iparser import IResponseParser
from .connetion.tcp import TcpConnection
from .handler.modbus_tcp import ModbusTcpHandler
from .builder.factory import CommandBuilderFactory
from .parser.factory import ResponseParserFactory


class ModbusTcpProtocol(IDeviceProtocol):
    def __init__(self, config: DeviceConfig, protocol: ProtocolConfig):
        super().__init__(config=config, protocol=protocol)

        self._connection: Optional[IConnection] = TcpConnection(config.connection)

        self._builder: Optional[ICommandBuilder] = CommandBuilderFactory.get(protocol)

        self._parser: Optional[IResponseParser] = ResponseParserFactory.get(protocol)

        self._handler: Optional[IHandler] = ModbusTcpHandler(
            device=self,
            connection=self._connection,
            builder=self._builder,
            parser=self._parser,
            protocol_config=protocol,
            device_config=config,
            enabled_channels=self.enabled_channels
        )

        self._init_components(
            connection=self._connection,
            builder=self._builder,
            parser=self._parser,
            handler=self._handler
        )
