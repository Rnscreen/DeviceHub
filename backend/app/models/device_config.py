"""
设备配置文件类型定义
"""
# \backend\app\models\device_config.py
from typing import Optional, Any
from pathlib import Path
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings
import yaml

class ConnectionConfig(BaseModel):
    """
    @设备配置-连接设置
    """
    host: Optional[str] = None
    port: Optional[int] = None
    serial: Optional[str] = None
    address: Optional[str] = None
    baudrate: Optional[int] = Field(default=9600)
    timeout: float = Field(default=0.4, ge=0.1)

    @property
    def is_tcp(self) -> bool:
        """
        是否为tcp协议
        """
        return bool(self.host and self.port)

    @model_validator(mode='before')
    @classmethod
    def validate_connection_type(cls, data: dict[str, Any]) -> dict[str, Any]:
        """连接类型判断"""
        host = data.get("host")
        port = data.get("port")
        serial = data.get("serial")

        if not ((host and port) or serial):
            raise ValueError("必须配置TCP(host+port)或串口(serial)")
        if (host and port) and serial:
            raise ValueError("不能同时配置TCP和串口连接")

        return data

class PollConfig(BaseModel):
    """
    设备的轮询配置
    """
    poll_interval:float = 1.0
    poll_slow:int = 5
    poll_status:int = 10
    monitor: Optional[list[str]]=None
    saver: Optional[list[str]]=None

EnabledChannels = dict[str,list[str]]

class DeviceConfig(BaseModel):
    """
    设备配置-单个设备
    """
    id: str = Field(..., min_length=1)
    name: str
    type: str
    vendor: str
    model: str
    version: str
    enabled: bool = False

    connection: ConnectionConfig

    enabled_channels: Optional[EnabledChannels] = Field(
        default_factory=EnabledChannels,
        description="从protocol配置中读取可用通道组"
    )

    poll:PollConfig

    tags: dict[str, str] = Field(default_factory=dict)
    description: str = ""

    @field_validator("version")
    @classmethod
    def validate_version_format(cls, v:str):
        """
        版本格式校验
        """
        if not v.startswith("v"):
            return f"v{v}"
        return v

    @field_validator("poll")
    @classmethod
    def validate_config_intervals(cls, v:PollConfig):
        """验证轮询次数为正整数"""
        if v.poll_slow <= 0:
            raise ValueError("poll_slow必须为正整数")
        if v.poll_status <= 0:
            raise ValueError("poll_status必须为正整数")
        return v

class DeviceGroup(BaseModel):
    """
    设备组, 包含的设备(id),以及描述
    """
    name: str
    devices: list[str]
    description: str = ""

class DeviceHubConfig(BaseSettings):
    """
    设备配置--config/devices.yaml
    """
    # 修改点1：设备字典，键为设备ID
    devices: dict[str, DeviceConfig] = {}
    groups: dict[str, DeviceGroup] = {}

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "DeviceHubConfig":
        """从yaml配置加载设备配置"""
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # 修改点2：确保每个设备配置都有正确的ID
        if "devices" in data:
            for device_id, device_config in data["devices"].items():
                device_config["id"] = device_id  # 自动填充ID字段
        
        config = cls(**data)
        config._validate_group_references()  # 新增验证
        return config

    def _validate_group_references(self) -> None:
        """验证分组中引用的设备是否存在"""
        all_device_ids = set(self.devices.keys())
        
        for group_id, group in self.groups.items():
            missing_devices = [
                device_id for device_id in group.devices 
                if device_id not in all_device_ids
            ]
            if missing_devices:
                raise ValueError(
                    f"分组 '{group_id}' 引用了不存在的设备: {missing_devices}"
                )

    def get_device(self, device_id: str) -> Optional[DeviceConfig]:
        """根据设备id获取设备配置"""
        # 修改点3：直接字典查找
        return self.devices.get(device_id)

    def get_device_by_group(self, group_id: str) -> list[DeviceConfig]:
        """获取设备组中的所有设备"""
        group = self.groups.get(group_id)
        if not group:
            return []
        
        # 修改点4：直接通过设备ID列表获取
        return [
            self.devices[device_id] 
            for device_id in group.devices 
            if device_id in self.devices
        ]
