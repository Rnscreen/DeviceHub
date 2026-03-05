# \backend\app\services\protocols\parser\modbus.py
"""
Modbus响应解析器 - 深度预编译优化
"""
from typing import Callable, Any, Optional
import struct
import logging
from ....models import ProtocolConfig
from ..base.ihandler import IHandler
from ..base.iparser import IResponseParser

class ModbusResponseParser(IResponseParser):
    """Modbus响应解析器 - 深度预编译优化"""
    
    def __init__(self, protocol_config: ProtocolConfig):
        super().__init__(protocol_config)
        self.logger = logging.getLogger(f"ModbusResponseParser.{protocol_config.name}")
        
        # 深度预编译缓存
        self._converter_cache: dict[str, Callable[[bytes], Any]] = {}
        self._precompile()
    
    def _precompile(self):
        """预编译所有数据转换器"""
        # 预编译监控数据的转换器
        for data_items in self.protocol_config.data.values():
            for data_name, data_def in data_items.items():
                channel_group = data_def.channel
                channel_config = self._get_channel_config(channel_group)
                
                converter = self._build_converter(channel_config)
                self._converter_cache[f"monitor_{data_name}"] = converter
        
        # 预编译控制数据的转换器
        for ctrl_name, ctrl_def in self.protocol_config.controls.items():
            channel_group = ctrl_def.channel
            channel_config = self._get_channel_config(channel_group)
            
            converter = self._build_converter(channel_config)
            self._converter_cache[f"control_{ctrl_name}"] = converter
        
        # 预编译控制命令的 update 配置
        self._control_update_cache: dict[str, Optional[str]] = {}
        for ctrl_name in self.protocol_config.controls.keys():
            parse_key = f"set_{ctrl_name}"
            if parse_key in self.protocol_config.parse:
                parse_def = self.protocol_config.parse[parse_key]
                self._control_update_cache[ctrl_name] = parse_def.update
            else:
                self._control_update_cache[ctrl_name] = None
    
    def _get_channel_config(self, channel_group: str) -> dict[str, Any]:
        """获取通道配置"""
        channels = self.protocol_config.channels.get(channel_group)
        if not channels:
            raise ValueError(f"Channel group {channel_group} not found")
        
        if isinstance(channels, str):
            return {"type": "str", "address": 0, "size": 1, "factor": 1.0}
        
        if isinstance(channels, dict):
            return channels
        
        raise ValueError(f"Invalid channel config for {channel_group}")
    
    def _build_converter(self, channel_config: dict[str, Any]) -> Callable[[bytes], Any]:
        """预构建数据转换器"""
        data_type = channel_config.get("type", "int16")
        order = channel_config.get("order", "big")
        factor = channel_config.get("factor", 1.0)
        
        def converter(raw_data: bytes) -> Any:
            try:
                if data_type == "int16":
                    value = struct.unpack(f">{order}h", raw_data)[0]
                elif data_type == "uint16":
                    value = struct.unpack(f">{order}H", raw_data)[0]
                elif data_type == "int32":
                    value = struct.unpack(f">{order}i", raw_data)[0]
                elif data_type == "uint32":
                    value = struct.unpack(f">{order}I", raw_data)[0]
                elif data_type == "float":
                    value = struct.unpack(f">{order}f", raw_data)[0]
                elif data_type == "double":
                    value = struct.unpack(f">{order}d", raw_data)[0]
                elif data_type == "hex":
                    value = raw_data.hex()
                elif data_type == "str":
                    value = raw_data.decode("ascii", errors="ignore").strip()
                else:
                    value = raw_data
                
                return value * factor if factor != 1.0 else value
            except Exception as e:
                self.logger.error(f"Data conversion failed: {e}")
                return None
        
        return converter
    
    def parse_monitor_response(self, response: str, data_type: str, data_name: str) -> Any:
        """解析监控响应"""
        parse_key = f"monitor_{data_name}"
        
        if parse_key not in self._converter_cache:
            raise ValueError(f"No converter found for {data_name}")
        
        # 将十六进制字符串转换为字节
        try:
            raw_data = bytes.fromhex(response)
        except ValueError as e:
            self.logger.error(f"Invalid hex response: {e}")
            return None
        
        # 验证CRC
        if not self._validate_crc(raw_data):
            self.logger.error(f"CRC validation failed for {data_name}")
            return None
        
        # 提取数据部分（去掉设备地址、功能码、字节数）
        if len(raw_data) >= 3:
            data_bytes = raw_data[3:-2]  # 去掉地址(1) + 功能码(1) + 字节数(1) 和CRC(2)
        else:
            self.logger.error(f"Response too short for {data_name}")
            return None
        
        # 使用预编译的转换器
        converter: Callable[[bytes], Any] = self._converter_cache[parse_key]
        return converter(data_bytes)
    
    def parse_control_response(self, response: str, control_name: str, handler: IHandler) -> tuple[bool, Optional[str]]:
        """解析控制响应
        
        Returns:
            tuple: (是否成功, update_key)
        """
        try:
            raw_data = bytes.fromhex(response)
        except ValueError as e:
            self.logger.error(f"Invalid hex response: {e}")
            return (False, None)
        
        # 验证CRC
        if not self._validate_crc(raw_data):
            self.logger.error(f"CRC validation failed for control {control_name}")
            return (False, None)
        
        # Modbus写响应格式: 设备地址(1) + 功能码(1) + 起始地址(2) + 寄存器数量(2) + CRC(2)
        # 简单验证长度和功能码
        if len(raw_data) == 8:
            device_addr = raw_data[0] # type: ignore
            function_code = raw_data[1]
            
            # 验证功能码（0x06或0x10）
            if function_code in [0x06, 0x10]:
                # 控制成功，返回 update_key（如果有）
                update_key = self._control_update_cache.get(control_name, None)
                return (True, update_key)
        
        return (False, None)
    
    def _validate_crc(self, data: bytes) -> bool:
        """验证Modbus CRC16校验"""
        if len(data) < 2:
            return False
        
        received_crc = struct.unpack("<H", data[-2:])[0]
        calculated_crc = self._calculate_crc(data[:-2])
        
        return received_crc == calculated_crc
    
    def _calculate_crc(self, data: bytes) -> int:
        """计算Modbus CRC16校验"""
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc
    
    def parse_batch_response(self, response: str, data_name: str, terminator: str) -> dict[str, Any]:
        """解析批量响应（多行）
        
        Args:
            response: 批量响应字符串（十六进制格式，可能包含多个响应帧）
            data_name: 数据项名称
            terminator: 响应终止符（Modbus不使用，保留参数兼容性）
            
        Returns:
            解析后的数据字典，按通道组织
        """
        try:
            raw_data = bytes.fromhex(response)
        except ValueError as e:
            self.logger.error(f"Invalid hex response: {e}")
            return {}
        
        # 获取数据定义以确定通道组
        data_def = None
        for data_items in self.protocol_config.data.values():
            if data_name in data_items:
                data_def = data_items[data_name]
                break
        
        if not data_def:
            self.logger.error(f"Data definition not found for {data_name}")
            return {}
        
        channel_group = data_def.channel
        channels = self.protocol_config.channels.get(channel_group, [])
        
        if isinstance(channels, str):
            channels = [channels]
        
        # Modbus批量响应解析
        # 假设响应包含多个连续的寄存器值
        results: dict[str, Any] = {}
        
        # 验证CRC
        if not self._validate_crc(raw_data):
            self.logger.error(f"CRC validation failed for batch response {data_name}")
            return {}
        
        # 提取数据部分（去掉设备地址、功能码、字节数）
        if len(raw_data) >= 3:
            data_bytes = raw_data[3:-2]  # 去掉地址(1) + 功能码(1) + 字节数(1) 和CRC(2)
        else:
            self.logger.error(f"Batch response too short for {data_name}")
            return {}
        
        # 根据通道配置解析数据
        if isinstance(channels, list) and len(channels) > 0:
            # 批量读取多个寄存器的情况
            bytes_per_value = 2  # 默认每个值2字节（int16/uint16）
            
            # 检查第一个通道的配置确定数据类型
            first_channel_config = self._get_channel_config(channel_group)
            data_type = first_channel_config.get("type", "int16")
            
            if data_type in ["int32", "uint32", "float"]:
                bytes_per_value = 4
            elif data_type == "double":
                bytes_per_value = 8
            
            # 解析每个通道的值
            for i, channel in enumerate(channels):
                start_idx = i * bytes_per_value
                end_idx = start_idx + bytes_per_value
                
                if end_idx <= len(data_bytes):
                    value_bytes = data_bytes[start_idx:end_idx]
                    
                    # 为每个通道构建转换器
                    channel_config = self._get_channel_config(channel_group)
                    converter = self._build_converter(channel_config)
                    value = converter(value_bytes)
                    
                    results[channel] = value
                else:
                    self.logger.warning(f"Not enough data for channel {channel}")
                    results[channel] = None
        else:
            # 单通道情况
            channel_config = self._get_channel_config(channel_group)
            converter = self._build_converter(channel_config)
            value = converter(data_bytes)
            results[channel_group] = value
        
        return results
