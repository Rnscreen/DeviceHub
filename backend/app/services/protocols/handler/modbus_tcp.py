import asyncio
from typing import Any, Optional, Sequence, Union
import logging
import struct

from ....utils.convert_type import convert_type
from ....models import PollDataType, DataFrame, DataCategory
from ..base.ihandler import IHandler

class ModbusTcpHandler(IHandler):
    """Modbus TCP协议处理器实现"""
    
    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self.logger = logging.getLogger(f"ModbusTcpHandler.{self.device_config.id}")
        self.address = self.device_config.connection.address
        self.unit_id = self._get_unit_id()
        self._lock = asyncio.Lock()
    
    def _get_unit_id(self) -> int:
        """获取Modbus从站地址"""
        try:
            return int(self.address) if self.address else 1
        except (ValueError, TypeError):
            self.logger.warning(f"Invalid address {self.address}, using default 1")
            return 1
    
    def _build_modbus_frame(self, request: dict[str, Any]) -> bytes:
        """构建Modbus TCP帧"""
        function_code = request['function_code']
        unit_id = request.get('unit_id', self.unit_id)
        
        if function_code in [0x03, 0x04]:
            start_address = request['start_address']
            register_count = request['register_count']
            pdu = struct.pack('>BHH', function_code, start_address, register_count)
        elif function_code == 0x06:
            address = request['address']
            value = request['value']
            pdu = struct.pack('>BHH', function_code, address, value)
        elif function_code == 0x10:
            start_address = request['start_address']
            values = request['values']
            register_count = len(values)
            byte_count = register_count * 2
            values_bytes = b''.join(struct.pack('>H', v) for v in values)
            pdu = struct.pack('>BHHB', function_code, start_address, register_count, byte_count) + values_bytes
        else:
            raise ValueError(f"Unsupported function code: {function_code}")
        
        length = len(pdu)
        transaction_id = self._get_next_transaction_id()
        protocol_id = 0
        
        mbap = struct.pack('>HHHB', transaction_id, protocol_id, length, unit_id)
        
        return mbap + pdu
    
    def _get_next_transaction_id(self) -> int:
        """获取下一个事务ID"""
        if not hasattr(self, '_transaction_id'):
            self._transaction_id = 0
        self._transaction_id = (self._transaction_id + 1) % 65536
        return self._transaction_id
    
    async def _send_command(self, command: Any) -> bytes:
        """发送Modbus请求并接收响应
        
        Args:
            command: Modbus请求字典
        
        Returns:
            响应字节
        """
        frame = self._build_modbus_frame(command)
        
        async with self._lock:
            await self.connection.send(frame)
            response = await self.connection.receive()
        
        return response
    
    async def execute_monitor(
        self, 
        commands: Sequence[tuple[str, Union[str, list[str]]]]
    ) -> DataFrame:
        """执行批量查询命令
        
        Args:
            commands: 命令序列
            - 每个元素为 (data_name, channel)
            - data_name 数据项名称
            - channel 可以是字符串或字符串列表
        
        Returns:
            DataFrame: 包含查询结果的DataFrame
        """
        data_frame = DataFrame(id=self.device_config.id)
        
        if not commands:
            return data_frame
        
        cmd_keys, built_commands = self.builder.build_poll_command(commands)
        
        if not built_commands:
            return data_frame
        
        responses: Sequence[tuple[str, dict[str, Any]]] = []
        
        for cmd_key, request in zip(cmd_keys, built_commands):
            try:
                response = await self._send_command(request)
                request['response'] = response
                responses.append((cmd_key, request))
            except Exception as e:
                self.logger.error(f"Failed to send command for {cmd_key}: {e}")
                request['response'] = None
                responses.append((cmd_key, request))
        
        parsed_results = self.parser.parse_poll_response(responses)
        
        for _data_name, channels in commands:
            pln = self.dataname_to_datatype.get(_data_name, PollDataType.MONITOR_FAST)
            layer_name = pln.dt
            layer = data_frame[layer_name]
            data_category = DataCategory(layer_name, _data_name)
            
            value_type = self.protocol_config.data[pln][_data_name].type
            
            if not parsed_results:
                self.logger.warning(f"No parsed results for {_data_name}")
                break
            
            result_name, result_value = parsed_results[0]
            
            if result_name != _data_name:
                self.logger.warning(f"Data name mismatch, expected: {_data_name}, actual: {result_name}")
                return data_frame
            
            if isinstance(channels, str):
                channels = [channels]
            
            if isinstance(result_value, dict):
                for key, value in result_value.items():
                    if key in channels:
                        data_category[key] = convert_type(value, value_type) #type:ignore
            else:
                for channel in channels:
                    data_category[channel] = convert_type(result_value, value_type) #type:ignore
            
            layer.add_category(_data_name, data=data_category)
            
            del parsed_results[0]
            
            if not parsed_results:
                break
        
        return data_frame
    
    async def execute_control(
        self, 
        commands: Sequence[tuple[str, Optional[str], str]]
    ) -> list[bool]:
        """执行批量控制命令
        
        Args:
            commands: 命令序列
            - 每个元素为 (control_name, channel, value)
            - channel 为通道名称
            - value 为要设置的值
        
        Returns:
            list[bool]: 控制结果列表
        """
        if not commands:
            return []
        
        formatted_commands: list[tuple[str, str, Any]] = []
        
        for control_name, channel, value in commands:
            if channel is None:
                channel = "main"
            formatted_commands.append((control_name, channel, value))
        
        cmd_keys, built_commands = self.builder.build_control_command(formatted_commands)
        
        if not built_commands:
            return []
        
        responses: Sequence[tuple[str, dict[str, Any]]] = []
        
        for cmd_key, request in zip(cmd_keys, built_commands):
            try:
                response = await self._send_command(request)
                request['response'] = response
                responses.append((cmd_key, request))
            except Exception as e:
                self.logger.error(f"Failed to send control command for {cmd_key}: {e}")
                request['response'] = None
                responses.append((cmd_key, request))
        
        parsed_results, update_keys = self.parser.parse_control_response(responses)
        
        results: list[bool] = []
        for result in parsed_results:
            if isinstance(result, bool):
                results.append(result)
            elif result is not None:
                results.append(True)
            else:
                results.append(False)
        
        if update_keys:
            update_commands: list[tuple[str, Union[str, list[str]]]] = []
            for update_key in update_keys:
                if update_key.startswith("set_"):
                    data_name = update_key[4:]
                else:
                    data_name = update_key
                
                channel_group = self.dataname_to_channels.get(data_name, "main")
                channel = self.enabled_channels.get(channel_group, channel_group)
                update_commands.append((data_name, channel))
            
            if update_commands:
                try:
                    await self.execute_monitor(update_commands)
                except Exception as e:
                    self.logger.warning(f"Update command failed: {e}")
        
        return results
