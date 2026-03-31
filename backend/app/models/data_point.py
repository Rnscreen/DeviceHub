from datetime import timezone
"""
定义缓存|轮询|广播的数据类型
"""
# /backend/app/models/data_point.py
from typing import  Any, Optional, Union
from enum import Enum
from datetime import datetime
from pydantic import BaseModel, Field

class DataType(str, Enum):
    """数据具有以下几种类型
    MONITOR
    STREAM
    STATUS
    INFO
    """
    MONITOR = "monitor"
    MONITOR_FAST= MONITOR
    MONITOR_SLOW= MONITOR
    STREAM = "stream"
    STATUS = "status"
    INFO = "info"

class DataCategory:
    """数据类别 - 动态通道管理"""

    def __init__(self, data_type: DataType, category: str,
                channels: Optional[dict[str, list[str]]] = None):
        self.data_type = data_type
        self.category = category
        self._channels: dict[str, Optional[Union[float, int, str, bool, None]]] = {}

        # 初始化定义的通道
        if channels:
            for ch in channels:
                self._channels[ch] = None

    def __getitem__(self, channel: str) -> Optional[Union[float, int, str]]:
        """通道访问: category['A']"""
        return self._channels.get(channel)

    def __setitem__(self, channel: str, value: Optional[Union[float, int, str]]):
        """设置通道值"""
        self._channels[channel] = value

    def get(self, channel: str, default:Union[None,str]=None):
        """安全获取"""
        return self._channels.get(channel, default)

    def set_all(self, values: dict[str, Any])->None:
        """批量设置通道值"""
        self._channels.update(values)

    def get_all(self) -> dict[str, Any]:
        """获取所有通道值(安全)"""
        return {k: v for k, v in self._channels.items() if v is not None}

    def ensure_channel(self, channel: str):
        """确保通道存在(动态添加)"""
        if channel not in self._channels:
            self._channels[channel] = None

class DataTypeLayer:
    """数据类型层 - 管理多个category"""
    def __init__(self, data_type: DataType):
        self.data_type = data_type
        self._categories: dict[str, DataCategory] = {}

    def update(self, layer:DataTypeLayer)->None:
        """更新DataTypeLayer(融合)"""
        if layer.data_type != self.data_type:
            raise ValueError(
                f"Cannot update {self.data_type.value} layer with "
                f"{layer.data_type.value} layer"
            )
        self._categories = self._categories|layer._categories  # 就地合并
        
    def add_category(self, category:str, data:DataCategory)->None:
        """更新DataTypeLayer(增加单类)"""
        self._categories.update({category:data})

    def get_by_category(self,category:str)->Optional[DataCategory]:
        """获取categorys"""
        return self._categories.get(category)

    def __getitem__(self, category: str) -> DataCategory:
        """获取category: data_type['数据类型']"""
        if category not in self._categories:
            # 动态创建但通道未初始化
            self._categories[category] = DataCategory(self.data_type, category)
        return self._categories[category]

    def get_category(self, category: str,
                    channels: Optional[dict[str, list[str]]] = None) -> DataCategory:
        """获取或创建带通道的category"""
        if category not in self._categories:
            self._categories[category] = DataCategory(self.data_type, category, channels)
        return self._categories[category]

    def get_categoris(self)->dict[str,DataCategory]:
        """获取所有category"""
        return self._categories
    
    def get_all(self) -> dict[str, dict[str, Any]]:
        """获取该类型下所有数据"""
        return {
            category: cat.get_all()
            for category, cat in self._categories.items()
        }

class DataFrame(BaseModel):
    """数据帧 - 顶层容器"""
    
    model_config = {"arbitrary_types_allowed": True}
    
    id: Optional[str] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # 数据层
    monitor: Optional[DataTypeLayer] = None
    stream: Optional[DataTypeLayer] = None
    status: Optional[DataTypeLayer] = None
    info: Optional[DataTypeLayer] = None
    
    def __init__(self, **data:Any):
        # 初始化各层
        super().__init__(**data)
        self.monitor = DataTypeLayer(DataType.MONITOR)
        self.stream = DataTypeLayer(DataType.STREAM)
        self.status = DataTypeLayer(DataType.STATUS)
        self.info = DataTypeLayer(DataType.INFO)

    def __getitem__(self, data_type: DataType) -> DataTypeLayer:
        """获取数据类型层"""
        return getattr(self,data_type)
    
    def __setitem__(self, data_type: DataType, new_data: DataTypeLayer):
        """设置数据类型层"""
        setattr(self,data_type, new_data)
    
    def add_to_layer(self, data_type:DataType, new_data: DataTypeLayer):
        self[data_type].update(new_data)

    def get_category(self, data_type: DataType, category: str) -> DataCategory:
        """获取数据类别"""
        return self[data_type][category]

    def get_value(self, data_type: DataType, category: str, channel: str) -> Any:
        """获取具体值"""
        return self.get_category(data_type, category)[channel]

    def set_value(self, data_type: DataType, category: str, channel: str,
                  value: Union[float, int, str, None]):
        """设置值"""
        self.get_category(data_type, category)[channel] = value

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result:dict[str, Any] = {
            "id": self.id,
            "timestamp": self.timestamp,
        }
        for data_type in DataType:
            layer = self[data_type].get_all()
            if layer != {}:
                result.update({
                    data_type.value: layer
                })
        return result
    
    def to_flat_dict(self) -> dict[str, Any]:
        """转换为扁平字典"""
        result:dict[str, Any] = {
            "id": self.id,
            "timestamp": self.timestamp,
            "data": {}
        }
        for data_type in DataType:
            layer = self[data_type].get_all()
            if layer != {}:
                result["data"].update(layer)
        return result

    def to_compact(self, data_type: Optional[DataType] = None) -> dict[str, Any]:
        """紧凑格式 - 用于传输"""
        if data_type:
            return {
                "timestamp": self.timestamp,
                "data_type": data_type.value,
                "data": self[data_type].get_all()
            }
        return self.to_dict()

    def update_from_dict(self, data_dict: dict[DataType, dict[str,dict[str,Any]]])->None:
        """从字典更新"""
        for data_type_str, categories in data_dict.items():
            for category, channels in categories.items():
                cat_obj = self.get_category(
                    data_type_str,
                    category
                )
                cat_obj.set_all(channels)
