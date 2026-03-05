from typing import Callable, Optional, Union, Any
import struct
import logging
from ....models import ProtocolConfig, ProtocolType, PollDataType
from ....services.protocols.base.ibuilder import ICommandBuilder

class ModbusCommandBuilder(ICommandBuilder):
    """Modbus命令构建器 - 深度预编译优化"""
    
    def __init__(
        self,
        protocol_config: ProtocolConfig,
        address: Optional[str] = None
    ):
        super().__init__(protocol_config=protocol_config, address=address)
        self.logger = logging.getLogger(f"ModbusCommandBuilder.{protocol_config.name}")
        
        # 深度预编译缓存
        self._register_cache: dict[str, dict[str, Any]] = {}
        self._frame_cache: dict[str, bytes] = {}
        self._converter_cache: dict[str, Callable[...,Any]] = {}
        self._precompile()
        self._validate_protocol_type()

    def _precompile(self):
        """深度预编译Modbus命令"""
        # 预编译所有监控命令的寄存器信息
        for data_type, data_items in self.protocol_config.data.items(): #type:ignore
            for data_name, data_def in data_items.items():
                channel_group = data_def.channel
                
                # 获取通道组的寄存器配置
                channel_config = self._get_channel_config(channel_group)
                
                # 预计算寄存器映射
                register_info = self._precompile_registers(
                    data_name, channel_group, channel_config
                )
                self._register_cache[f"monitor_{data_name}"] = register_info
                
                # 预构建Modbus请求帧
                self._frame_cache[f"monitor_{data_name}"] = self._build_read_frame(
                    register_info
                )
                
                # 预编译数据转换器
                self._converter_cache[f"monitor_{data_name}"] = self._build_converter(
                    channel_config
                )
        
        # 预编译所有控制命令
        for ctrl_name, ctrl_def in self.protocol_config.controls.items():
            channel_group = ctrl_def.channel
            channel_config = self._get_channel_config(channel_group)
            
            register_info = self._precompile_registers(
                ctrl_name, channel_group, channel_config
            )
            self._register_cache[f"control_{ctrl_name}"] = register_info
            
            self._converter_cache[f"control_{ctrl_name}"] = self._build_converter(
                channel_config
            )

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

    def _precompile_registers(
        self,
        name: str,
        channel_group: str,
        channel_config: dict[str, Any]
    ) -> dict[str, Any]:
        """预编译寄存器信息"""
        return {
            "name": name,
            "channel_group": channel_group,
            "address": channel_config.get("address", 0),
            "size": channel_config.get("size", 2),
            "data_type": channel_config.get("type", "int16"),
            "order": channel_config.get("order", "big"),
            "factor": channel_config.get("factor", 1.0)
        }

    def _build_read_frame(self, register_info: dict[str, Any]) -> bytes:
        """预构建Modbus读请求帧"""
        address = register_info["address"]
        size = register_info["size"]
        
        # 构建Modbus读保持寄存器请求（功能码0x03）
        # 格式: 设备地址(1) + 功能码(1) + 起始地址(2) + 寄存器数量(2) + CRC(2)
        device_addr = int(self.address) if self.address else 1
        function_code = 0x03
        
        frame = struct.pack(
            ">BBHH",
            device_addr,
            function_code,
            address,
            size
        )
        
        # 添加CRC校验
        crc = self._calculate_crc(frame)
        return frame + struct.pack("<H", crc)

    def _build_converter(self, channel_config: dict[str, Any]) -> Callable[[bytes], Union[float, int, str,None]]:
        """预构建数据转换器"""
        data_type = channel_config.get("type", "int16")
        order = channel_config.get("order", "big")
        factor = channel_config.get("factor", 1.0)
        
        def converter(raw_data: bytes) -> Union[float, int, str,None]:
            try:
                match data_type:
                    case "str":
                        value = raw_data.decode("ascii", errors="ignore").strip()
                        return value if value else None
                    case "hex":
                        value = hex(int(raw_data.hex())*factor)
                        return value
                    case "int16":
                        value = struct.unpack(f">{order}h", raw_data)[0]
                    case "uint16":
                        value = struct.unpack(f">{order}H", raw_data)[0]
                    case "int32":
                        value = struct.unpack(f">{order}i", raw_data)[0]
                    case "uint32":
                        value = struct.unpack(f">{order}I", raw_data)[0]
                    case "float":
                        value = struct.unpack(f">{order}f", raw_data)[0]
                    case "double":
                        value = struct.unpack(f">{order}d", raw_data)[0]
                        return value * factor if factor != 1.0 else value
                    case _:
                        value = raw_data
                        return str(raw_data)
                    
            except Exception as e:
                self.logger.error(f"Data conversion failed: {e}")
                return None
        
        return converter

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

    def _validate_protocol_type(self):
        if self.protocol_config.protocol_type not in [t.value for t in ProtocolType]:
            raise ValueError(
                f"Invalid protocol type: {self.protocol_config.protocol_type}"
            )

    def build_monitor_command(
        self,
        data_type: PollDataType,
        data_name: str,
        use_multisend: bool = False
    ) -> tuple[str, str]:
        """构建监控命令 - 使用预编译的Modbus帧"""
        command_key = f"monitor_{data_name}"
        
        if command_key in self._frame_cache:
            frame = self._frame_cache[command_key]
            register_info = self._register_cache[command_key]
            
            # 返回十六进制字符串和预期响应长度
            hex_command = frame.hex().upper()
            response_length = register_info["size"] * 2 + 5  # 设备地址+功能码+字节数+数据+CRC
            
            return (hex_command, str(response_length))
        
        raise ValueError(f"No precompiled command found for {data_name}")

    def build_control_command(
        self,
        control_name: str,
        value: Union[float, int, str],
        use_multisend: bool = False
    ) -> tuple[str, str]:
        """构建控制命令 - 使用预编译的转换器"""
        command_key = f"control_{control_name}"
        
        if command_key in self._register_cache:
            register_info = self._register_cache[command_key]
            converter = self._converter_cache[command_key]  #type: ignore
            
            # 转换值
            if isinstance(value, (int, float)):
                scaled_value = value / register_info["factor"]
            else:
                scaled_value = value
            
            # 构建写请求帧
            frame = self._build_write_frame(register_info, scaled_value)
            hex_command = frame.hex().upper()
            
            return (hex_command, "8")  # 标准写响应长度
        
        raise ValueError(f"No precompiled command found for control {control_name}")

    def build_update_command(
        self,
        update_key: str,
        channel: Optional[str] = None,
        use_multisend: bool = False
    ) -> tuple[str, str]:
        """构建更新命令 - 使用预编译的Modbus帧"""
        # 从 update_key 提取数据名称
        if update_key.startswith("get_"):
            data_name = update_key[4:]
        elif update_key.startswith("get_all_"):
            data_name = update_key[8:]
        else:
            raise ValueError(f"Invalid update_key format: {update_key}")
        
        # 尝试获取数据定义
        data_def = None
        for data_type in self.protocol_config.data.values():
            if data_name in data_type:
                data_def = data_type[data_name]
                break
        
        if not data_def:
            raise ValueError(f"No data definition found for {data_name}")
        
        # 如果没有指定 channel，使用数据定义中的 channel
        if channel is None:
            channel = data_def.channel
        
        # 使用预编译的帧
        command_key = f"monitor_{data_name}"
        
        if command_key in self._frame_cache:
            frame = self._frame_cache[command_key]
            register_info = self._register_cache[command_key]
            
            # 返回十六进制字符串和预期响应长度
            hex_command = frame.hex().upper()
            response_length = register_info["size"] * 2 + 5  # 设备地址+功能码+字节数+数据+CRC
            
            return (hex_command, str(response_length))
        
        raise ValueError(f"No precompiled command found for {data_name}")

    def _build_write_frame(self, register_info: dict[str, Any], value: Any) -> bytes:
        """构建Modbus写请求帧"""
        address = register_info["address"]
        data_type = register_info["data_type"]
        order = register_info["order"]
        device_addr = int(self.address) if self.address else 1
        function_code = 0x06  # 写单个寄存器
        
        # 打包数据
        if data_type == "int16":
            data = struct.pack(f">{order}h", int(value))
        elif data_type == "uint16":
            data = struct.pack(f">{order}H", int(value))
        elif data_type == "int32":
            function_code = 0x10  # 写多个寄存器
            data = struct.pack(f">{order}i", int(value))
        elif data_type == "uint32":
            function_code = 0x10
            data = struct.pack(f">{order}I", int(value))
        elif data_type == "float":
            function_code = 0x10
            data = struct.pack(f">{order}f", float(value))
        else:
            data = struct.pack(">H", int(value))
        
        # 构建帧
        if function_code == 0x06:
            frame = struct.pack(">BBHH", device_addr, function_code, address, 0)
            frame += data[:2]
        else:
            frame = struct.pack(">BBHH", device_addr, function_code, address, len(data) // 2)
            frame += struct.pack("B", len(data))
            frame += data
        
        # 添加CRC
        crc = self._calculate_crc(frame)
        return frame + struct.pack("<H", crc)

    def _build_protocol_packet(
        self,
        command: str,
        is_multisend: bool = False,
        channel: Optional[str] = None
    ) -> tuple[str, str]:
        """构建协议报文"""
        proto = self.protocol_config.protocols
        
        send_packet = proto.send.format(
            command=command,
            send_terminator=proto.send_terminator
        )
        
        response_terminator = proto.recv_terminator if is_multisend else proto.response
        
        return (send_packet, response_terminator)
