"""
Harness 核心组件单元测试
"""
import json
import tempfile
from pathlib import Path

from harness.permissions import PermissionPolicy, PermissionGuard
from harness.memory import MemoryStore
from harness.observability import AuditLogger
from harness.tools import create_default_registry


def test_permission_guard():
    """测试权限守卫"""
    policy = PermissionPolicy(
        max_steps=3,
        denied_tools={"execute_shell"},
        allow_file_delete=False,
        allow_network=False,
        allowed_paths=["workspace/"],
    )
    guard = PermissionGuard(policy)

    # 正常工具应通过
    ok, reason = guard.check("read_file", {"path": "workspace/test.txt"})
    assert ok, f"应允许 read_file: {reason}"

    # 黑名单工具应拒绝
    ok, reason = guard.check("execute_shell", {"command": "ls"})
    assert not ok, "应拒绝 execute_shell"

    # 越权路径应拒绝
    ok, reason = guard.check("read_file", {"path": "/etc/passwd"})
    assert not ok, "应拒绝越权路径"

    # 危险参数应拒绝
    ok, reason = guard.check("execute_python", {"code": "rm -rf /"})
    assert not ok, "应拒绝危险参数"

    # 步数上限
    guard2 = PermissionGuard(PermissionPolicy(max_steps=1))
    guard2.check("read_file", {"path": "workspace/test.txt"})
    ok, reason = guard2.check("read_file", {"path": "workspace/test.txt"})
    assert not ok, "应拒绝超步数"

    print("✅ PermissionGuard 测试通过")


def test_memory_store():
    """测试记忆存储"""
    with tempfile.TemporaryDirectory() as tmpdir:
        mem = MemoryStore(memory_dir=tmpdir)

        # 保存和加载
        mem.save("test_agent", {"history": [{"role": "user", "content": "hi"}], "step": 1})
        loaded = mem.load("test_agent")
        assert loaded["step"] == 1

        # 检查点
        cp = mem.checkpoint("test_agent", 2, {"step": 2})
        assert Path(cp).exists()

        rolled = mem.rollback("test_agent", 2)
        assert rolled["step"] == 2

        # 上下文压缩
        long_history = [{"role": "system"}] + [{"role": "user", "content": str(i)} for i in range(30)]
        compacted = mem.compact_history(long_history, max_items=10)
        assert len(compacted) == 10
        assert compacted[0]["role"] == "system"

        print("✅ MemoryStore 测试通过")


def test_audit_logger():
    """测试审计日志"""
    with tempfile.TemporaryDirectory() as tmpdir:
        logger = AuditLogger(log_dir=tmpdir)
        logger.log_thought("思考中...", "agent_1")
        logger.log_tool_request("read_file", {"path": "test.txt"}, "agent_1")
        logger.log_tool_result("read_file", "hello", 15.2, "agent_1")

        transcript = logger.get_transcript()
        assert len(transcript) == 3
        assert logger.summary()["total_events"] == 3

        print("✅ AuditLogger 测试通过")


def test_tool_registry():
    """测试工具注册表"""
    registry = create_default_registry()
    tools = registry.list_tools()
    assert len(tools) >= 5

    # 测试本地工具
    result = registry.execute("calculate", {"expression": "2+3*4"})
    assert result == "14"

    # 测试未知工具
    try:
        registry.execute("unknown_tool", {})
        assert False, "应抛出异常"
    except ValueError:
        pass

    print("✅ ToolRegistry 测试通过")


if __name__ == "__main__":
    test_permission_guard()
    test_memory_store()
    test_audit_logger()
    test_tool_registry()
    print("\n🎉 所有测试通过!")