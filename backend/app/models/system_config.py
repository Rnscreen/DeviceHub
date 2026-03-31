# backend/app/config.py
from typing import Any, Callable, Optional
import logging
from pathlib import Path
from pydantic import Field, computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import yaml
from .device_config import DeviceConfig, DeviceHubConfig

logger = logging.getLogger(__name__)

# 子模型定义
class ServerConfig(BaseSettings):
    """服务器配置"""
    host: str = Field(default="0.0.0.0", description="绑定主机地址")
    port: int = Field(default=8000, description="绑定端口")

class SecurityConfig(BaseSettings):
    """安全配置"""
    cors_origins: list[str] = Field(default=["http://localhost:3000"], description="CORS允许的源")

class LoggingConfig(BaseSettings):
    """日志配置"""
    level: str = Field(default="INFO", description="日志级别")

class PollingConfig(BaseSettings):
    """轮询配置"""
    interval: float = Field(default=1.0, description="默认轮询间隔(秒)")

class DatabaseConfig(BaseSettings):
    """数据库配置"""
    type: str = Field(default="sqlite", description="数据库类型")
    sqlite_path: str = Field(default="device_data.db", description="SQLite数据库路径")

class MonitoringConfig(BaseSettings):
    """监控配置"""
    polling: PollingConfig = Field(default_factory=PollingConfig)

