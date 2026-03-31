from typing import Sequence
from abc import ABC, abstractmethod
from typing import Optional, Any, Union

from ....models import ProtocolConfig, ControlDefinition, DataDefinition

class ICommandBuilder(ABC):
    """命令构建器抽象基类 - 重新设计版本"""
    
    def __init__(
        self,
        protocol_config: ProtocolConfig,
        address: Optional[str] = None
    ): 
        self.protocol_config = protocol_config
        self.channels = protocol_config.channels
        self.commands = protocol_config.command
        self.address = address
        self._validate_config()

        # 初始化数据类型到数据项的映射
        self.datatype_to_data_name = {
            dt: [data_name for data_name in protocol_config.data[dt]]
            for dt in protocol_config.data
        }
        # 初始化数据项到数据类型的映射
        self.dataname_to_datatype = {
            data_name: poll_data_type
            for poll_data_type, data_dict in protocol_config.data.items()
            for data_name in data_dict
        }

        # 初始化数据项到通道组的映射
        self.dataname_to_channels = {
            data_name: data_def.channel_group
            for data_dict in protocol_config.data.values()
            for data_name, data_def in data_dict.items()
        }
        # 初始化数据项的报警值（max,min），默认值为None
        self.alarm_values = {
            data_name: (data_def.max, data_def.min)
            for data_dict in protocol_config.data.values()
            for data_name, data_def in data_dict.items()
        }

    def _validate_config(self):
        """验证配置有效性"""
        self._validate_channel_references()

    def _validate_channel_references(self):
        """验证所有数据和控制项引用的通道是否存在"""
        for data_items in self.protocol_config.data.values():
            for item_name, item_def in data_items.items():
                if item_def.channel_group not in self.channels:
                    raise ValueError(
                        f"Data item {item_name} references non-existent channel: {item_def.channel_group}"
                    )

        for ctrl_name, ctrl_def in self.protocol_config.controls.items():
            if ctrl_def.channel_group not in self.channels:
                raise ValueError(
                    f"Control {ctrl_name} references non-existent channel: {ctrl_def.channel_group}"
                )

    @abstractmethod
    def build_poll_command(self,
        origin_commands: Sequence[tuple[str, Union[str,list[str]]]]) -> tuple[list[str], list[Any]]:
        """构建轮询命令 - 优先使用批量命令
        
        Args:
            origin_commands: 原始命令元组序列，每个元组包含数据项名称和通道列表或单个通道字符串:
                - data_name: 数据项名称
                - channels: 通道列表或单个通道字符串
            
        Returns:
            cmd_keys: 命令键列表
            final_commands: 发送命令列表
        """
        pass

    @abstractmethod
    def build_control_command(
        self,
        origin_commands: Sequence[tuple[str, Union[str, list[str]], Any]]
    ) -> tuple[list[str], list[Any]]:
        """构建控制命令
        
        Args:
            origin_commands: 控制命令元组序列，每个元组包含:
                - control_name: 控制项名称
                - channels: 通道列表或单个通道字符串
                - value: 要设置的值
            
        Returns:
            cmd_keys: 命令键列表
            final_commands: 发送命令列表
        """
        pass

    def _get_command_priority(self, data_name: str) -> list[str]:
        """获取命令构建优先级: get_all_xxx > get_xxx > get_default"""
        priority:list[str] = []
        
        priority.append(self.commands.get_command(data_name))
        
        return priority

    def _format_command(self, command_template: str,
                       channel: Optional[str] = None,
                       value: Optional[Any] = None) -> str:
        """格式化命令模板"""
        formatted = command_template
        
        if channel:
            formatted = formatted.replace("{channel}", channel)
        
        if value is not None:
            formatted = formatted.replace("{value}", str(value))
        
        if self.address:
            formatted = formatted.replace("{address}", self.address)
        
        return formatted

    def _get_data_definition(
        self,
        data_name: str
    ) -> DataDefinition:
        """获取数据定义"""
        try:
            for data_dict in self.protocol_config.data.values():
                if data_name in data_dict:
                    return data_dict[data_name]
            raise KeyError
        except KeyError:
            raise ValueError(
                f"No data definition found for {data_name}"
            )

    def _get_command_template(
        self,
        command_type: str
    ) -> str:
        """获取命令模板"""
        # 检查特定命令
        if hasattr(self.protocol_config.command, command_type):
            return getattr(self.protocol_config.command, command_type)
        
        # 检查默认命令
        if self.protocol_config.command.get_default:
            return self.protocol_config.command.get_default
            
        raise ValueError(
            f"No command template found for {command_type} "
            f"and no default command defined"
        )

    def _build_protocol_packet(
        self,
        commands: list[str]
    ) -> list[str]:
        """构建协议报文"""
        proto = self.protocol_config.protocols
        
        for command in commands:
            # 处理地址占位符
            if "{address}" in proto.send and hasattr(self.protocol_config, "address"):
                if self.address is None:
                    raise ValueError("Address is required for this protocol")
                command = command.replace("{address}", str(self.address))
        
        return commands

    def _validate_control_value(
        self,
        ctrl_def: ControlDefinition,
        value: Union[float, int, str]
    ):
        """验证控制值"""
        if ctrl_def.enum:
            enum_mapping = self.protocol_config.enums.get(ctrl_def.enum, {})
            if str(value) not in enum_mapping and value not in enum_mapping.values():
                raise ValueError(
                    f"Value {value} not in enum {ctrl_def.enum}. "
                    f"Valid values: {list(enum_mapping.values())}"
                )
        
        if isinstance(value, (int, float)):
            if ctrl_def.min is not None and value < ctrl_def.min:
                raise ValueError(f"Value {value} < min {ctrl_def.min}")
            if ctrl_def.max is not None and value > ctrl_def.max:
                raise ValueError(f"Value {value} > max {ctrl_def.max}")

    def _format_control_value(
        self,
        ctrl_def: ControlDefinition,
        value: Union[float, int, str]
    ) -> str:
        """格式化控制值"""
        if ctrl_def.enum:
            # 如果是枚举值，转换为协议需要的格式
            enum_mapping = self.protocol_config.enums[ctrl_def.enum]
            if value in enum_mapping.values():
                # 反向查找键
                for k, v in enum_mapping.items():
                    if v == value:
                        return k
            return str(value)
        
        # 数值类型处理
        if ctrl_def.type == 'int':
            return str(int(value))
        elif ctrl_def.type == 'float':
            return f"{float(value):.6f}".rstrip('0').rstrip('.')
        
        return str(value)

    def check_alarm_conditions(
        self,
        data_name: str,
        value: Union[float, int]
    ) -> Optional[str]:
        """检查报警条件"""
        data_def = self._get_data_definition(data_name)
        
        if data_def.max is not None and value > data_def.max:
            return "high"
        if data_def.min is not None and value < data_def.min:
            return "low"
        
        return None

    def cal_check(self, cmd:bytes, verify:str)->Optional[bytes]:
        """计算校验码"""
        from ....utils.verify import (calculate_checksum,
                                          calculate_crc16,
                                          calculate_crc32,
                                          calculate_lrc,
                                          calculate_crc16_ccitt)
    
        match verify:
            case "crc16":
                return calculate_crc16(cmd)
            case "crc32":
                return calculate_crc32(cmd)
            case "lrc":
                return calculate_lrc(cmd)
            case "checksum":
                return calculate_checksum(cmd)
            case "ccitt":
                return calculate_crc16_ccitt(cmd)
            case _:
                return None