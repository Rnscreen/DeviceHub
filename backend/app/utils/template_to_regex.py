from typing import Callable
import re
def template_to_regex(template: str) -> str:
    """将占位符模板转换为正则表达式"""
    # 将 {var} 替换为 (?P<var>)
    # 注意：需要先转义特殊字符
    return re.sub(r'{(\w+)}',r'(?P<\1>.*)', template)

def create_matcher(template: str, var_pattern: str=r'\\w+') -> Callable[[str], dict[str, str]|None]:
    """创建模板匹配器"""
    pattern = re.sub('{(\\w+)}', f'(?P<\\1>{var_pattern})', template)
    pattern = f'^{pattern}$'
    compiled = re.compile(pattern)
    
    def matcher(text: str) -> dict[str, str]|None:
        """匹配文本是否符合模板"""
        match = compiled.match(text)
        return match.groupdict() if match else None
    
    return matcher

def test():
    # 创建多个模板的匹配器
    matchers: dict[str, Callable[[str], dict[str, str]|None]] = {
        'single': create_matcher("prefix_{response}"),
        'double': create_matcher("prefix_{response_code}_{response_data}"),
        'user': create_matcher("user_{id}_{name}"),
        'date': create_matcher("{year}-{month}-{day}", r'\\d+')  # 自定义数字匹配
    }

    # 测试
    test_cases = [
        "prefix_hello",
        "prefix_error_404",
        "user_123_john",
        "2024-12-31",
        "not_matching"
    ]

    for test in test_cases:
        matched = False
        for matcher_name, matcher in matchers.items():
            result = matcher(test)
            if result:
                print(f"'{test}' 匹配 {matcher_name}: {result}")
                matched = True
                break
        
        if not matched:
            print(f"'{test}' 不匹配任何模板")

if __name__ == '__main__':
    test()