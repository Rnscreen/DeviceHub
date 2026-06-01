from typing import Optional, Any
import struct
import logging

from ....models import ProtocolConfig, PollCommands, ControlCommands, \
    ControlDefinition, ModbusChannel, ModbusRegister
from ..base.ibuilder import ICommandBuilder

FN_READ_COILS = 0x01
FN_READ_DISCRETE_INPUTS = 0x02
FN_READ_HOLDING_REGISTERS = 0x03
FN_READ_INPUT_REGISTERS = 0x04
FN_WRITE_SINGLE_COIL = 0x05
FN_WRITE_SINGLE_REGISTER = 0x06
FN_WRITE_MULTIPLE_COILS = 0x0F
FN_WRITE_MULTIPLE_REGISTERS = 0x10

READ_FNS = {0x01, 0x02, 0x03, 0x04}
WRITE_SINGLE_FNS = {0x05, 0x06}
WRITE_MULTIPLE_FNS = {0x0F, 0x10}

TYPE_TO_STRUCT: dict[str, str] = {
    'short': '>h',
    'int16': '>h',
    'uint16': '>H',
    'int32': '>i',
    'uint32': '>I',
    'float': '>f',
    'double': '>d',
}

TYPE_SIZE: dict[str, int] = {
    'short': 2, 'int16': 2, 'uint16': 2,
    'int32': 4, 'uint32': 4,
    'float': 4, 'double': 8,
    'hex': 2, 'str': 2,
}

BYTEORDER_MAP: dict[str, str] = {
    '1234': '>',
    '4321': '<',
    '3412': '>',   # handled manually via byte swap
    '2143': '<',   # handled manually via word swap
}


def _swap_bytes(data: bytes, order: str) -> bytes:
    if order in ('1234', '4321'):
        return data
    if order == '3412':
        return b''.join(data[i:i+2][::-1] for i in range(0, len(data), 2))
    if order == '2143':
        return b''.join(data[i:i+2] for i in range(len(data)-2, -1, -2))
    return data


def _pack_value(value: Any, reg_type: str, order: str) -> bytes:
    fmt = TYPE_TO_STRUCT.get(reg_type, '>H')
    base_fmt = BYTEORDER_MAP.get(order, '>')
    fmt = base_fmt + fmt[1:]

    if reg_type in ('float',):
        value = float(value)
    elif reg_type in ('double',):
        value = float(value)
    elif reg_type in ('str', 'hex'):
        return _pack_string_or_hex(value, order, TYPE_SIZE.get(reg_type, 2) * 2)
    elif 'int' in reg_type or reg_type == 'short':
        value = int(value)
    else:
        value = int(value)

    packed = struct.pack(fmt, value)
    if order in ('3412', '2143'):
        packed = _swap_bytes(packed, order)
    return packed


def _pack_string_or_hex(value: str|int, order: str, size: int) -> bytes:
    if isinstance(value, str):
        data = value.encode('ascii', errors='ignore').ljust(size, b'\x00')[:size]
    else:
        data = str(value).encode('ascii', errors='ignore').ljust(size, b'\x00')[:size]
    return _swap_bytes(data, order) if order in ('3412', '2143') else data


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
                values_bytes = self._encode_multi_register_value(formatted_value, reg)
                pdu = _build_write_multiple_registers_pdu(fc, reg.address, values_bytes)

            elif fc == FN_WRITE_MULTIPLE_COILS:
                coil_byte_count = (reg.registers + 7) // 8
                coil_values = self._encode_coil_values(formatted_value, reg.registers)
                pdu = _build_write_multiple_coils_pdu(fc, reg.address, coil_values[:coil_byte_count])

            else:
                self.logger.warning(f"Unsupported write function code {fc} for {control_name}")
                continue

            cmd_key = f"set_{control_name}"
            final_commands.append(pdu)
            cmd_keys.append(cmd_key)

        return cmd_keys, final_commands

    def _encode_multi_register_value(self, value_str: str, reg: ModbusRegister) -> bytes:
        if reg.type in ('str', 'hex'):
            return _pack_string_or_hex(value_str, reg.order, reg.registers * 2)

        if reg.type in ('float',):
            value = float(value_str)
        elif reg.type in ('double',):
            value = float(value_str)
        elif 'int' in reg.type or reg.type == 'short':
            if reg.factor and reg.factor != 1.0 and reg.factor != 0:
                value = int(float(value_str) / reg.factor)
            else:
                value = int(float(value_str))
        else:
            if reg.factor and reg.factor != 1.0 and reg.factor != 0:
                value = int(float(value_str) / reg.factor)
            else:
                value = int(float(value_str))

        return _pack_value(value, reg.type, reg.order)

    def _encode_coil_values(self, value_str: str, count: int) -> bytes:
        try:
            vals = [int(x.strip()) for x in value_str.split(',') if x.strip() != '']
        except ValueError:
            vals = [1 if value_str and value_str not in ('0', 'False', 'false') else 0] * count

        while len(vals) < count:
            vals.append(0)

        byte_count = (count + 7) // 8
        result = bytearray(byte_count)
        for i, v in enumerate(vals[:count]):
            if v:
                result[i // 8] |= (1 << (i % 8))
        return bytes(result)
