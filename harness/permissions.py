"""
权限层：工具调用前的策略检查、危险操作拦截、审批流
"""
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set


@dataclass
class PermissionPolicy:
    """权限策略：定义 Agent 能做什么、不能做什么"""
    allowed_tools: Set[str] = field(default_factory=set)      # 空 = 全部允许（黑名单模式）
    denied_tools: Set[str] = field(default_factory=set)         # 明确禁止的工具
    dangerous_patterns: List[str] = field(default_factory=list) # 参数中的危险模式
    require_approval_for: Set[str] = field(default_factory=set) # 需要人工确认的工具
    max_steps: int = 10                                         # 最大步数防死循环
    allow_network: bool = False                                 # 是否允许网络访问
    allow_file_write: bool = True                               # 是否允许写文件
    allow_file_delete: bool = False                             # 是否允许删除文件
    allowed_paths: List[str] = field(default_factory=lambda: ["workspace/"])  # 允许操作的路径前缀


class PermissionGuard:
    """权限守卫：每个工具调用前必须经过这里"""

    DANGEROUS_KEYWORDS = [
        "rm -rf", "sudo", "chmod 777", "mkfs", "dd if=",
        r"curl.*\|.*sh", r"wget.*\|.*sh", r"> /dev/", r"eval\(", r"exec\(",
        "__import__('os').system", "subprocess.call", "os.system",
    ]

    def __init__(self, policy: PermissionPolicy):
        self.policy = policy
        self.step_count = 0
        self.approval_cache: Dict[str, bool] = {}  # 已审批的工具缓存

    def check(self, tool_name: str, params: Dict, agent_id: str = "default") -> tuple[bool, str]:
        """
        检查工具调用是否被允许
        返回: (is_allowed, reason)
        """
        self.step_count += 1

        # 1. 步数上限护栏
        if self.step_count > self.policy.max_steps:
            return False, f"步数超限: {self.step_count}/{self.policy.max_steps}"

        # 2. 黑名单检查
        if tool_name in self.policy.denied_tools:
            return False, f"工具 '{tool_name}' 在黑名单中"

        # 3. 白名单检查（如果配置了白名单）
        if self.policy.allowed_tools and tool_name not in self.policy.allowed_tools:
            return False, f"工具 '{tool_name}' 不在允许列表中"

        # 4. 参数危险模式检查
        params_str = str(params).lower()
        for pattern in self.DANGEROUS_KEYWORDS:
            if re.search(pattern, params_str):
                return False, f"参数匹配危险模式: '{pattern}'"

        # 5. 路径检查
        if "path" in params or "file_path" in params:
            path = params.get("path") or params.get("file_path") or ""
            if not any(str(path).startswith(ap) for ap in self.policy.allowed_paths):
                return False, f"路径 '{path}' 超出允许范围: {self.policy.allowed_paths}"

        # 6. 写权限检查
        if tool_name in ("write_file", "append_file") and not self.policy.allow_file_write:
            return False, "文件写入被策略禁止"

        # 7. 删除权限检查
        if tool_name in ("delete_file", "remove") and not self.policy.allow_file_delete:
            return False, "文件删除被策略禁止"

        # 8. 网络权限检查
        if tool_name in ("fetch_url", "http_get", "curl") and not self.policy.allow_network:
            return False, "网络访问被策略禁止"

        # 9. 需要人工审批的工具
        if tool_name in self.policy.require_approval_for:
            cache_key = f"{agent_id}:{tool_name}:{hash(str(params))}"
            if cache_key not in self.approval_cache:
                # 这里简化：自动拒绝，真实场景应弹出 UI 或发送审批请求
                return False, f"工具 '{tool_name}' 需要人工审批（当前自动拒绝）"

        return True, "通过"

    def grant_approval(self, tool_name: str, params: Dict, agent_id: str = "default"):
        """人工审批通过后调用"""
        cache_key = f"{agent_id}:{tool_name}:{hash(str(params))}"
        self.approval_cache[cache_key] = True

    def get_stats(self) -> Dict:
        return {
            "steps_executed": self.step_count,
            "max_steps": self.policy.max_steps,
            "remaining": max(0, self.policy.max_steps - self.step_count),
        }