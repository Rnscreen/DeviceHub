from typing import Sequence, Any, Optional
import struct
import logging
from collections import defaultdict

from ....models import ProtocolConfig, ModbusChannel, ModbusRegister
from ..base.iparser import IResponseParser

FN_READ_COILS = 0x01
FN_READ_DISCRETE_INPUTS = 0x02
FN_READ_HOLDING_REGISTERS = 0x03
FN_READ_INPUT_REGISTERS = 0x04
FN_WRITE_SINGLE_COIL = 0x05
FN_WRITE_SINGLE_REGISTER = 0x06
FN_WRITE_MULTIPLE_COILS = 0x0F
FN_WRITE_MULTIPLE_REGISTERS = 0x10

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
    'hex': 1, 'str': 1, 'bit': 1,
}

def _swap_bytes(data: bytes, type: str, order: str) -> bytes|list[bytes]:
    # 交换寄存器内部字节序(支持2字节和4字节)
    size = TYPE_SIZE.get(type, 2)
    if len(data) == 2 and size == 2:
        match order:
            case '12' | 'big':
                return data
            case '21' | 'little':
                return bytes([data[1], data[0]])
            case _:
                return data
    elif len(data) == 4 and size == 4:
        match order:
            case '4321'|'little':
                return bytes([data[3], data[2], data[1], data[0]])
            case '3412':
                return bytes([data[2], data[3], data[0], data[1]])
            case '2143':
                return bytes([data[1], data[0], data[3], data[2]])
            case _: # '1234' or other
                return data
    # len能被size整除, 递归调用swap_bytes处理每个子数据
    elif len(data) % size == 0:
        tmp:list[bytes]=[]
        for i in range(0, len(data), size):
            # 这里忽略类型检查, 因为type一定与size匹配
            tmp.append(_swap_bytes(data[i:i+size], type, order)) # type: ignore
        return tmp
    else:
        return data
    
def _parse_value(data: bytes, reg_type: str, order: str, factor: float) -> Any:

    # str直接解码ascii编码的字符串
    if reg_type == 'str':
        return data.decode('ascii', errors='ignore').rstrip('\x00')
    # hex直接返回码值
    if reg_type == 'hex':
        return data.hex()
    # bit 返回长度为8的二进制字符串, 例如 '01010101'
    if reg_type == 'bit':
        return data.hex().zfill(8)

    # 其他类型需要交换字节序
    swapped = _swap_bytes(data, reg_type, order)
    # 即使是小端，也被交换成大端排序，因此直接使用大端格式
    fmt = TYPE_TO_STRUCT.get(reg_type, '>H')

    if isinstance(swapped, bytes):
        swapped = [swapped]

    swapped = list(swapped)
    results:list[Any]=[]
    for tmp in swapped:
        # 解包
        try:
            raw = struct.unpack(fmt, bytes(tmp))[0]
        except struct.error:
            return 0
        
        # 乘以缩放因子
        # 这里不需要直接转化为最终类型, 最终类型需要根据存在数据库里的type字段进行转换, 这里只做缩放因子的处理
        if reg_type in ('float', 'double'):
            # results.append(round(raw * factor, 6))
            # 如果有效位数超过4位, 采用科学计数法表示, 否则采用4位小数
            if abs(raw * factor) > 10000 or abs(raw * factor) < 0.001:
                results.append(f"{raw * factor:.6e}")
            else:
                results.append(f"{raw * factor:.4f}")
        elif reg_type in ('int32', 'uint32', 'int16', 'uint16', 'short'):
            # 如果factor为1, 则直接返回原始值
            results.append(round(raw * factor, 2) if factor != 1 else raw)
        else:
            results.append(raw)

    if len(results) == 1:
        return results[0]
    return str(results)[1:-1]


def _parse_multi_register_value(pdu_data: bytes, reg: ModbusRegister) -> Any:
    expected_bytes = reg.registers * 2
    if len(pdu_data) < expected_bytes:
        pdu_data = pdu_data.ljust(expected_bytes, b'\x00')
    data = pdu_data[:expected_bytes]
    return _parse_value(data, reg.type, reg.order, reg.factor)


