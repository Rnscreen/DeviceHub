# app/protocols/manager.py
"""
协议管理器 - 根据协议类型创建对应的协议类实例
"""
from .base import IDeviceProtocol # type: ignore
from .factory import ProtocolFactory # type: ignore

protocol_factory = ProtocolFactory()
