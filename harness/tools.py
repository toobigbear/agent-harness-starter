"""
工具层：定义 Agent 可调用的工具，支持本地执行和沙箱执行两种模式
"""
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


class Tool:
    """单个工具的定义"""

    def __init__(
        self,
        name: str,
        description: str,
        handler: Callable,
        params_schema: Optional[Dict] = None,
        use_sandbox: bool = False,
    ):
        self.name = name
        self.description = description
        self.handler = handler
        self.params_schema = params_schema or {"type": "object", "properties": {}}
        self.use_sandbox = use_sandbox

    def execute(self, **kwargs) -> Any:
        return self.handler(**kwargs)

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.params_schema,
            "sandbox": self.use_sandbox,
        }


class ToolRegistry:
    """工具注册表：统一管理所有可用工具"""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Dict]:
        return [t.to_dict() for t in self._tools.values()]

    def execute(self, name: str, params: Dict, sandbox_runner=None) -> Any:
        tool = self.get(name)
        if not tool:
            raise ValueError(f"未知工具: {name}")

        if tool.use_sandbox and sandbox_runner:
            # 沙箱执行：把参数序列化后在沙箱中运行
            if name == "execute_python":
                return sandbox_runner.run_python_code(params.get("code", ""))
            elif name == "execute_shell":
                return sandbox_runner.run_shell_command(params.get("command", ""))
            else:
                # 通用沙箱执行：通过 JSON 传递参数
                wrapper_code = f"""
import json, sys
params = json.loads({json.dumps(json.dumps(params))})
# 这里简化处理，真实场景需要更复杂的序列化
result = {tool.handler.__name__}(**params)
print(json.dumps(result, ensure_ascii=False))
"""
                return sandbox_runner.run_python_code(wrapper_code)
        else:
            return tool.execute(**params)


# ========== 内置工具实现 ==========

def read_file(path: str) -> str:
    """读取文件内容"""
    p = Path(path)
    if not p.exists():
        return f"[错误] 文件不存在: {path}"
    try:
        return p.read_text(encoding="utf-8")
    except Exception as e:
        return f"[错误] 读取失败: {e}"


def write_file(path: str, content: str) -> str:
    """写入文件（本地执行，不走沙箱，因为需要持久化到 workspace）"""
    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"[成功] 已写入: {path} ({len(content)} 字符)"
    except Exception as e:
        return f"[错误] 写入失败: {e}"


def list_files(directory: str = "workspace") -> List[str]:
    """列出目录中的文件"""
    p = Path(directory)
    if not p.exists():
        return []
    try:
        return [str(f.relative_to(p)) for f in p.iterdir() if f.is_file()]
    except Exception as e:
        return [f"[错误] {e}"]


def execute_python(code: str) -> str:
    """执行 Python 代码（这个函数的本地版本，实际走沙箱）"""
    # 本地版本仅做参数校验，真实执行走沙箱
    return f"[沙箱执行] Python 代码长度: {len(code)}"


def execute_shell(command: str) -> str:
    """执行 Shell 命令（本地版本，真实执行走沙箱）"""
    return f"[沙箱执行] Shell 命令: {command}"


def calculate(expression: str) -> str:
    """安全计算数学表达式"""
    try:
        # 只允许数字和基本运算符
        allowed = set("0123456789+-*/(). ")
        if not all(c in allowed for c in expression):
            return "[错误] 表达式包含非法字符"
        result = eval(expression, {"__builtins__": {}}, {})
        return str(result)
    except Exception as e:
        return f"[错误] 计算失败: {e}"


def search_files(directory: str = "workspace", pattern: str = "") -> List[str]:
    """在目录中搜索包含指定内容的文件"""
    p = Path(directory)
    if not p.exists():
        return []
    matches = []
    for f in p.rglob("*"):
        if f.is_file():
            try:
                content = f.read_text(encoding="utf-8")
                if pattern in content:
                    matches.append(str(f.relative_to(p)))
            except Exception:
                pass
    return matches


def create_default_registry() -> ToolRegistry:
    """创建默认工具集"""
    registry = ToolRegistry()

    registry.register(Tool(
        name="read_file",
        description="读取指定路径的文件内容",
        handler=read_file,
        params_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "文件路径"}
            },
            "required": ["path"]
        },
    ))

    registry.register(Tool(
        name="write_file",
        description="将内容写入指定路径的文件",
        handler=write_file,
        params_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "目标文件路径"},
                "content": {"type": "string", "description": "文件内容"}
            },
            "required": ["path", "content"]
        },
    ))

    registry.register(Tool(
        name="list_files",
        description="列出指定目录中的文件",
        handler=list_files,
        params_schema={
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "目录路径，默认 workspace"}
            }
        },
    ))

    registry.register(Tool(
        name="calculate",
        description="计算数学表达式（仅支持 + - * / 和括号）",
        handler=calculate,
        params_schema={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "数学表达式"}
            },
            "required": ["expression"]
        },
    ))

    registry.register(Tool(
        name="search_files",
        description="在目录中搜索包含指定文本的文件",
        handler=search_files,
        params_schema={
            "type": "object",
            "properties": {
                "directory": {"type": "string"},
                "pattern": {"type": "string", "description": "要搜索的文本"}
            },
            "required": ["pattern"]
        },
    ))

    registry.register(Tool(
        name="execute_python",
        description="在 Docker 沙箱中执行 Python 代码",
        handler=execute_python,
        params_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python 代码"}
            },
            "required": ["code"]
        },
        use_sandbox=True,
    ))

    registry.register(Tool(
        name="execute_shell",
        description="在 Docker 沙箱中执行 Shell 命令",
        handler=execute_shell,
        params_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell 命令"}
            },
            "required": ["command"]
        },
        use_sandbox=True,
    ))

    return registry