class ModbusResponseParser(IResponseParser):
    def __init__(self, protocol_config: ProtocolConfig):
        super().__init__(protocol_config)
        self.logger = logging.getLogger(f"ModbusResponseParser.{protocol_config.name}")
        self._build_channel_registry()

    def _build_channel_registry(self):
        self._data_channels: dict[str, dict[str, ModbusRegister]] = {}
        for _, data_dict in self.protocol_config.data.items(): # poll_dt
            for data_name, data_def in data_dict.items():
                channel_group = data_def.channel_group
                channel_cfg = self.protocol_config.channels.get(channel_group)
                if isinstance(channel_cfg, ModbusChannel):
                    self._data_channels[data_name] = dict(channel_cfg)

        self._ctrl_channels: dict[str, dict[str, ModbusRegister]] = {}
        for ctrl_name, ctrl_def in self.protocol_config.controls.items():
            channel_group = ctrl_def.channel_group
            channel_cfg = self.protocol_config.channels.get(channel_group)
            if isinstance(channel_cfg, ModbusChannel):
                self._ctrl_channels[ctrl_name] = dict(channel_cfg)

    def _extract_data_name(self, cmd_key: str) -> str:
        if ':' in cmd_key:
            cmd_key = cmd_key.split(':')[0]
        if cmd_key.startswith("get_all_"):
            return cmd_key[8:]
        elif cmd_key.startswith("get_"):
            return cmd_key[4:]
        elif cmd_key.startswith("set_"):
            return cmd_key[4:]
        return cmd_key

    def _extract_channel(self, cmd_key: str) -> Optional[str]:
        if ':' in cmd_key:
            return cmd_key.split(':', 1)[1]
        return None

    def parse_poll_response(
        self,
        origin_responses: Sequence[tuple[str, Any]]
    ) -> list[tuple[str, dict[str, Any]]]:
        grouped: dict[str, list[tuple[Optional[str], bytes]]] = defaultdict(list)
        data_order: list[str] = []
        for cmd_key, response in origin_responses:
            # 提取数据点名称 get_{name}:channel
            data_name = cmd_key.split(':')[0][4:]
            channel = self._extract_channel(cmd_key)
            if data_name not in data_order:
                data_order.append(data_name)
            if isinstance(response, bytes):
                grouped[data_name].append((channel, response))
            elif isinstance(response, str):
                grouped[data_name].append((channel, response.encode('ascii')))

        results: list[tuple[str, dict[str, Any]]] = []
        for data_name in data_order:
            responses = grouped.get(data_name, [])
            if not responses:
                # 没有响应, 则跳过
                continue
            
            channel_map = self._data_channels.get(data_name, {})

            if not channel_map:
                value = self._parse_single_poll_response(responses[0][1])
                results.append((data_name, value))
                continue

            channel_values: dict[str, Any] = {}
            for ch_name, pdu in responses:
                reg = channel_map.get(ch_name) if ch_name else None
                if reg and ch_name:
                    channel_values[ch_name] = self._parse_single_poll_response(pdu, reg)

            for ch in channel_map:
                if ch not in channel_values:
                    channel_values[ch] = None

            results.append((data_name, channel_values))

        return results

    def _parse_single_poll_response(
        self, pdu: bytes, reg: Optional[ModbusRegister] = None
    ) -> Any:
        if not pdu or len(pdu) < 2:
            return None

        fc = pdu[0]
        if fc & 0x80:
            exception_code = pdu[1] if len(pdu) > 1 else 0
            self.logger.warning(f"Modbus exception: FC={fc & 0x7F}, code={exception_code}")
            return None

        if fc in (FN_READ_COILS, FN_READ_DISCRETE_INPUTS):
            if len(pdu) < 2:
                return None
            byte_count = pdu[1]
            coil_data = pdu[2:2+byte_count]
            if reg and reg.type in ('short', 'int16', 'uint16'):
                raw = int.from_bytes(coil_data[:2], byteorder='big', signed=(reg.type == 'short' or 'int' in reg.type))
                return int(raw * reg.factor)
            return coil_data

        if fc in (FN_READ_HOLDING_REGISTERS, FN_READ_INPUT_REGISTERS):
            if len(pdu) < 2:
                return None
            byte_count = pdu[1]
            register_data = pdu[2:2+byte_count]

            if reg:
                return _parse_multi_register_value(register_data, reg)

            return register_data

        self.logger.warning(f"Unexpected function code in poll response: {fc:#04x}")
        return None

    def parse_control_response(
        self,
        origin_responses: Sequence[tuple[str, Any]]
    ) -> tuple[Sequence[Any], list[str]]:
        values: list[Any] = []
        updates: list[str] = []

        for cmd_key, response in origin_responses:
            if isinstance(response, bytes):
                pdu = response
            elif isinstance(response, str):
                pdu = response.encode('ascii')
            else:
                values.append(False)
                continue

            success = self._parse_control_pdu(pdu)

            if cmd_key.startswith("set_"):
                data_name = cmd_key[4:]
                updates.append(data_name)

            values.append(success)

        return values, updates

    def _parse_control_pdu(self, pdu: bytes) -> bool:
        if not pdu or len(pdu) < 1:
            return False

        fc = pdu[0]
        if fc & 0x80:
            self.logger.warning(f"Modbus write exception: FC={fc & 0x7F}")
            return False

        if fc in (FN_WRITE_SINGLE_COIL, FN_WRITE_SINGLE_REGISTER):
            return len(pdu) >= 5

        if fc in (FN_WRITE_MULTIPLE_COILS, FN_WRITE_MULTIPLE_REGISTERS):
            return len(pdu) >= 5

        return True
