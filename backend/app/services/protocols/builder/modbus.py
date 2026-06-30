from typing import Optional, Any
import struct
import logging

from ....models import ProtocolConfig, PollCommands, ControlCommands, \
    ControlDefinition, ModbusChannel, ModbusRegister
from ..base.ibuilder import ICommandBuilder
from ....utils.modbus_utils import *

def _build_read_pdu(fc: int, address: int, count: int) -> bytes:
    return struct.pack('>BHH', fc, address, count)


def _build_write_single_pdu(fc: int, address: int, value: int) -> bytes:
    return struct.pack('>BHH', fc, address, value)


def _build_write_multiple_registers_pdu(fc: int, address: int, values: bytes) -> bytes:
    quantity = len(values) // 2
    byte_count = len(values)
    header = struct.pack('>BHHB', fc, address, quantity, byte_count)
    return header + values


def _build_write_multiple_coils_pdu(fc: int, address: int, coil_bytes: bytes) -> bytes:
    quantity = len(coil_bytes) * 8
    byte_count = len(coil_bytes)
    header = struct.pack('>BHHB', fc, address, quantity, byte_count)
    return header + coil_bytes
class ModbusCommandBuilder(ICommandBuilder):
    def __init__(
        self,
        protocol_config: ProtocolConfig,
        address: Optional[str] = None
    ):
        super().__init__(protocol_config=protocol_config, address=address)
        self.logger = logging.getLogger(f"ModbusCommandBuilder.{protocol_config.name}")
        self._unit_id: int = 1
        self._build_register_map()

    def _format_control_value(
        self,
        ctrl_def: ControlDefinition,
        value: Any) -> Any:
        """格式化控制值(覆盖默认方法)"""
        if value is None:
            return ""
        # 数值类型处理
        if ctrl_def.type == 'int':
            return str(int(value))
        elif ctrl_def.type == 'float':
            return f"{float(value):.6f}".rstrip('0').rstrip('.')
        elif ctrl_def.type == 'str':
            if ',' in value:
                return [item.strip() for item in str(value).split(',')]
        
        return str(value)


    def _build_register_map(self):
        self._data_register_map: dict[str, dict[str, ModbusRegister]] = {}
        for _, data_dict in self.protocol_config.data.items(): # poll_dt
            for data_name, data_def in data_dict.items():
                channel_group = data_def.channel_group
                channel_cfg = self.protocol_config.channels.get(channel_group)
                if isinstance(channel_cfg, ModbusChannel):
                    self._data_register_map[data_name] = dict(channel_cfg)

        self._ctrl_register_map: dict[str, dict[str, ModbusRegister]] = {}
        for ctrl_name, ctrl_def in self.protocol_config.controls.items():
            channel_group = ctrl_def.channel_group
            channel_cfg = self.protocol_config.channels.get(channel_group)
            if isinstance(channel_cfg, ModbusChannel):
                self._ctrl_register_map[ctrl_name] = dict(channel_cfg)

    def _get_data_def(self, data_name: str):
        for data_dict in self.protocol_config.data.values():
            if data_name in data_dict:
                return data_dict[data_name]
        raise ValueError(f"Data definition not found for {data_name}")

    def _get_ctrl_def(self, control_name: str) -> ControlDefinition:
        ctrl_def = self.protocol_config.controls.get(control_name)
        if ctrl_def is None:
            raise ValueError(f"Control definition not found for {control_name}")
        return ctrl_def

    def _get_fc_for_data(self, data_name: str) -> int:
        data_def = self._get_data_def(data_name)
        if data_def.fc is not None:
            return data_def.fc
        return FN_READ_HOLDING_REGISTERS

    def _get_fc_for_ctrl(self, control_name: str) -> int:
        ctrl_def = self._get_ctrl_def(control_name)
        if ctrl_def.fc is not None:
            return ctrl_def.fc
        return FN_WRITE_SINGLE_REGISTER

    def build_poll_command(
        self,
        origin_commands: PollCommands
    ) -> tuple[PollCommands, list[str], list[Any]]:
        cmd_keys: list[str] = []
        final_commands: list[bytes] = []
        valid_commands: PollCommands = []

        for cmd in origin_commands:
            if cmd.channel is None:
                continue

            data_name = cmd.data_name
            try:
                fc = self._get_fc_for_data(data_name)
                register_map = self._data_register_map.get(data_name, {})
            except ValueError as e:
                self.logger.warning(f"Skipping {data_name}: {e}")
                continue

            channels = [cmd.channel] if isinstance(cmd.channel, str) else list(cmd.channel)

            for ch in channels:
                reg = register_map.get(ch)
                if reg is None:
                    self.logger.warning(f"No register config for channel {ch} in {data_name}")
                    continue

                if fc in READ_FNS:
                    pdu = _build_read_pdu(fc, reg.address, reg.registers)
                else:
                    self.logger.warning(f"Unsupported read function code {fc} for {data_name}")
                    continue

                cmd_key = f"get_{data_name}:{ch}"
                final_commands.append(pdu)
                cmd_keys.append(cmd_key)

        return valid_commands, cmd_keys, final_commands

    def build_control_command(
        self,
        origin_commands: ControlCommands
    ) -> tuple[list[str], list[Any]]:
        cmd_keys: list[str] = []
        final_commands: list[bytes] = []

        for cmd in origin_commands:
            control_name = cmd.control_name
            try:
                fc = self._get_fc_for_ctrl(control_name)
                register_map = self._ctrl_register_map.get(control_name, {})
                ctrl_def = self._get_ctrl_def(control_name)
            except ValueError as e:
                self.logger.warning(f"Skipping control {control_name}: {e}")
                continue

            channel_name = cmd.channel
            reg = register_map.get(channel_name)
            if reg is None:
                self.logger.warning(f"No register config for channel {channel_name} in control {control_name}")
                continue

            try:
                self._validate_control_value(ctrl_def, cmd.value)
            except ValueError as e:
                self.logger.warning(f"Control value validation failed for {control_name}: {e}")
                continue

            formatted_value = self._format_control_value(ctrl_def, cmd.value)

            if fc == FN_WRITE_SINGLE_COIL:
                coil_val = 0xFF00 if formatted_value and formatted_value not in ('0', 'False', 'false') else 0x0000
                pdu = _build_write_single_pdu(fc, reg.address, coil_val)

            elif fc == FN_WRITE_SINGLE_REGISTER:
                if reg.factor and reg.factor != 1.0 and reg.factor != 0:
                    int_val = int(float(formatted_value) / reg.factor) if formatted_value else 0
                else:
                    int_val = int(float(formatted_value)) if formatted_value else 0
                pdu = _build_write_single_pdu(fc, reg.address, int_val)

            elif fc == FN_WRITE_MULTIPLE_REGISTERS:
                values_bytes = encode_multi_register_value(formatted_value, reg)
                pdu = _build_write_multiple_registers_pdu(fc, reg.address, values_bytes)

            elif fc == FN_WRITE_MULTIPLE_COILS:
                coil_byte_count = (reg.registers + 7) // 8
                coil_values = encode_coil_values(formatted_value, reg.registers)
                pdu = _build_write_multiple_coils_pdu(fc, reg.address, coil_values[:coil_byte_count])

            else:
                self.logger.warning(f"Unsupported write function code {fc} for {control_name}")
                continue

            cmd_key = f"set_{control_name}"
            final_commands.append(pdu)
            cmd_keys.append(cmd_key)

        return cmd_keys, final_commands
