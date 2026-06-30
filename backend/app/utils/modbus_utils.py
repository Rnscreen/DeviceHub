# backend/app/utils/modbus_utils.py
import struct
from ..models import ModbusRegister
from typing import Any

# modbus function codes
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

# type to struct format
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

def swap_bytes(data: bytes, type: str, order: str) -> bytes|list[bytes]:
    """
    交换字节序
    params:
        data: 待交换字节序的字节数据
        type: 寄存器类型
        order: 字节序
    return:
        交换字节序后的字节数据
    """
    # 交换寄存器内部字节序(支持2字节和4字节)
    size = TYPE_SIZE.get(type, 2)
    if len(data) == size:
        return swap_bytes_single(data, type, order)
    # len能被size整除, 递归调用swap_bytes处理每个子数据
    elif len(data) % size == 0:
        tmp:list[bytes]=[]
        for i in range(0, len(data), size):
            # 这里忽略类型检查, 因为type一定与size匹配
            tmp.append(swap_bytes_single(data[i:i+size], type, order)) # type: ignore
        return tmp
    else:
        return swap_bytes_single(data, type, order)

def swap_bytes_single(data: bytes, type: str, order: str) -> bytes:
    """
    交换字节序
    params:
        data: 待交换字节序的字节数据
        type: 寄存器类型
        order: 字节序
    return:
        交换字节序后的字节数据
    """
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
    else:
        return data

def parse_value(data: bytes, reg_type: str, order: str, factor: float) -> Any:
    """
    解析寄存器值
    params:
        data: 要解析的字节数据
        reg_type: 寄存器类型
        order: 字节序
        factor: 缩放因子
    return:
        解析后的值
    """
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
    swapped = swap_bytes(data, reg_type, order)
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

def parse_multi_register_value(pdu_data: bytes, reg: ModbusRegister) -> Any:
    expected_bytes = reg.registers * 2
    if len(pdu_data) < expected_bytes:
        pdu_data = pdu_data.ljust(expected_bytes, b'\x00')
    data = pdu_data[:expected_bytes]
    return parse_value(data, reg.type, reg.order, reg.factor)

def pack_value(value: Any, reg_type: str, order: str) -> bytes:
    fmt = TYPE_TO_STRUCT.get(reg_type, '>H')

    if reg_type in ('float',):
        value = float(value)
    elif reg_type in ('double',):
        value = float(value)
    elif reg_type in ('str', 'hex'):
        return pack_string_or_hex(value, order, TYPE_SIZE.get(reg_type, 2) * 2)
    elif 'int' in reg_type or reg_type == 'short':
        value = int(value)
    else:
        value = int(value)

    packed = struct.pack(fmt, value)
    swapped = swap_bytes_single(packed, reg_type, order)
    return swapped

def pack_string_or_hex(value: str|int, order: str, size: int) -> bytes:
    if isinstance(value, str):
        data = value.encode('ascii', errors='ignore').ljust(size, b'\x00')[:size]
    else:
        data = str(value).encode('ascii', errors='ignore').ljust(size, b'\x00')[:size]
    return swap_bytes(data, 'str', order) # type: ignore

def encode_multi_register_value(value_str: str|list[str], reg: ModbusRegister) -> bytes:
    """
    编码多个寄存器值
    params:
        value_str: 要编码的值, 可以是字符串或字符串列表
        reg: 寄存器信息
    return:
        编码后的字节数据
    """
    # 处理列表
    if isinstance(value_str, list):
        results:list[bytes]=[]
        for v in value_str:
            results.append(encode_multi_register_value_single(v, reg))
        return b''.join(results)
    else:
        return encode_multi_register_value_single(value_str, reg)

def encode_multi_register_value_single(value_str: str, reg: ModbusRegister) -> bytes:
    if reg.type in ('str', 'hex'):
        return pack_string_or_hex(value_str, reg.order, reg.registers * 2)
    elif reg.type in ('float',):
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

    return pack_value(value, reg.type, reg.order)

def encode_coil_values(value_str: str, count: int) -> bytes:
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


