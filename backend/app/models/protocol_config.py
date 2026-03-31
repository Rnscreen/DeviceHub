"""
协议配置的类型定义
"""
# backend/app/models/protocol_config.py
from typing import ClassVar, Optional, Union, Any, Literal
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
import yaml
from .data_point import DataType
# 枚举定义
class ProtocolType(str, Enum):
    """
    协议类型
    """
    TCP = "tcp"
    MODBUS_TCP = "modbus_tcp"
    MODBUS_RTU = "modbus_rtu"
    SERIAL = "serial"
    USB = "usb"

class PollDataType(str, Enum):
    """
    设备数据的轮询类型可为以下几种类型
    MONITOR_FAST
    MONITOR_SLOW
    STATUS
    INFO
    STREAM
    CONTROLS
    """
    MONITOR_FAST = "monitor_fast"
    MONITOR_SLOW = "monitor_slow"
    STATUS = "status"
    INFO = "info"
    STREAM = "stream"

    @property    
    def dt(self) -> DataType:
        """获取对应的数据类型"""
        return DataType[self.name]

# 基础模型

class ModbusRegister(BaseModel):
    """Modbus寄存器配置"""
    address: int
    size: int = 2
    type: Literal["int16", "uint16", "int32", "uint32", "float", "double", "hex", "str"] = "int16"
    order: Literal["big", "little"] = "big"
    factor: float = 1.0

class ModbusChannel(dict[str, ModbusRegister]):
    """Modbus模式通道 - 寄存器配置"""
    # def get_channels(self)-> list[str]:
    #     """获取ModbusChannel的通道列表"""
    #     v:list[str]=[]
    #     for _ in self:
    #         v.extend(list(_.keys()))
    #     return v

AsciiChannel=list[str] #Modbus模式通道 - 寄存器配置"""
Channel = Union[str,AsciiChannel,ModbusChannel]
class ChannelConfig(dict[str,Channel]):
    """通道配置"""

    @property
    def all_channels(self)-> dict[str,list[str]]:
        """获取通道列表"""
        v:dict[str,list[str]]={}
        for category, channels in self.items():
            if isinstance(channels,ModbusChannel):
                v[category]=list(channels.keys())
            elif isinstance(channels,list):
                v[category]=channels
        return v

EnumDefinition = dict[str,str]
Enums = dict[str,EnumDefinition]
class EnumKey(str):
    """枚举键"""
    def build(self, ori_value: str, enums:Enums={}):
        if ori_value.startswith("enum."):
            split = ori_value.split(".")
            if len(split) != 3:
                raise ValueError(f"枚举键{ori_value}格式错误")
            _, group_name, key = split
            if group_name not in enums:
                raise ValueError(f"枚举组{group_name}不存在")
            if key not in enums[group_name]:
                raise ValueError(f"枚举键{key}不存在")
            self = enums[group_name][key]
            return self
        else:
            raise ValueError(f"枚举键{ori_value}格式错误")


# 数据定义
class DataDefinition(BaseModel):
    """数据项定义基类"""
    description: str
    channel_group: str = "main"
    channel: Optional[str] = Field(default=None, validation_alias="channel")
    type: Literal["int", "float", "str", "bool", None] = "str"
    max: Optional[float] = None
    min: Optional[float] = None

    @field_validator("channel", mode="before")
    @classmethod
    def resolve_channel(cls, v: Optional[str], info: Any) -> Optional[str]:
        """支持使用 channel 作为 channel_group 的别名"""
        return v

    @model_validator(mode="after")
    def resolve_channel_group(self) -> "DataDefinition":
        """如果 channel_group 是默认值但存在 channel 值，则使用 channel 值"""
        if self.channel is not None:
            self.channel_group = self.channel
        return self

    @model_validator(mode="after")
    def validate_limits(self) -> "DataDefinition":
        """验证最大最小值"""
        if self.max is not None and self.min is not None and self.max <= self.min:
            raise ValueError("max必须大于min")
        return self

# 控制定义
class ControlDefinition(DataDefinition):
    """控制定义"""
    channel_group: str = "main"
    max: Optional[float] = None
    min: Optional[float] = None
    enum: Optional[str] = None  # 枚举名，引用protocol.enums中的枚举
    type: Literal["int", "float", "str", "bool", None] = "float"

    @model_validator(mode="after")
    def validate_type_enum(self) -> "ControlDefinition":
        """验证type和enum互斥"""
        if self.enum is not None:
            self.type = None
        return self

# 解析步骤
ParseType = Literal["regex", "split", "calc", "map", "custom", "transform", "exact"]
class ParseStep(BaseModel):
    """解析步骤"""
    method: ParseType
    params: dict[str, Any]

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        """
        选择解析步骤使用的方法
        """
        valid_methods = ParseType.__args__
        if v not in valid_methods:
            raise ValueError(f'method必须是: {valid_methods}')
        return v

# Package配置
class PackageConfig(BaseModel):
    """Package块配置定义"""
    channel_group: str
    data_source: Literal["sequential", "interleaved", "custom"] = "sequential"
    
    @field_validator("channel_group")
    @classmethod
    def validate_channel_group(cls, v: str) -> str:
        """验证通道组名称格式"""
        if not v or not v.strip():
            raise ValueError("channel_group不能为空")
        return v.strip()

