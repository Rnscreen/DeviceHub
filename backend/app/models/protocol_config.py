"""
协议配置的类型定义
"""
# backend/app/models/protocol_config.py
from typing import ClassVar, Optional, Sequence, Union, Any, Literal
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
    address: int     # 寄存器地址
    registers: int = 1    # 寄存器数量
    type: Literal["bit","short","int16", "uint16", "int32", "uint32", "float", "double", "hex", "str", "short"] = "int16" # 寄存器类型
    size: int = 2 # 寄存器大小
    order: Literal["1234","4321","3412","2143","12","21","big","little"] = "12" # 字节序
    factor: float = 1.0

    @model_validator(mode="after")
    def after_validate(self) -> "ModbusRegister":
        """后处理"""
        # 处理寄存器数量
        if self.registers <= 0:
            self.registers = 1
        else:
            type_sizes = {
                'bit': 1,
                'int16': 2, 'short': 2, 'uint16': 2,
                'int32': 4, 'uint32': 4,
                'float': 4, 'double': 8,
                'hex': 2, 'str': 2,
            }
            self.size = type_sizes.get(self.type, 2)

        # 字节序后处理, 防止字节序与寄存器类型不匹配
        match self.type:
            case 'int32' | 'uint32' | 'float' | 'double':
                match self.order:
                    case "1234" | "4321" | "3412" | "2143":
                        # 四字节序不处理
                        pass
                    case "21"|"little": 
                        # 小端转化为4321
                        self.order = "4321"
                    case _: 
                        # 其他默认为1234
                        self.order = "1234"
            case 'int16' | 'uint16' | 'short':
                match self.order:
                    case "4321"|"21"|"little": 
                        # 小端转化为二字节序
                        self.order = "21"
                    case _:
                        # 其他默认为12
                        self.order = "12"
            case _: 
                self.order = "12"
                pass

        return self
    
    @field_validator("order", mode="before")
    @classmethod
    def validate_order(cls, v: Any) -> str:
        if isinstance(v, int):
            return str(v)
        return str(v) if v is not None else "big"
    
    @field_validator("factor", mode="before")
    @classmethod
    def validate_factor(cls, v: Any) -> float:
        """验证缩放因子"""
        if v == 0:
            raise ValueError("Factor is not allowed to be 0, it may make division by zero error!")
        return v
    
    @field_validator("address", mode="before")
    @classmethod
    def validate_address(cls, v: Any) -> int:
        """验证地址"""
        if v < 0:
            raise ValueError("Address is not allowed to be negative!")
        return v

class ModbusChannel(dict[str, ModbusRegister]):
    """Modbus模式通道 - 寄存器配置"""
    def __init__(self, kwargs: dict[str, Any]):
        for key, value in kwargs.items():
            self[key] = ModbusRegister(**value)
    def get_channels(self)-> dict[str,int]:
        """获取ModbusChannel的通道列表"""
        v:dict[str,int]={}
        for key,reg in self.items():
            v[key]=reg.address  
        return v

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
    type: Literal["int", "float", "str", "bool", "enum", "None"] = "str"
    enum: Optional[str] = None  # 枚举名，引用protocol.enums中的枚举
    max: Optional[float] = None
    min: Optional[float] = None
    fc: Optional[int] = None

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

    @model_validator(mode="after")
    def validate_type_enum(self) -> "ControlDefinition":
        """验证type和enum是否一致"""
        if self.enum is not None:
            self.type = "enum"
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


def what_command(data_name: str, channel: Union[str, list[str], None] = None, value: Optional[str] = 'get_only'):
    """构建命令"""
    if value == 'get_only':
        return PollCommand(data_name=data_name, channel=channel)
    else:
        if channel is None:
            channel = "main"
        if isinstance(channel, str):
            return ControlCommand(control_name=data_name, channel=channel, value=value)
        else:
            raise ValueError("channel must be a string.")
        
# 轮询命令 (data_name, channel|channel_group)
class PollCommand(BaseModel):
    """轮询命令"""
    data_name: str
    channel: Union[str, list[str], None]
    def __init__(self, data_name: str,
                 channel: Union[str, list[str], None] = None):
        super().__init__(data_name=data_name, channel=channel)
    def expand(self) -> PollCommands:
        """展开通道"""
        if self.channel is None:
            return [self]
        if isinstance(self.channel, str):
            return [self]
        elif isinstance(self.channel, list): #type: ignore
            return [PollCommand(data_name=self.data_name, channel=ch) for ch in self.channel]
        else:
            raise ValueError("channel must be a string or a list of strings.")
        
# 控制命令 (data_name, channel, value)
class ControlCommand(BaseModel):
    """控制命令"""
    data_name: str
    control_name: str = Field(alias="data_name") # data_name别名为control_name
    channel: str
    value: Optional[str]
    def __init__(self, control_name: str,
                 channel: str = "main",
                 value: Optional[str] = None):
        if value == '':
            value = None
        super().__init__(data_name=control_name, channel=channel, value=value)
class BuildCommand(BaseModel):
    """构建命令"""
    data_name: str
    channel: Union[str, list[str], None]
    value: Optional[str] = None
# 命令序列
PollCommands = Sequence[PollCommand]
ControlCommands = Sequence[ControlCommand]
BatchCommands = Sequence[PollCommand | ControlCommand]

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

    protocols: Optional[ProtocolFormat] = None
    command: Optional[ProtocolCommand] = None
    parse: Optional[dict[str, ParseResult]] = None

    @field_validator("protocols", "command", "parse", mode="before")
    @classmethod
    def validate_nullable_fields(cls, v: Any) -> Any:
        """将字符串'None'转换为Python None"""
        if v == 'None' or v is None:
            return None
        return v

    @field_validator("channels", mode="before")
    @classmethod
    def validate_channels(cls, v: dict[str, Optional[Union[str, list[str], dict[str, Any]]]]) -> ChannelConfig:
        """将字典转换为ChannelConfig实例，并自动转换Modbus通道"""
        if isinstance(v, ChannelConfig):
            return v
        if isinstance(v, dict): # type: ignore
            result: dict[str, Channel] = {}
            for category, channels in v.items(): 
                if isinstance(channels, str):
                    result[category] = channels
                elif isinstance(channels, list):
                    result[category] = channels
                elif isinstance(channels, dict): # type: ignore
                    # 将dict转换为ModbusChannel
                    result[category] = ModbusChannel(channels)
                else:
                    raise ValueError(f"通道{category}中包含未知类型数据")
            return ChannelConfig(result)
        raise ValueError("channels必须是字典或ChannelConfig实例")

    @field_validator("enums", mode="before")
    @classmethod
    def validate_enums(cls, v: dict[str, Any]) -> Enums:
        """将整型、浮点型枚举键转换为字符串"""
        result: Enums = {}
        for group_name, enum_def in v.items():
            if isinstance(enum_def, dict):
                converted:EnumDefinition = {}

                for k, val in enum_def.items(): # type: ignore
                    converted[str(k)] = str(val) # type: ignore

                result[str(group_name)] = converted
        return result

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
