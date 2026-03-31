from typing import Optional, Any, Sequence, Union
import logging
import struct
from ....models import ProtocolConfig, ProtocolType, ModbusRegister
from ..base.ibuilder import ICommandBuilder

class ModbusCommandBuilder(ICommandBuilder):
    def __init__(
        self,
        protocol_config: ProtocolConfig,
        address: Optional[str] = None
    ):
        super().__init__(protocol_config=protocol_config, address=address)
        self.logger = logging.getLogger(f"ModbusCommandBuilder.{protocol_config.name}")
        
        self._transaction_id = 0
        self._validate_protocol_type()

    def _validate_protocol_type(self):
        if self.protocol_config.protocol_type != ProtocolType.MODBUS_TCP and \
           self.protocol_config.protocol_type != ProtocolType.MODBUS_RTU:
            raise ValueError(
                f"Invalid protocol type: {self.protocol_config.protocol_type}, expected modbus_tcp or modbus_rtu"
            )

    def _get_next_transaction_id(self) -> int:
        """获取下一个事务ID"""
        self._transaction_id = (self._transaction_id + 1) % 65536
        return self._transaction_id

    def _get_unit_id(self) -> int:
        """获取Modbus从站地址"""
        try:
            return int(self.address) if self.address else 1
        except (ValueError, TypeError):
            self.logger.warning(f"Invalid address {self.address}, using default 1")
            return 1

    def _build_modbus_header(self, length: int, unit_id: int) -> bytes:
        """构建Modbus TCP头部"""
        transaction_id = self._get_next_transaction_id()
        protocol_id = 0
        
        return struct.pack('>HHHB', transaction_id, protocol_id, length, unit_id)

    def _get_register_config(self, data_name: str, channel: str) -> ModbusRegister:
        """获取寄存器配置"""
        data_def = self._get_data_definition(data_name)
        channel_group = data_def.channel_group
        
        if channel_group not in self.channels:
            raise ValueError(f"Channel group {channel_group} not found")
        
        channel_config = self.channels[channel_group]
        
        if isinstance(channel_config, dict):
            if channel not in channel_config:
                raise ValueError(f"Channel {channel} not found in group {channel_group}")
            return channel_config[channel]
        else:
            raise ValueError(f"Channel group {channel_group} is not a ModbusChannel")

    def _merge_continuous_registers(self, register_configs: list[tuple[str, str, ModbusRegister]]) -> list[dict[str, Any]]:
        """合并连续地址的寄存器以减少请求次数
        
        Returns:
            合并后的寄存器请求列表
        """
        if not register_configs:
            return []
        
        merged: list[dict[str, Any]] = []
        current_group: dict[str, Any] = {
            'data_name': register_configs[0][0],
            'channels': [register_configs[0][1]],
            'register_configs': [register_configs[0][2]],
            'start_address': register_configs[0][2].address,
            'register_count': register_configs[0][2].size // 2
        }
        
        for data_name, channel, reg_config in register_configs[1:]:
            expected_address = current_group['start_address'] + current_group['register_count']
            
            if reg_config.address == expected_address and reg_config.type == current_group['register_configs'][0].type:
                current_group['channels'].append(channel)
                current_group['register_configs'].append(reg_config)
                current_group['register_count'] += reg_config.size // 2
            else:
                merged.append(current_group)
                current_group = {
                    'data_name': data_name,
                    'channels': [channel],
                    'register_configs': [reg_config],
                    'start_address': reg_config.address,
                    'register_count': reg_config.size // 2
                }
        
        merged.append(current_group)
        return merged

    def _build_read_request(self, start_address: int, register_count: int, unit_id: int) -> bytes:
        """构建读取请求帧（功能码03或04）"""
        function_code = 0x03
        
        pdu = struct.pack('>BHH', function_code, start_address, register_count)
        length = len(pdu)
        mbap = self._build_modbus_header(length, unit_id)
        
        return mbap + pdu

    def _build_write_single_request(self, address: int, value: int, unit_id: int) -> bytes:
        """构建单个寄存器写入请求帧（功能码06）"""
        function_code = 0x06
        
        pdu = struct.pack('>BHH', function_code, address, value)
        length = len(pdu)
        mbap = self._build_modbus_header(length, unit_id)
        
        return mbap + pdu

    def _build_write_multiple_request(self, start_address: int, values: list[int], unit_id: int) -> bytes:
        """构建多个寄存器写入请求帧（功能码16）"""
        function_code = 0x10
        register_count = len(values)
        byte_count = register_count * 2
        
        values_bytes = b''
        for value in values:
            values_bytes += struct.pack('>H', value)
        
        pdu = struct.pack('>BHHB', function_code, start_address, register_count, byte_count) + values_bytes
        length = len(pdu)
        mbap = self._build_modbus_header(length, unit_id)
        
        return mbap + pdu

    def _value_to_register_value(self, value: Union[float, int, str, bool], reg_config: ModbusRegister) -> int:
        """将值转换为寄存器值（应用缩放因子的逆运算）"""
        try:
            if isinstance(value, bool):
                return 1 if value else 0
            elif isinstance(value, str):
                if reg_config.type == 'str':
                    return int.from_bytes(value.encode('ascii')[:reg_config.size], 'big')
                else:
                    return int(value)
            else:
                scaled_value = float(value) / reg_config.factor
                return int(round(scaled_value))
        except Exception as e:
            self.logger.error(f"Failed to convert value {value} to register value: {e}")
            raise

    def build_poll_command(
        self,
        origin_commands: Sequence[tuple[str, Union[str, list[str]]]]
    ) -> tuple[list[str], list[dict[str, Any]]]: 
        """
        构建轮询命令（读取寄存器）
        
        Args:
            origin_commands: 原始命令元组序列，每个元组包含数据项名称和通道列表或单个通道字符串
                - data_name: 数据项名称
                - channels: 通道列表或单个通道字符串
        
        Returns:
            cmd_keys: 命令键列表
            final_commands: Modbus请求字典列表
        """
        commands: list[dict[str, Any]] = []
        cmd_keys: list[str] = []
        
        for data_name, channels in origin_commands:
            try:
                if isinstance(channels, str):
                    channels = [channels]
                
                register_configs: list[tuple[str, str, ModbusRegister]] = []
                for channel in channels:
                    reg_config = self._get_register_config(data_name, channel)
                    register_configs.append((data_name, channel, reg_config))
                
                merged_requests = self._merge_continuous_registers(register_configs)
                
                for request in merged_requests:
                    unit_id = self._get_unit_id()
                    modbus_request: dict[str, Any] = {
                        'data_name': request['data_name'],
                        'channels': request['channels'],
                        'function_code': 0x03,
                        'start_address': request['start_address'],
                        'register_count': request['register_count'],
                        'register_configs': request['register_configs'],
                        'unit_id': unit_id
                    }
                    commands.append(modbus_request)
                    cmd_keys.append(f"get_{data_name}")
                    
            except ValueError as e:
                self.logger.warning(f"Failed to build poll command for {data_name}: {e}")
                continue
        
        return cmd_keys, commands

    def build_control_command(
        self,
        origin_commands: Sequence[tuple[str, Union[str, list[str]], Any]]
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """
        构建控制命令（写寄存器）
        
        Args:
            origin_commands: 控制命令元组序列，每个元组包含:
                - control_name: 控制项名称
                - channels: 通道列表或单个通道字符串
                - value: 要设置的值
        
        Returns:
            cmd_keys: 命令键列表
            final_commands: Modbus请求字典列表
        """
        commands: list[dict[str, Any]] = []
        cmd_keys: list[str] = []
        
        for control_name, channels, value in origin_commands:
            try:
                ctrl_def = self.protocol_config.controls.get(f"set_{control_name}",None)
                if ctrl_def is None:
                    raise ValueError(f"Control {control_name} not found in protocol config")
                
                self._validate_control_value(ctrl_def, value)
                
                if isinstance(channels, str):
                    channels = [channels]
                
                for channel in channels:
                    reg_config = self._get_register_config(control_name, channel)
                    register_value = self._value_to_register_value(value, reg_config)
                    unit_id = self._get_unit_id()
                    
                    modbus_request: dict[str, Any] = {
                        'control_name': control_name,
                        'channel': channel,
                        'function_code': 0x06,
                        'address': reg_config.address,
                        'value': register_value,
                        'unit_id': unit_id,
                        'register_config': reg_config
                    }
                    commands.append(modbus_request)
                    cmd_keys.append(f"set_{control_name}")
                    
            except ValueError as e:
                self.logger.warning(f"Failed to build control command for {control_name}: {e}")
                continue
        
        return cmd_keys, commands
