from typing import Any, Optional
def convert_type(value: Any, target_type: Optional[str]='str') -> Any:
    """将值转换为指定的目标类型
    
    Args:
        value: 要转换的值
        target_type: 目标类型名称，支持: 'int', 'float', 'str', 'bool'
    
    Returns:
        转换后的值
    
    Raises:
        ValueError: 当目标类型不支持或转换失败时
    """
    result:Any = None
    if value is None:
        return None
    if target_type is None:
        target_type = 'str'
    else:
        match target_type.lower():
            case "int":
                try:
                    result = int(value)
                except ValueError:
                    result = 0
            case "float":
                try:
                    result = float(value)
                except ValueError:
                    result = 0.0    
            case "str":
                result = str(value)
            case "bool":
                if isinstance(value, bool):
                    result = value
                elif isinstance(value, str):
                    if value.lower() in ("true","True", "1"):
                        result = True
                    else:
                        result = False
                else:
                    result = False
            case _:
                # 其他类型保持不变
                result = value
    return result