class SystemConfig(BaseSettings):
    """系统配置"""
    server: ServerConfig = Field(default_factory=ServerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    @classmethod
    def load(cls, config: dict[str, Any]) -> 'SystemConfig':
        """从字典加载配置"""
        return cls(config) # type: ignore

class Settings(BaseSettings):
    """应用主配置"""
    # 基本配置（从环境变量读取）
    APP_NAME: str = Field(default="DeviceHub", description="应用名称")
    DEBUG: bool = Field(default=False, description="调试模式")

    # 配置文件路径（相对于项目根目录）
    ROOT_PATH: Path = Path(str(Path(__file__))[:str(Path(__file__)).find('backend')]) #"项目根目录路径"
    CONFIG_PATH: Path = Path(ROOT_PATH / "config") 
    SYSTEM_CONFIG_PATH: Path = Path(CONFIG_PATH / "system.yaml")
    DEVICE_CONFIG_PATH: Path = Path(CONFIG_PATH / "devices.yaml")
    # 动态加载的配置
    _system_config: Optional[SystemConfig] = None
    _devicehub_config: Optional[DeviceHubConfig] = None
    device_configs: dict[str, DeviceConfig] = Field(
        default_factory=dict, description="设备配置字典")
    
    # 热重载回调函数（不使用下划线前缀以兼容 Pydantic）
    reload_callbacks: list[Callable[[str], None]] = Field(
        default_factory=list[Callable[[str], None]], description="配置重载回调函数列表")
    hot_reload_enabled: bool = Field(default=False, description="是否启用热重载")

    model_config = SettingsConfigDict(
        env_file=f"{str(ROOT_PATH)}/backend/.env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        arbitrary_types_allowed=True,
        validate_assignment=True,
    )

    @model_validator(mode='after')
    def load_config_files(self) -> 'Settings':
        """验证后加载配置文件"""
        self._load_configs()
        return self

    def _load_configs(self) -> None:
        """加载所有配置文件"""
        # 获取项目根目录
        # 加载系统配置
        if self._system_config is None:
            try:
                if self.SYSTEM_CONFIG_PATH.exists():
                    with open(self.SYSTEM_CONFIG_PATH, 'r', encoding='utf-8') as f:
                        yaml_data = yaml.safe_load(f)
                        self._system_config = SystemConfig.load(yaml_data)
                else:
                    self._system_config = SystemConfig()
                    logger.warning(f"⚠️ 系统配置文件不存在: {self.SYSTEM_CONFIG_PATH}")
            except Exception as e:
                logger.error(f"加载系统配置失败: {e}")
                self._system_config = SystemConfig()

        # 加载设备配置
        if self._devicehub_config is None:
            try:
                if self.DEVICE_CONFIG_PATH.exists():
                    self._devicehub_config = DeviceHubConfig().from_yaml(self.DEVICE_CONFIG_PATH)
                    self.device_configs = self._devicehub_config.devices
                else:
                    logger.warning(f"⚠️ 设备配置文件不存在: {self.DEVICE_CONFIG_PATH}") 
                    return
            except Exception as e:
                logger.error(f"加载设备配置失败: {e}")
                return

    @computed_field
    @property
    def HOST(self) -> str:
        """服务器主机地址"""
        return self._system_config.server.host if self._system_config else "0.0.0.0"

    @computed_field
    @property
    def PORT(self) -> int:
        """服务器端口"""
        return self._system_config.server.port if self._system_config else 8000

    @computed_field
    @property
    def CORS_ORIGINS(self) -> list[str]:
        """CORS允许的源"""
        return self._system_config.security.cors_origins if self._system_config else ["http://localhost:3000"]

    @computed_field
    @property
    def LOG_LEVEL(self) -> str:
        """日志级别"""
        return self._system_config.logging.level if self._system_config else "INFO"

    @computed_field
    @property
    def POLLING_INTERVAL(self) -> float:
        """轮询间隔"""
        return self._system_config.monitoring.polling.interval if self._system_config else 1.0

    @computed_field
    @property
    def DATABASE_TYPE(self) -> str:
        """数据库类型"""
        return self._system_config.database.type if self._system_config else "sqlite"

    @computed_field
    @property
    def SQLITE_PATH(self) -> str:
        """SQLite数据库路径"""
        return self._system_config.database.sqlite_path if self._system_config else "device_data.db"

    @property
    def system_config(self) -> SystemConfig:
        """获取系统配置"""
        if self._system_config is None:
            self._load_configs()
        return self._system_config or SystemConfig()

    @property
    def devicehub_config(self) -> DeviceHubConfig:
        """获取设备配置"""
        if self._devicehub_config is None:
            self._load_configs()
        return self._devicehub_config or DeviceHubConfig()
    
    def get_device_config(self,device_id:str) -> Optional[DeviceConfig]:
        """获取指定设备配置"""
        return self.device_configs.get(device_id, None)
    
    def reload_configs(self) -> None:
        """重新加载配置文件"""
        self._load_configs()
        logger.info("✅ 配置文件已重新加载")
        
        # 触发所有回调函数
        for callback in self.reload_callbacks:
            try:
                callback("config_reloaded")
            except Exception as e:
                logger.error(f"配置重载回调执行失败: {e}")
    
    def register_reload_callback(self, callback: Callable[[str], None]) -> None:
        """注册配置重载回调函数
        
        Args:
            callback: 回调函数，接收一个参数（变化类型）
        """
        if callback not in self.reload_callbacks:
            self.reload_callbacks.append(callback)
            logger.info(f"已注册配置重载回调: {callback.__name__}")
    
    def _on_config_changed(self, file_path: str) -> None:
        """配置文件变化时的处理函数
        
        Args:
            file_path: 变化的文件路径
        """
        file_path_obj = Path(file_path)
        
        if file_path_obj == self.SYSTEM_CONFIG_PATH:
            logger.info(f"检测到 system.yaml 变化，正在重启...")
            # 重启应用
            import os
            import sys
            os.execv(sys.executable, [sys.executable] + sys.argv)
            
            
        elif file_path_obj == self.DEVICE_CONFIG_PATH:
            logger.info(f"检测到 devices.yaml 变化，重新加载...")
            self._devicehub_config = None
            self._load_configs()
            for callback in self.reload_callbacks:
                try:
                    callback("device_config_changed")
                    # 重启poll服务
                    from ..services import polling_service
                    polling_service.restart_polling_sync()
                except Exception as e:
                    logger.error(f"配置重载回调执行失败: {e}")
            logger.info("✅ devices.yaml 已重新加载")
    
    def enable_hot_reload(self) -> None:
        """启用配置文件热重载"""
        if self.hot_reload_enabled:
            logger.warning("热重载已启用")
            return
            
        try:
            from ..services import file_watcher
                        
            # 监听系统配置文件
            file_watcher.watch_file(self.SYSTEM_CONFIG_PATH.as_posix(), self._on_config_changed)
            
            # 监听设备配置文件
            file_watcher.watch_file(self.DEVICE_CONFIG_PATH.as_posix(), self._on_config_changed)
            
            self.hot_reload_enabled = True
            logger.info("✅ 配置文件热重载已启用")
            
        except ImportError:
            logger.error("无法导入 file_watcher，热重载功能不可用")
        except Exception as e:
            logger.error(f"启用热重载失败: {e}")
    
    def disable_hot_reload(self) -> None:
        """禁用配置文件热重载"""
        self.hot_reload_enabled = False
        logger.info("配置文件热重载已禁用")

settings = Settings()
