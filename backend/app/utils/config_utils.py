"""
配置工具
"""
# backend/app/utils/config_utils.py
from pathlib import Path
from typing import Dict, Any, Optional
import logging
import yaml
from ..models.system_config import settings

logger = logging.getLogger(__name__)

def save_yaml_config(config_data: Dict[str, Any], file_path: Path) -> None:
    """
    保存配置到YAML文件
    
    Args:
        config_data: 配置数据
        file_path: 文件路径
    """
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, allow_unicode=True, sort_keys=False, indent=2)
        
        logger.info(f"配置已保存到: {file_path}")
    except Exception as e:
        logger.error(f"保存配置失败: {e}")

def load_yaml_config(file_path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    从YAML文件加载配置
    
    Args:
        file_path: 文件路径
        default: 默认配置
    
    Returns:
        配置字典
    """
    if not file_path.exists():
        logger.warning(f"配置文件不存在: {file_path}")
        return default or {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config:dict[str,dict[str,Any]] = yaml.safe_load(f) or {}
        return config
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        return default or {}

def save_device_config(config_data: Dict[str, Any], path: Optional[Path] = None) -> None:
    """保存设备配置到YAML文件"""
    if path is None:
        # 获取项目根目录
        project_root = Path(__file__).parent.parent.parent
        path = project_root / settings.DEVICE_CONFIG_PATH

    save_yaml_config(config_data, path)
