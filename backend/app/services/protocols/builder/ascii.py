from typing import Optional, Any, Sequence, Union
import logging
import re
from ....models import ProtocolConfig, ProtocolType, ControlDefinition
from ..base.ibuilder import ICommandBuilder

class AsciiCommandBuilder(ICommandBuilder):
    def __init__(
        self,
        protocol_config: ProtocolConfig,
        address: Optional[str] = None
    ):
        super().__init__(protocol_config=protocol_config, address=address)
        self.logger = logging.getLogger(f"AsciiCommandBuilder.{protocol_config.name}")
        
        self._command_cache: dict[str, str] = {}
        self._precompile()
        self._validate_protocol_type()

    def _precompile(self):
        for data_items in self.protocol_config.data.values():
            for data_name in data_items.keys():
                if hasattr(self.protocol_config.command, f"get_all_{data_name}"):
                    self._command_cache[f"get_all_{data_name}"] = getattr(
                        self.protocol_config.command, f"get_all_{data_name}"
                    )
                elif hasattr(self.protocol_config.command, f"get_{data_name}"):
                    self._command_cache[f"get_{data_name}"] = getattr(
                        self.protocol_config.command, f"get_{data_name}"
                    )
        
        for ctrl_name in self.protocol_config.controls.keys():
            if hasattr(self.protocol_config.command, f"set_{ctrl_name}"):
                self._command_cache[f"control_{ctrl_name}"] = getattr(
                    self.protocol_config.command, f"set_{ctrl_name}"
                )

    def _validate_protocol_type(self):
        if self.protocol_config.protocol_type not in [t.value for t in ProtocolType]:
            raise ValueError(
                f"Invalid protocol type: {self.protocol_config.protocol_type}"
            )

    def _format_command(self, command_template: str,
                       channel: Optional[str] = None,
                       value: Optional[Any] = None) -> str:
        """格式化命令模板"""
        formatted = command_template
        
        if channel is not None:
            formatted = formatted.replace("{channel}", str(channel))
        
        if value is not None:
            # 兼容 value:.xf 格式, 防止精度过高导致命令过长, 导致设备解析错误
            if "{value:" in formatted:
                match = re.search(r"{value:([^}]+)}", formatted)
                if match:
                    format_spec = match.group(1)
                    # 如果value能转换为浮点数, 则格式化
                    try:
                        v = float(value)
                        formatted = formatted.replace(f"{{value:{format_spec}}}", f"{v:{format_spec}}")
                    # 如果value不能转换为浮点数, 则直接替换为字符串
                    except ValueError:
                        self.logger.warning(f"Value {value} cannot be formatted with {format_spec}, using default format")
                        formatted = formatted.replace("{value}", str(value))
            else:
                formatted = formatted.replace("{value}", str(value))
        
        if self.address:
            formatted = formatted.replace("{address}", str(self.address))
        
        return formatted

    def build_poll_command(
        self,
        origin_commands: Sequence[tuple[str, Union[str,list[str]]]]
    ) -> tuple[list[str], list[str]]:
        """
        根据原始命令元组序列构建轮询命令列表
        origin_commands 为 一个元组序列，每个元组包含数据项名称和通道列表或单个通道字符串:
            - data_name: 数据项名称
            - channels: 通道列表或单个通道字符串
        """
        commands: list[str] = []
        cmd_keys: list[str] = []
                
        for data_name, channels in origin_commands:
            try:
                cmd_template = self.protocol_config.command.get_command(data_name)
                cmd_key = self.protocol_config.command.get_cmd_key(data_name)
            except ValueError:
                self.logger.warning(f"No command template for {data_name}, skipping")
                continue
            
            if 'all' in cmd_key:
                formatted_cmd = self._format_command(cmd_template, channel='main')
                commands.append(formatted_cmd)
                cmd_keys.append(cmd_key if 'default' not in cmd_key else f"get_{data_name}")
            elif isinstance(channels, str):
                formatted_cmd = self._format_command(cmd_template, channel=channels)
                commands.append(formatted_cmd)
                cmd_keys.append(cmd_key if 'default' not in cmd_key else f"get_{data_name}")
            else:
                for ch in channels:
                    formatted_cmd = self._format_command(cmd_template, channel=ch)
                    commands.append(formatted_cmd)
                    cmd_keys.append(cmd_key if 'default' not in cmd_key else f"get_{data_name}")
            
        
        final_commands: list[str] = []
        for cmd in commands:
            send_format = self.protocol_config.protocols.send
            final_cmd = self._apply_send_format(send_format, cmd)
            final_commands.append(final_cmd)
        
        return cmd_keys, final_commands

    def build_control_command(
        self,
        origin_commands: Sequence[tuple[str, Union[str, list[str]], Any]]
    ) -> tuple[list[str], list[str]]:
        """
        构建控制命令
        
        Args:
            origin_commands: 控制命令元组序列，每个元组包含:
                - control_name: 控制项名称
                - channels: 通道列表或单个通道字符串
                - value: 要设置的值
        
        Returns:
            cmd_keys: 命令键列表
            final_commands: 发送命令列表
        """
        commands: list[str] = []
        cmd_keys: list[str] = []
        
        for control_name, channels, value in origin_commands:
            try:
                cmd_template = self.protocol_config.command.get_control_command(control_name)
                if not cmd_template:
                    raise ValueError(f"No control command template for {control_name}")
                cmd_key = f"set_{control_name}"
            except ValueError:
                self.logger.warning(f"No control command template for {control_name}, skipping")
                continue
            
            ctrl_def = self._get_control_definition(control_name)
            
            try:
                self._validate_control_value(ctrl_def, value)
            except ValueError as e:
                self.logger.warning(f"Control value validation failed for {control_name}: {e}")
                continue
            
            formatted_value = self._format_control_value(ctrl_def, value)
            
            if 'all' in cmd_key:
                formatted_cmd = self._format_command(cmd_template, channel='main')
                commands.append(formatted_cmd)
                cmd_keys.append(cmd_key if 'default' not in cmd_key else f"get_{control_name}")
            elif isinstance(channels, str):
                formatted_cmd = self._format_command(
                    cmd_template, 
                    channel=channels, 
                    value=formatted_value
                )
                commands.append(formatted_cmd)
                cmd_keys.append(cmd_key)
            else:
                for ch in channels:
                    formatted_cmd = self._format_command(
                        cmd_template, 
                        channel=ch, 
                        value=formatted_value
                    )
                    commands.append(formatted_cmd)
                    cmd_keys.append(cmd_key)
        
        final_commands: list[str] = []
        for cmd in commands:
            send_format = self.protocol_config.protocols.send
            final_cmd = self._apply_send_format(send_format, cmd)
            final_commands.append(final_cmd)
        
        return cmd_keys, final_commands
    
    def _get_control_definition(self, control_name: str) -> "ControlDefinition":
        """获取控制定义"""
        ctrl_def = self.protocol_config.controls.get(control_name)
        if ctrl_def is None:
            raise ValueError(f"No control definition found for {control_name}")
        return ctrl_def

    def _apply_send_format(self, send_format: str, command: str) -> str:
        result = send_format.replace("{command}", command)
                
        if "{address}" in result and self.address:
            result = result.replace("{address}", str(self.address))
        
        if "{verify}" in result:
            result = result.replace("{verify}", '') # 移除校验码占位符
            
            if (func:=self.protocol_config.protocols.verify):
                if (check_code_bytes:=self.cal_check(result.encode(),func)):
                    check_code: str = check_code_bytes.decode()
                else:   # 如果校验码存在且不匹配，使用eval计算自定义校验码
                    try:
                        check_code: str = eval(
                            f"lambda cmd: {func}",
                            {"cmd": result}
                        )
                    except Exception as e:
                        self.logger.error(f"Error evaluating verify function: {e}")
                        check_code = ""
            else:
                check_code = ""

            result = result+check_code

        return result