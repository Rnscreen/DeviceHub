from typing import Sequence
import re
import logging
from typing import Any, Optional, Union, Callable # type: ignore
from ....models import ProtocolConfig, ParseStep, PackageConfig
# from ..base.ihandler import IHandler
from ..base.iparser import IResponseParser

class AsciiResponseParser(IResponseParser):
    """ASCII响应解析器 - 支持预编译结构"""
    
    def __init__(self, protocol_config: ProtocolConfig):
        super().__init__(protocol_config)
        self.logger = logging.getLogger(f"AsciiResponseParser.{protocol_config.name}")
        
        # 预编译所有解析步骤
        self._compiled_parse_steps: dict[str, list[Callable[[list[str], str], list[str]]]] = {}
        self._compiled_packages: dict[str, PackageConfig] = {}
        self._compiled_results: dict[str, str] = {}
        self._compiled_updates: dict[str, str] = {}
        
        self._precompile_parse_steps()
    
    def _precompile_parse_steps(self):
        """预编译所有解析步骤"""
        for parse_name, parse_def in self._parse_config.items():
            compiled_steps: list[Callable[[list[str], str], list[str]]] = []
            
            for step in parse_def.steps:
                compiled_step: Callable[[list[str], str], list[str]] = self._compile_step(step)
                compiled_steps.append(compiled_step)
            
            self._compiled_parse_steps[parse_name] = compiled_steps
            
            # 编译package配置
            if parse_def.package:
                self._compiled_packages[parse_name] = parse_def.package
            
            # 编译result表达式
            if parse_def.result:
                self._compiled_results[parse_name] = parse_def.result
            
            # 编译update引用
            if parse_def.update:
                self._compiled_updates[parse_name] = parse_def.update

    def _compile_step(self, step: ParseStep) -> Callable[[list[str], str], list[str]]:
        """编译单个解析步骤"""
        method = step.method
        params = step.params
        
        if method == "regex":
            pattern = params.get("pattern", "")
            flags = params.get("flags", 0)
            compiled_regex = re.compile(pattern, flags)
            
            def regex_step(vars: list[str], response: str) -> list[str]:
                match = compiled_regex.search(response)
                if match:
                    return list(match.groups())
                return []
            
            return regex_step
        
        elif method == "split":
            separator = params.get("separator", ";")
            maxsplit = params.get("maxsplit", -1)
            
            def split_step(vars: list[str], response: str) -> list[str]:
                return response.split(separator, maxsplit)
            
            return split_step
        
        elif method == "transform":
            expression = params.get("expression", "")
            target = params.get("target", "all")
            
            def transform_step(vars: list[str], response: str) -> list[str]:
                return self._apply_transform(vars, expression, target)
            
            return transform_step
        
        elif method == "map":
            mapping = params.get("mapping", {})
            
            def map_step(vars: list[str], response: str) -> list[str]:
                return [mapping.get(v, v) for v in vars]
            
            return map_step
        
        else:
            raise ValueError(f"Unsupported parse method: {method}")
    
    def _apply_transform(self, vars: list[str], expression: str, target: Union[int, str]) -> list[str]:
        """应用转换表达式"""
        # 安全的表达式求值环境
        safe_globals: dict[str, Any] = {
            'float': float,
            'int': int,
            'strip': str.strip,
            'abs': abs,
            'round': round,
        }
        
        def safe_eval(expr: str, value: str) -> Any:
            try:
                local_vars = {'value': value, 'x': value}
                result = eval(expr, safe_globals, local_vars)
                return str(result)
            except Exception as e:
                self.logger.warning(f"Transform failed: {e}, keeping original value")
                return value
        
        if target == "all":
            return [safe_eval(expression, v) for v in vars]
        elif isinstance(target, int) and 0 <= target < len(vars):
            vars[target] = safe_eval(expression, vars[target])
            return vars
        else:
            return vars

    def parse_poll_response(self, 
                        origin_responses: Sequence[tuple[str, str]])->  list[tuple[str, Any]]:
        """
        解析轮询响应(以及一般的读取响应) - 支持批量解析
        args:
            origin_responses: 原始响应序列，每个元素为(cmd_key, response)
                - cmd_key: 命令键
                - response: 对应的数据响应字符串
        
        returns:
            解析结果列表,顺序与origin_responses中cmd_key顺序一致
        """
        results: list[tuple[str, Any]] = []

        for cmd_key, response in origin_responses:
            data_name = cmd_key.split("_")[-1]
            data_config = cmd_key in self._parse_config
            
            if data_config:
                # 执行解析
                parsed_data = self._execute_parse(cmd_key, response)
                
                # 将结果添加到列表中
                results.append((data_name,parsed_data))
            else:
                results.append((data_name,None))
        
        return results

    def parse_control_response(self,
                            origin_responses: Sequence[tuple[str, str]]) -> tuple[Sequence[Any],list[str]]:
        """解析控制响应, 批量解析
        
        Args:
            origin_responses: 原始响应序列，每个元素为(control_key, response)
                - control_key: 命令键
                - response: 对应的数据响应字符串
        
        Returns:
            values: 解析后的值序列
            updates: 需要从poll更新的通道序列(data_name)
        """
        values: list[Any] = []
        updates: list[str] = []
        
        for control_key, response in origin_responses:
            if control_key in self._compiled_parse_steps:
                parsed_result = self._execute_parse(control_key, response)
                values.append(parsed_result)
                
                if control_key in self._compiled_updates:
                    update_key = self._compiled_updates[control_key]
                    updates.append(update_key)
            else:
                if "OK" in response.upper() or "OK" in response:
                    values.append(True)
                elif "ERROR" in response.upper() or "ERR" in response:
                    values.append(False)
                else:
                    values.append(None)
        
        return values, updates

    def _execute_parse(self, parse_key: str, response: str) -> Union[dict[str, Any],int,float,str,bool,None]:
        """执行预编译的解析步骤"""
        steps = self._compiled_parse_steps.get(parse_key, [])
        
        if not steps:
            raise ValueError(f"No compiled steps found for {parse_key}")
        
        # 初始化vars
        vars: list[str] = [response]
        
        # 执行所有步骤
        for step_func in steps:
            try:
                vars = step_func(vars, response)
                if not vars:
                    self.logger.warning(f"Parse step returned empty vars for {parse_key}")
                    return None
            except Exception as e:
                self.logger.error(f"Parse step failed for {parse_key}: {e}")
                return None
        
        for _ in vars:
            if isinstance(_,str):
                _=_.strip()

        # 处理结果
        if parse_key in self._compiled_packages:
            result= self._package_result(parse_key, vars)
        elif parse_key in self._compiled_results:
            result= self._evaluate_result(parse_key, vars)
        else:
            result= vars[0] if vars else None

        if isinstance(result,str):
            result=result.strip()
        
        return result
    
    def _package_result(self, parse_key: str, vars: list[str]) -> dict[str, Any]:
        """打包批量结果"""
        package_config = self._compiled_packages[parse_key]
        channel_group = package_config.channel_group
        
        if not channel_group:
            raise ValueError(f"No channel_group specified in package for {parse_key}")
        
        # 获取通道组
        channels = self.protocol_config.channels.get(channel_group, [])
        
        if isinstance(channels, str):
            channels = [channels]
        
        # 构建数据包
        data_package: dict[str, Any] = {}
        for i, channel in enumerate(channels):
            if i < len(vars):
                data_package[channel] = vars[i]
            else:
                data_package[channel] = None
                self.logger.warning(f"Not enough values for channel {channel}")
        
        return data_package
    
    def _evaluate_result(self, parse_key: str, vars: list[str]) -> Any:
        """评估结果表达式"""
        result_expr = self._compiled_results[parse_key]
        
        # 安全的表达式求值环境
        safe_globals: dict[str, Any] = {
            'float': float,
            'int': int,
            'len': len,
            'vars': vars,
        }
        
        try:
            local_vars: dict[str, Any] = {'vars': vars, 'index': 0}
            result = eval(result_expr, safe_globals, local_vars)
            return result
        except Exception as e:
            self.logger.error(f"Result evaluation failed for {parse_key}: {e}")
            return vars[0] if vars else None
    
    def parse_batch_response(self, response: str, data_name: str, terminator: str) -> dict[str, Any]:
        """解析批量响应（多行）"""
        # 分割多行响应
        lines = response.split(terminator)
        lines = [line.strip() for line in lines if line.strip()]
        
        parse_key = f"get_all_{data_name}"
        if parse_key not in self._compiled_parse_steps:
            raise ValueError(f"No batch parse definition found for {data_name}")
        
        # 合并所有行的结果
        all_vars: list[str] = []
        for line in lines:
            steps = self._compiled_parse_steps[parse_key]
            vars: list[str] = [line]
            
            for step_func in steps:
                try:
                    vars = step_func(vars, line)
                    if vars:
                        all_vars.extend(vars)
                except Exception as e:
                    self.logger.warning(f"Batch parse step failed for line '{line}': {e}")
        
        # 打包结果
        return self._package_result(parse_key, all_vars)
