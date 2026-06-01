from typing import Sequence
import logging
from typing import Any, Optional
from abc import ABC, abstractmethod

from ....models import ProtocolConfig, ParseResult

class IResponseParser(ABC):
    """响应解析器抽象基类"""
    
    def __init__(self, protocol_config: ProtocolConfig):
        self.protocol_config = protocol_config
        self.logger = logging.getLogger(f"{self.__class__.__name__}.{protocol_config.name}")
        self._parse_config = protocol_config.parse
    
    @abstractmethod
    def parse_poll_response(self, 
                          origin_responses: Sequence[tuple[str, Any]]
                          )-> list[tuple[str,Any]]:
        """解析轮询响应 - 支持批量解析
        
        Args:
            origin_responses: 原始响应字典，每个元素为(cmd_key, response)
                - cmd_key: 命令键
                - response: 对应的数据响应字符串
        
        Returns:解析结果列表,顺序与origin_responses中cmd_key顺序一致
            data_name: 数据项名称
            value: 解析后的值
        """
        pass

    @abstractmethod
    def parse_control_response(self,
                             origin_responses: Sequence[tuple[str, Any]]) -> tuple[Sequence[Any],list[str]]:
        """解析控制响应, 批量解析
        
        Args:
            origin_responses: 原始响应序列，每个元素为(control_key, response)
                - control_key: 命令键
                - response: 对应的数据响应字符串
        
        Returns:
            values: 解析后的值序列
            updates: 需要从poll更新的通道序列(data_name)
        """
        pass

    def _get_parse_method(self, data_name: str, command_type: str) -> Optional[ParseResult]:
        """获取解析方法配置"""
        parse_key = command_type if command_type in self._parse_config else data_name
        return self._parse_config.get(parse_key,None)

    def _execute_parse_steps(self, response: str, parse_config: dict[str, Any]) -> list[Any]:
        """执行解析步骤"""
        vars = [response]  # 初始变量
        
        if 'steps' not in parse_config:
            return vars
        
        for step in parse_config['steps']:
            method = step.get('method', '')
            params = step.get('params', {})
            
            if method == 'regex':
                vars = self._parse_regex(vars, params)
            elif method == 'split':
                vars = self._parse_split(vars, params)
            elif method == 'transform':
                vars = self._parse_transform(vars, params)
            # 可以添加更多解析方法
        
        return vars

    def _parse_regex(self, vars: list[Any], params: dict[str, Any]) -> list[Any]:
        """正则表达式解析"""
        import re
        pattern = params.get('pattern', '')
        results: list[str] = []
        
        for var in vars:
            if isinstance(var, str):
                matches = re.findall(pattern, var)
                results.extend(matches)
        
        return results

    def _parse_split(self, vars: list[Any], params: dict[str, Any]) -> list[Any]:
        """分隔符解析"""
        separator = params.get('separator', ';')
        results: list[str] = []
        
        for var in vars:
            if isinstance(var, str):
                parts = var.split(separator)
                results.extend(parts)
        
        return results

    def _parse_transform(self, vars: list[Any], params: dict[str, Any]) -> list[Any]:
        """值转换解析"""
        # 实现安全的表达式求值
        return vars

    def _extract_result(self, vars: list[Any], parse_config: dict[str, Any]) -> Any:
        """提取最终结果"""
        if 'result' in parse_config:
            # 执行result表达式
            result_expr = parse_config['result']
            # 这里实现安全的表达式求值
            return eval(result_expr, {"__builtins__": None}, {"vars": vars[0]})
        
        return vars[0] if vars else None

    def _package_results(self, vars: list[Any], parse_config: dict[str, Any], 
                        channels: list[str]) -> dict[str, Any]:
        """打包批量结果"""
        if 'package' not in parse_config:
            return {}
        
        # package_config = parse_config['package']
        # channel_group = package_config.get('channel_group', '')
        
        # 实现批量结果打包逻辑
        results: dict[str, Any] = {}
        for i, channel in enumerate(channels):
            if i < len(vars):
                results[channel] = vars[i]
        
        return results