class ParseResult(BaseModel):
    """解析结果定义"""
    steps: list[ParseStep] = Field(min_length=1)
    result: Optional[str] = None
    package: Optional[PackageConfig] = None
    update: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_package(self) -> "ParseResult":
        """验证result和package互斥"""
        if self.result is not None and self.package is not None:
            raise ValueError("result和package不能同时设置")
        if self.result is None and self.package is None:
            # 对于controls，允许没有result（只验证update）
            if not self.update:
                raise ValueError("必须设置result或package")
        return self


# 通信协议
class ProtocolFormat(BaseModel):
    """通信格式定义"""
    multisend: bool = False
    send: str
    response: str
    send_terminator: str = "\r\n"
    recv_terminator: str = "\r\n"
    send_split: str = "\r\n"
    recv_split: str = "\r\n"
    error: Optional[str] = None
    verify: Optional[Union[Literal["crc16", "crc32", "lrc", "checksum", "ccitt"],str]] = None  # 支持字符串或验证函数

    @field_validator("send")
    @classmethod
    def validate_send(cls, v: str) -> str:
        """验证模板字符串格式"""
        # 检查必要的占位符
        if "{command}" not in v:
            raise ValueError("必须包含{command}占位符")
        return v
    
    @field_validator("response")
    @classmethod
    def validate_response(cls, v: str) -> str:
        """验证模板字符串格式"""
        # 检查必要的占位符
        if "{response" not in v:
            raise ValueError("必须包含{response}/{response_data}占位符")
        return v
    

class ProtocolCommand(BaseModel):
    """命令定义"""
    get_default: Optional[str] = None
    # 支持任意自定义命令
    model_config = {"extra": "allow"}

    def get_command(self, data_name: str) -> str:
        """获取命令模板"""
        # 优先级: get_all_xxx > get_xxx > get_default
        custom_cmd = (getattr(self, f"get_all_{data_name}", None)
                    or getattr(self, f"get_{data_name}", None)
                    or self.get_default
                    )
        if not custom_cmd:
            raise ValueError(f"未定义命令模板: get_all_{data_name}, get_{data_name}, get_default")
        return custom_cmd
    def get_control_command(self, control_name: str) -> Optional[str]:
        """获取控制命令模板"""
        return getattr(self, f"set_{control_name}", None)
    def get_cmd_key(self, data_name: str) -> str:
        """获取命令键"""
        return (f"get_all_{data_name}" if hasattr(self, f"get_all_{data_name}")
                    else f"get_{data_name}" if hasattr(self, f"get_{data_name}")
                    else "get_default"
                    )

# 主协议配置
class ProtocolConfig(BaseModel):
    """协议配置主模型"""

    model_config = {"arbitrary_types_allowed": True}
    
    name: str
    version: str
    device_type: str
    protocol_type: ProtocolType

    channels: ChannelConfig
    enums: Enums = Field(default_factory=Enums)

    data: dict[PollDataType, dict[str, DataDefinition]]
    controls: dict[str, ControlDefinition]

    protocols: ProtocolFormat
    command: ProtocolCommand
    parse: dict[str, ParseResult]

    @field_validator("channels", mode="before")
    @classmethod
    def validate_channels(cls, v: Any) -> ChannelConfig:
        """将字典转换为ChannelConfig实例"""
        if isinstance(v, ChannelConfig):
            return v
        if isinstance(v, dict):
            return ChannelConfig(v) # type: ignore
        raise ValueError("channels必须是字典或ChannelConfig实例")

    # 表达式引擎占位符
    EXPRESSION_VARS: ClassVar[dict[str, str]] = {
        "response": "原始响应数据",
        "data": "协议缓存数据",
        "enum": "枚举映射"
    }

    @field_validator("version")
    @classmethod
    def validate_version_format(cls, v:str) -> str:
        """
        版本信息验证
        """
        if not v.startswith("v"):
            return f"v{v}"
        return v

    @model_validator(mode="after")
    def validate_data_channels(self) -> "ProtocolConfig":
        """验证数据项引用的通道存在"""
        all_channel_groups = set(self.channels.keys())

        # 检查data中的通道引用
        for data_type, data_dict in self.data.items():
            for data_name, data_def in data_dict.items():
                if data_def.channel_group not in all_channel_groups:
                    raise ValueError(f"数据类型{data_type}.{data_name}引用不存在的通道组: {data_def.channel_group}")

        # 检查controls中的通道引用
        for ctrl_name, ctrl_def in self.controls.items():
            if ctrl_def.channel_group not in all_channel_groups:
                raise ValueError(f"控制{ctrl_name}引用不存在的通道组: {ctrl_def.channel_group}")

        return self

    @classmethod
    def from_yaml(cls, yaml_path: str) -> "ProtocolConfig":
        """从YAML文件加载"""
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def get_enum_mapping(self, enum_name: str) -> dict[str, str]:
        """获取枚举映射"""
        return self.enums.get(enum_name, {})

    # def validate_expression(self, expr: str) -> bool:
    #     """验证表达式语法 - 使用simpleeval"""
    #     # 这里可以集成simpleeval的安全检查
    #     # 暂时返回True，实际实现时需添加
    #     return True
