from typing import Callable, Optional
from typing import Sequence, Union, Any
import logging
import struct

from backend.app.models.protocol_config import ModbusChannel
from ....models import ProtocolConfig, ModbusRegister
from ..base.iparser import IResponseParser

class ModbusResponseParser(IResponseParser):
    """Modbus TCP响应解析器"""
    
    def __init__(self, protocol_config: ProtocolConfig):
        super().__init__(protocol_config)
        self.logger = logging.getLogger(f"ModbusResponseParser.{protocol_config.name}")
    
    def _check_exception(self, response: bytes) -> Optional[int]:
        """检查响应是否包含异常码
        
        Returns:
            异常码，如果没有异常则返回None
        """
        if len(response) < 8:
            return None
        
        try:
            function_code = response[7]
            if function_code & 0x80:
                exception_code = response[8] if len(response) > 8 else 0
                return exception_code
        except Exception as e:
            self.logger.error(f"Failed to check exception: {e}")
        
        return None
    
    def _get_exception_message(self, exception_code: int) -> str:
        """获取异常消息"""
        exception_messages = {
            0x01: "Illegal function",
            0x02: "Illegal data address",
            0x03: "Illegal data value",
            0x04: "Slave device failure",
            0x05: "Acknowledge",
            0x06: "Slave device busy",
            0x07: "Negative acknowledge",
            0x08: "Memory parity error",
            0x0A: "Gateway path unavailable",
            0x0B: "Gateway target device failed to respond"
        }
        return exception_messages.get(exception_code, f"Unknown exception code: 0x{exception_code:02X}")
    
    def _convert_register_value(self, raw_bytes: bytes, reg_config: ModbusRegister) -> Union[int, float, str]:
        """根据寄存器配置转换值
        
        Args:
            raw_bytes: 原始字节数据
            reg_config: 寄存器配置
        
        Returns:
            转换后的值
        """
        try:
            data_type = reg_config.type
            byte_order = '>' if reg_config.order == 'big' else '<'
            
            if data_type == 'int16':
                value = struct.unpack(f'{byte_order}h', raw_bytes[:2])[0]
            elif data_type == 'uint16':
                value = struct.unpack(f'{byte_order}H', raw_bytes[:2])[0]
            elif data_type == 'int32':
                value = struct.unpack(f'{byte_order}i', raw_bytes[:4])[0]
            elif data_type == 'uint32':
                value = struct.unpack(f'{byte_order}I', raw_bytes[:4])[0]
            elif data_type == 'float':
                value = struct.unpack(f'{byte_order}f', raw_bytes[:4])[0]
            elif data_type == 'double':
                value = struct.unpack(f'{byte_order}d', raw_bytes[:8])[0]
            elif data_type == 'hex':
                value = raw_bytes.hex().upper()
            elif data_type == 'str':
                value = raw_bytes.decode('ascii', errors='ignore').rstrip('\x00')
            else:
                raise ValueError(f"Unsupported data type: {data_type}")
            
            return value
            
        except Exception as e:
            self.logger.error(f"Failed to convert register value: {e}")
            raise
    
    # def _apply_scaling(self, value: Union[int, float], factor: float) -> float:
    #     """应用缩放因子"""
    #     return float(value) * factor
    # 使用lambda重写apply_scaling方法
    _apply_scaling: Callable[[Union[int, float], float], float] = \
        lambda value, factor: float(value) * factor
    
    def _parse_read_response(self, response: bytes, register_configs: ModbusChannel) -> dict[str, Any]:
        """
        解析读取响应
        
        Args:
            response: Modbus响应帧
            register_configs: 寄存器配置列表
        
        Returns:
            解析后的数据字典 {channel: value}
        """
        result: dict[str, Any] = {}
        
        try:
            byte_count = response[8]
            data_bytes = response[9:9+byte_count]
            
            offset = 0
            for reg_name,reg_config in register_configs.items():
                reg_bytes = data_bytes[offset:offset+reg_config.size]
                raw_value = self._convert_register_value(reg_bytes, reg_config)
                if isinstance(raw_value, (int, float)):
                    scaled_value = self._apply_scaling(raw_value, reg_config.factor)
                else:
                    scaled_value = raw_value
                result[reg_name] = scaled_value
                offset += reg_config.size
                
        except Exception as e:
            self.logger.error(f"Failed to parse read response: {e}")
            raise
        
        return result
    
    def _parse_write_response(self, response: bytes) -> bool:
        """
        解析写入响应
        
        Args:
            response: Modbus响应帧
        
        Returns:
            写入是否成功
        """
        try:
            function_code = response[7]
            
            if function_code & 0x80:
                exception_code = response[8]
                error_msg = self._get_exception_message(exception_code)
                self.logger.error(f"Write failed: {error_msg}")
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to parse write response: {e}")
            return False
    
    def parse_poll_response(self, 
                        origin_responses: Sequence[tuple[str, dict[str, Any]]]) -> list[tuple[str, Any]]:
        """
        解析轮询响应
        
        Args:
            origin_responses: 原始响应序列，每个元素为(cmd_key, modbus_request_with_response)
                - cmd_key: 命令键
                - modbus_request_with_response: 包含请求信息和响应字节的字典
        
        Returns:
            解析结果列表,顺序与origin_responses中cmd_key顺序一致
        """
        results: list[tuple[str, Any]] = []
        
        for cmd_key, request_data in origin_responses:
            try:
                response = request_data.get('response')
                if not response:
                    self.logger.warning(f"No response for {cmd_key}")
                    results.append((cmd_key, None))
                    continue
                
                exception_code = self._check_exception(response)
                if exception_code is not None:
                    error_msg = self._get_exception_message(exception_code)
                    self.logger.error(f"Exception in response for {cmd_key}: {error_msg}")
                    results.append((cmd_key, None))
                    continue
                
                data_name = request_data.get('data_name', cmd_key.replace('get_', ''))
                channels = request_data.get('channels', [])
                register_configs = request_data.get('register_configs', [])
                
                if not register_configs:
                    self.logger.warning(f"No register configs for {cmd_key}")
                    results.append((cmd_key, None))
                    continue
                
                parsed_data = self._parse_read_response(response, register_configs)
                
                if len(channels) == 1:
                    results.append((data_name, list(parsed_data.values())[0]))
                else:
                    channel_dict: dict[str, Any] = {}
                    for i, reg_config in enumerate(register_configs):
                        if i < len(channels):
                            channel_dict[channels[i]] = parsed_data[reg_config]
                    results.append((data_name, channel_dict))
                    
            except Exception as e:
                self.logger.error(f"Failed to parse poll response for {cmd_key}: {e}")
                results.append((cmd_key, None))
        
        return results
    
    def parse_control_response(self,
                            origin_responses: Sequence[tuple[str, dict[str, Any]]]) -> tuple[Sequence[Any], list[str]]:
        """
        解析控制响应
        
        Args:
            origin_responses: 原始响应序列，每个元素为(control_key, modbus_request_with_response)
                - control_key: 命令键
                - modbus_request_with_response: 包含请求信息和响应字节的字典
        
        Returns:
            values: 解析后的值序列（布尔值表示是否成功）
            updates: 需要从poll更新的通道序列（Modbus通常为空）
        """
        values: list[Any] = []
        updates: list[str] = []
        
        for control_key, request_data in origin_responses:
            try:
                response = request_data.get('response')
                if not response:
                    self.logger.warning(f"No response for {control_key}")
                    values.append(False)
                    continue
                
                exception_code = self._check_exception(response)
                if exception_code is not None:
                    error_msg = self._get_exception_message(exception_code)
                    self.logger.error(f"Exception in response for {control_key}: {error_msg}")
                    values.append(False)
                    continue
                
                success = self._parse_write_response(response)
                values.append(success)
                
            except Exception as e:
                self.logger.error(f"Failed to parse control response for {control_key}: {e}")
                values.append(False)
        
        return values, updates
