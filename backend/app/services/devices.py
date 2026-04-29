# backend/app/services/device_manager.py
"""
设备管理器
"""
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Any

import asyncio
import logging
from datetime import datetime, timezone

from ..models.data_point import DataFrame
from ..models.device_config import DeviceConfig
from ..models.protocol_config import ProtocolConfig, BatchCommands, PollCommand, ControlCommand, what_command
from .protocols import IDeviceProtocol, protocol_factory

from ..models import settings

if TYPE_CHECKING:
    from .sqlite import SQLiteService
    from .websocket import WebSocketManager

logger = logging.getLogger(__name__)

class DeviceManager:
    """设备管理器"""
    
    # 类常量
    CONFIG_DIR = settings.CONFIG_PATH
    PROTOCOLS_DIR = CONFIG_DIR/"protocols"
    
    @property
    def device_configs(self) -> dict[str, DeviceConfig]:
        """设备配置字典"""
        return settings.device_configs
    
    @property
    def protocol_configs(self) -> dict[str, ProtocolConfig]:
        """协议配置字典"""
        return settings.protocol_configs

    def __init__(self, db_service: "SQLiteService | None" = None, ws_service: "WebSocketManager | None" = None) -> None:
        self.db_service = db_service
        self.ws_service = ws_service
        self.loop = asyncio.get_event_loop()
        self.devices: dict[str, IDeviceProtocol] = {}
        
        # 运行时状态
        self.last_poll_times: dict[str, datetime] = {}
        self.device_status: dict[str, dict[str, datetime | str | bool | None]] = {}
        
        # 热重载状态
        self.hot_reload_enabled: bool = False

        self.device_functions: dict[str, dict[str, object]] = {}
        # 缓存设备函数
        """格式为
        {
            "device_id": device_id,
            "device_type": protocol.device_type,
            "channels": protocol.channels,
            "enums": protocol.enums,
            "enabled_channels": enabled_channels,
            "functions": 
                "name": func_name,
                "doc": description,
                "params": params,
                "is_get": is_get,
                "is_async": True
        }
        """

    def _load_protocol_config(self, protocol_name: str) -> ProtocolConfig | None:
        """加载协议配置"""
        # 检查缓存
        if protocol_name in self.protocol_configs:
            return self.protocol_configs[protocol_name]
            
        protocol_path = self.PROTOCOLS_DIR / f"{protocol_name}.yaml"
        try:
            if not protocol_path.exists():
                logger.error("协议配置文件不存在: %s", protocol_path)
                return None
                
            protocol_config = ProtocolConfig.from_yaml(str(protocol_path))
            # 缓存协议配置
            self.protocol_configs[protocol_name] = protocol_config
            return protocol_config
        except Exception as e:
            logger.error("加载协议配置失败 %s: %s", protocol_name, e)
            return None

    async def initialize_devices(self) -> None:
        """初始化所有设备"""
        success_count = 0
        
        for device_id, device_config in self.device_configs.items():
            if not device_config.enabled:
                logger.info("跳过禁用设备: %s", device_id)
                continue
            
            # 确定协议名称
            protocol_name = (
                f"{device_config.model}_{device_config.version}".lower() 
                if device_config.version 
                else device_config.model.lower()
            )
            
            protocol_config = self._load_protocol_config(protocol_name)
            if not protocol_config:
                logger.error("设备 %s 协议配置加载失败: %s", device_id, protocol_name)
                continue
            
            # 创建设备实例
            try:
                if device_id in self.devices:
                    continue

                device: IDeviceProtocol = protocol_factory.create_protocol(device_id)
                self.devices[device_id] = device
                
                # 初始化状态
                self.device_status[device_id] = {
                    "connected": False,
                    "last_seen": None,
                    "error": None
                }
                
                logger.info("添加设备: %s", device_id)
                success_count += 1
                
                # 异步连接设备
                asyncio.create_task(self._connect_device_async(device_id))
                
            except Exception as e:
                logger.error("创建设备实例失败 %s: %s", device_id, e)
                continue
        
        logger.info("设备初始化完成: %d/%d 成功", success_count, len(self.device_configs))

    async def _connect_device_async(self, device_id: str) -> None:
        """异步连接设备"""
        try:
            success = await self.connect_device(device_id)
            if success:
                logger.info("设备 %s 连接成功", device_id)
            else:
                logger.warning("设备 %s 连接失败，将尝试后台重连", device_id)
        except Exception as e:
            logger.error("设备 %s 连接异常: %s", device_id, e)

    def add_device(self, device_config: DeviceConfig) -> bool:
        """添加设备"""
        device_id = device_config.id
        
        try:
            protocol_name = (
                f"{device_config.model}_{device_config.version}".lower()
                if device_config.version
                else device_config.model.lower()
            )
            
            protocol_config = self._load_protocol_config(protocol_name)
            if not protocol_config:
                return False
                
            if device_id in self.devices:
                return False

            device: IDeviceProtocol = protocol_factory.create_protocol(device_id)
            self.devices[device_id] = device
            
            self.device_configs[device_id] = device_config
            self.device_status[device_id] = {
                "connected": False,
                "last_seen": None,
                "error": None
            }
            
            logger.info("添加设备: %s", device_id)
            return True
            
        except Exception as e:
            logger.error("添加设备失败 %s: %s", device_id, e)
            return False

    def get_device_config(self, device_id: str) -> DeviceConfig | None:
        """获取设备配置"""
        return self.device_configs.get(device_id)

    async def connect_device(self, device_id: str) -> bool:
        """连接设备"""
        match self.devices.get(device_id):
            case None:
                logger.error("设备不存在: %s", device_id)
                return False
            case device if not device.enabled:
                self.device_status[device_id]["connected"] = False
                logger.info("设备 %s 未启用", device_id)
                return False
            case device:
                try:
                    connected = await device.connect()
                    self.device_status[device_id].update({
                        "connected": connected,
                        "error": None
                    })
                    return connected
                except Exception as e:
                    self.device_status[device_id].update({
                        "connected": False,
                        "error": str(e)
                    })
                    logger.error("连接设备异常 %s: %s", device_id, e)
                    return False

    async def disconnect_device(self, device_id: str) -> bool:
        """断开设备连接"""
        if device := self.devices.get(device_id):
            try:
                await device.disconnect()
                self.device_status[device_id]["connected"] = False
                logger.info("设备断开连接: %s", device_id)
                return True
            except Exception as e:
                logger.error("断开连接异常 %s: %s", device_id, e)
                return False
        return False

    async def poll_device(self, device_id: str) -> bool|None:
        """轮询单个设备"""
        if device_id not in self.devices:
            return None
        
        device = self.devices[device_id]
        
        # 设备重连逻辑
        if not device.connected:
            logger.info("设备 %s 未连接，尝试重连...", device_id)
            try:
                await self.connect_device(device_id)
                if not device.connected:
                    logger.warning("设备 %s 重连失败", device_id)
                    return None
            except Exception as e:
                logger.error("设备 %s 重连异常: %s", device_id, e)
                return None
        
        try:
            poll_data:DataFrame = await device.get_poll()
            current_time = datetime.now(timezone.utc)
            
            self.last_poll_times[device_id] = current_time
            self.device_status[device_id].update({
                "last_seen": current_time,
                "error": None
            })
            
            # 存储数据
            if self.db_service:
                try:
                    self.db_service.write_device_data(poll_data)
                except Exception as e:
                    logger.error("存储设备 %s 数据失败: %s", device_id, e)

            # WebSocket 广播
            if self.ws_service:
                try:
                    await self.ws_service.send_device_update(device_id=device_id, data=poll_data)
                except Exception as e:
                    logger.error("向WebSocket广播设备 %s 数据失败: %s", device_id, e)
            
            return True

        except Exception as e:
            self.device_status[device_id]["error"] = str(e)
            logger.error("轮询设备失败 %s: %s", device_id, e)

    def get_device(self, device_id: str) -> IDeviceProtocol | None:
        """获取设备实例"""
        return self.devices.get(device_id)

    def get_all_devices(self) -> dict[str, IDeviceProtocol]:
        """获取所有设备"""
        return self.devices.copy()

    def get_device_status(self, device_id: str) -> dict[str, datetime | str | bool | None] | None:
        """获取设备状态"""
        return self.device_status.get(device_id)

    def get_all_device_status(self) -> dict[str, dict[str, object]]:
        """获取所有设备状态"""
        return {
            "devices_status": {
                device_id: device.connected 
                for device_id, device in self.devices.items()
            }
        }

    def get_device_ids(self) -> list[str]:
        """获取所有设备ID"""
        return list(self.devices.keys())

    def get_all_device_configs(self) -> dict[str, DeviceConfig]:
        """获取所有设备配置"""
        return self.device_configs.copy()

    async def remove_device(self, device_id: str) -> bool:
        """移除设备"""
        if device_id in self.devices:
            await self.disconnect_device(device_id)
            del self.devices[device_id]
            del self.device_configs[device_id]
            del self.device_status[device_id]
            logger.info("移除设备: %s", device_id)
            return True
        return False

    def build_command(self, device_id: str, command: str, params: Optional[dict[str, Any]] = None
                    )-> PollCommand|ControlCommand:
        """构建设备命令"""
        # command格式固定为 get_xxx or set_xxx, 为避免xxx包含下划线，不使用_分隔, 而是切片获取xxx部分
        dataname=command[4:]
        channel = params.get("channel") if params else None

        # 区分轮询命令和控制命令
        if command.startswith("get_"):
            value = 'get_only'
        else:
            value = params.get("value") if params else None

        # 获取设备协议
        device = self.get_device(device_id)
        if device is None:
            raise ValueError(f"设备 {device_id} 不存在")
        protocol_config = device.protocol_config

        # 根据dataname从protocol_config.data中查找polldatatype
        for data_dict in protocol_config.data.values():
            if dataname in data_dict:
                # 找到数据项
                break
        else:
            if dataname in protocol_config.controls:
                # 找到控制项
                pass
            else:
                raise ValueError(f"设备 {device_id} 数据项或控制项 {dataname} 均不存在")
        
        result = what_command(dataname, channel, value)

        return result

    async def execute_device_command(self, 
                                    device_id: str,
                                    commands: BatchCommands
                                    ) -> list[dict[str, Any]]|None:
        """执行设备命令（支持单个或批量命令）
        
        Args:
            device_id: 设备ID
            commands: 命令列表或单个命令，格式为 data_name, channel, value
                - data_name: 数据项名称
                - channel: 通道名称（可选）
                - value: 要设置的值 只能在控制命令中使用
        
        Returns:
            DataFrame: 执行结果, 如果设备不存在则返回None
        """
        if not (device := self.get_device(device_id)):
            logger.error("设备 %s 不存在", device_id)
            return None

        if not device.connected:
            logger.error("设备 %s 未连接", device_id)
            return None

        try:
            results = await device.execute(commands)
            results_json:list[dict[str, Any]]=[]
            for result in results:
                # 检查是否为DataFrame类型，如果是则广播并存储
                if isinstance(result, DataFrame):
                    if self.db_service:
                        try:
                            self.db_service.write_device_data(result)
                        except Exception as e:
                            logger.error("存储设备 %s 数据失败: %s", device_id, e)

                    results_json.append(result.to_flat_dict())
                else:
                    results_json.append({"success":result})
            return results_json

        except Exception as e:
            logger.error("执行设备 %s 命令失败: %s", device_id, e)
            return None


    def get_device_functions(self, device_id: str) -> dict[str, object] | None:
        """获取设备可用函数信息"""

        # 检查设备是否存在
        if not (device := self.get_device(device_id)) or not device.protocol_config:
            return None
        
        # 检查是否已缓存
        if device_id in self.device_functions:
            return self.device_functions[device_id]
        
        # 缓存函数信息
        protocol = device.protocol_config
        enabled_channels = device.enabled_channels

        methods = {}
        
        # 处理数据获取方法
        for data_cfg in protocol.data.values():
            for field, field_cfg in data_cfg.items():
                func_name = f"get_{field}"
                if method_config := self._build_method_config(protocol, func_name, field_cfg.description, 
                                                              field_cfg.channel_group, enabled_channels, 
                                                              True, "str", None):
                    methods[func_name] = method_config
        
        # 处理控制设置方法
        for field, field_cfg in protocol.controls.items():
            func_name = f"set_{field}"

            type_input = field_cfg.type or "str"
            enum_input: str|None = field_cfg.enum

            if method_config := self._build_method_config(protocol, func_name, field_cfg.description, 
                                                          field_cfg.channel_group, enabled_channels,
                                                          False, type_input, enum_input):
                methods[func_name] = method_config

        result: dict[str, object] = {
            "device_id": device_id,
            "device_type": protocol.device_type,
            "channels": protocol.channels,
            "enums": protocol.enums,
            "enabled_channels": enabled_channels,
            "functions": methods
        }

        # 缓存结果
        self.device_functions[device_id] = result
        return result

    def _build_method_config(self, protocol: ProtocolConfig, func_name: str, description: str, channel: str,
                           enabled_channels: dict[str, list[str]], is_get: bool, 
                           type_input: str,  enum_input: str | None = None) -> dict[str, object] | None:
        """构建方法配置"""
        params: list[dict[str, object]] = []
        channel_config = protocol.channels.get(channel)
        
        # 处理通道参数（非字符串通道）
        if channel_config and not isinstance(channel_config, str):
            channel_options = enabled_channels.get(channel, [])
            if not isinstance(channel_options, str):
                param: dict[str, object] = {
                    "name": "channel",
                    "type": type_input,
                    "default": None,
                    "required": True
                }
                
                match channel_options:
                    case list():
                        param["options"] = {channel: f"CH {channel}" for channel in channel_options}

                params.append(param)
        
        # 处理设置方法的数值参数
        if not is_get:
            if type_input == "None":
                param = {
                    "name": "value",
                    "type": None, 
                    "default": None,
                    "required": False
                }
            elif type_input == "enum" and enum_input:
                param = {
                    "name": "value",
                    "type": "enum", 
                    "default": None,
                    "required": True
                }
                
                match enum_input.split('.'):
                    case ["enums", enum_name]:
                        if enum_dict := protocol.enums.get(enum_name, {}):
                            param["options"] = enum_dict

                    case ["channels", ref_channel]:
                        if ref_options := enabled_channels.get(ref_channel):
                            match ref_options:
                                case list():
                                    param["options"] = {channel: f"CH {channel}" for channel in ref_options}
                    case _:
                        pass
            else:
                param = {
                    "name": "value",
                    "type": type_input, 
                    "default": None,
                    "required": True
                }

            params.append(param)

        return {
            "name": func_name,
            "doc": description,
            "params": params,
            "is_get": is_get,
            "is_async": False # 从缓存读取，可以同步返回
        } if params or is_get else None
    
    def _on_protocol_config_changed(self, file_path: str) -> None:
        """协议配置文件变化时的处理函数（同步版本，在watchdog线程调用）"""
        # 将异步处理调度到主事件循环
        future = asyncio.run_coroutine_threadsafe(#type:ignore
            self._async_on_protocol_config_changed(file_path),
            self.loop
        ) 
        # 可以选择等待结果，但只是触发更新
        # try:
        #     future.result(timeout=10)  # 最多等待10秒
        # except TimeoutError:
        #     logger.error(f"处理配置文件 {file_path} 超时")
        # except Exception as e:
        #     logger.error(f"处理配置文件 {file_path} 失败: {e}")
    
    async def _async_on_protocol_config_changed(self, file_path: str) -> None:
        """异步处理函数（在主事件循环执行）"""
        """协议配置文件变化时的处理函数
        
        Args:
            file_path: 变化的文件路径
        """
        file_path_obj = Path(file_path)
        protocol_name = file_path_obj.stem.lower()
        
        logger.info(f"检测到协议配置变化: {protocol_name}")
        
        # 清除缓存
        if protocol_name in self.protocol_configs:
            del self.protocol_configs[protocol_name]
        
        # 清除相关设备的函数缓存
        for device_id, device in self.devices.items():
            device_protocol_name = (
                f"{device.device_config.model}_{device.device_config.version}".lower()
                if device.device_config.version
                else device.device_config.model.lower()
            )
            
            if device_protocol_name == protocol_name:
                if device_id in self.device_functions:
                    del self.device_functions[device_id]
                
                # 重新加载协议配置
                try:
                    # 前往poll所在线程，断开连接
                    await device.disconnect()
                    del self.devices[device_id]

                    device_config = self.device_configs.get(device_id)
                    newprotocol_config = self._load_protocol_config(protocol_name)
                    if device_config and newprotocol_config:
                        # 创建新的协议实例
                        device: IDeviceProtocol = protocol_factory.reload_protocol(device_id)
                        self.devices[device_id] = device
                        
                        logger.info(f"设备 {device_id} 的协议配置已更新")
                except Exception as e:
                    logger.error(f"重新加载设备 {device_id} 的协议配置失败: {e}")
        
        logger.info(f"✅ 协议配置 {protocol_name} 已重新加载")
    
    def enable_protocol_hot_reload(self) -> None:
        """启用协议配置文件热重载"""
        if self.hot_reload_enabled:
            logger.warning("协议热重载已启用")
            return
            
        try:
            from . import file_watcher
            
            # 监听 protocols 目录
            protocols_dir = str(self.PROTOCOLS_DIR)
            
            # 监听 protocols 目录
            file_watcher.watch_directory(protocols_dir, self._on_protocol_config_changed)
            
            self.hot_reload_enabled = True
            logger.info("✅ 协议配置文件热重载已启用")
            
        except ImportError:
            logger.error("无法导入 file_watcher, 热重载功能不可用")
        except Exception as e:
            logger.error(f"启用协议热重载失败: {e}")
    
    def disable_protocol_hot_reload(self) -> None:
        """禁用协议配置文件热重载"""
        self.hot_reload_enabled = False
        logger.info("协议配置文件热重载已禁用")
