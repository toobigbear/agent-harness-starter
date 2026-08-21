"""
文件分析 Agent：演示 Harness 的完整能力

这个 Agent 能：
1. 读取 workspace 中的文件
2. 在 Docker 沙箱中执行 Python 分析代码
3. 将分析结果写回 workspace
4. 全程受权限控制、审计日志、步数限制约束
"""
from harness.core import AgentHarness
from harness.tools import create_default_registry
from harness.permissions import PermissionPolicy
from harness.sandbox import SandboxRunner


def create_file_analyst_agent() -> AgentHarness:
    """创建并配置一个文件分析 Agent"""

    # 1. 定义权限策略（Harness 核心：约束 Agent 的能力边界）
    policy = PermissionPolicy(
        allowed_tools={"read_file", "write_file", "list_files", "calculate",
                       "search_files", "execute_python", "execute_shell"},
        denied_tools={"delete_file", "remove"},          # 明确禁止删除
        max_steps=8,                                      # 最多 8 步防死循环
        allow_network=False,                              # 禁止网络
        allow_file_write=True,
        allow_file_delete=False,
        allowed_paths=["workspace/", "memory/", "logs/"],  # 只能操作这些目录
        require_approval_for=set(),                       # 空 = 不需要额外审批
    )

    # 2. 创建 Docker 沙箱执行器
    sandbox = SandboxRunner(
        image="python:3.11-slim",
        workspace_mount="workspace",
        memory_limit="128m",
        cpu_limit=0.5,
        timeout_seconds=30,
        network_disabled=True,
    )

    # 3. 创建工具注册表
    tools = create_default_registry()

    # 4. 组装 Harness
    agent = AgentHarness(
        agent_id="file_analyst_v1",
        tool_registry=tools,
        permission_policy=policy,
        sandbox_runner=sandbox,
    )

    return agent