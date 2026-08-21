"""
核心层：Agent 控制循环（ReAct 模式）+ Harness 编排

公式: Agent = Model + Harness
Harness = 控制循环 + 工具路由 + 记忆 + 权限 + 沙箱 + 观测
"""
import json
import time
from typing import Any, Dict, List, Optional

from .observability import AuditLogger
from .memory import MemoryStore
from .permissions import PermissionGuard, PermissionPolicy
from .sandbox import SandboxRunner
from .tools import ToolRegistry


class AgentHarness:
    """
    Agent Harness 主控制器

    职责：
    1. 管理 ReAct 循环（推理 → 行动 → 观察）
    2. 每一步都经过权限检查
    3. 工具执行走沙箱隔离
    4. 所有决策记录审计日志
    5. 状态持久化到记忆存储
    6. 硬护栏防止死循环和越权
    """

    def __init__(
        self,
        agent_id: str,
        tool_registry: ToolRegistry,
        permission_policy: PermissionPolicy,
        sandbox_runner: Optional[SandboxRunner] = None,
        memory_store: Optional[MemoryStore] = None,
        audit_logger: Optional[AuditLogger] = None,
        model_callback = None,  # 外部注入的模型调用函数
    ):
        self.agent_id = agent_id
        self.tools = tool_registry
        self.guard = PermissionGuard(permission_policy)
        self.sandbox = sandbox_runner
        self.memory = memory_store or MemoryStore()
        self.logger = audit_logger or AuditLogger()
        self.model_callback = model_callback or self._default_model

        # 会话状态
        self.history: List[Dict[str, Any]] = []
        self.step = 0
        self.halted = False
        self.halt_reason = ""

    def _default_model(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        默认模型回调（模拟 LLM 响应）
        真实场景应替换为 OpenAI/Claude/本地模型 API 调用
        """
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break

        # 简单规则引擎：根据用户输入决定工具调用
        content = last_user.lower()

        # 分析任务类型并返回结构化响应
        if "read" in content or "读取" in content or "查看" in content:
            # 提取路径
            import re
            paths = re.findall(r'["\']([^"\']+)["\']|([\w\-./]+\.\w+)', last_user)
            path = paths[0][0] or paths[0][1] if paths else "workspace/sample_data.txt"
            return {
                "thought": f"用户要求读取文件，我将使用 read_file 工具读取 {path}",
                "action": {"tool": "read_file", "params": {"path": path}},
                "is_final": False,
            }

        elif "write" in content or "写入" in content or "创建" in content:
            return {
                "thought": "用户要求写入文件，我将使用 write_file 工具",
                "action": {"tool": "write_file", "params": {"path": "workspace/output.txt", "content": "Hello from Agent Harness!"}},
                "is_final": False,
            }

        elif "calculate" in content or "计算" in content:
            import re
            exprs = re.findall(r'[\d\+\-\*/\(\)\. ]+', last_user)
            expr = exprs[0].strip() if exprs else "1+1"
            return {
                "thought": f"用户要求计算表达式: {expr}",
                "action": {"tool": "calculate", "params": {"expression": expr}},
                "is_final": False,
            }

        elif "python" in content or "代码" in content or "执行" in content:
            return {
                "thought": "用户要求执行 Python 代码，我将在沙箱中运行",
                "action": {"tool": "execute_python", "params": {"code": "print('Hello from sandbox!')\nprint(2**10)"}},
                "is_final": False,
            }

        elif "list" in content or "文件" in content or "目录" in content:
            return {
                "thought": "用户要求列出文件",
                "action": {"tool": "list_files", "params": {"directory": "workspace"}},
                "is_final": False,
            }

        elif "shell" in content or "命令" in content:
            return {
                "thought": "用户要求执行 shell 命令，我将在沙箱中运行",
                "action": {"tool": "execute_shell", "params": {"command": "ls -la"}},
                "is_final": False,
            }

        else:
            return {
                "thought": "任务已完成，无需进一步工具调用",
                "action": None,
                "is_final": True,
                "answer": f"已收到您的请求: {last_user}。这是一个模拟回复，真实场景会调用 LLM 生成完整回答。",
            }

    def _build_system_prompt(self) -> str:
        """构建系统提示，包含可用工具列表和约束"""
        tools_desc = json.dumps(self.tools.list_tools(), ensure_ascii=False, indent=2)
        return f"""你是一个受控 AI Agent，运行在 Harness 控制层下。

可用工具列表:
{tools_desc}

约束:
1. 每次只能调用一个工具
2. 所有文件操作必须在 workspace/ 目录下
3. 危险操作（删除、网络访问）被禁止
4. 最大步数限制: {self.guard.policy.max_steps}
5. 代码执行在 Docker 沙箱中完成

请按以下格式响应（JSON）:
{{
  "thought": "你的推理过程",
  "action": {{"tool": "工具名", "params": {{...}}}},
  "is_final": false
}}
或任务完成时:
{{
  "thought": "任务完成",
  "action": null,
  "is_final": true,
  "answer": "最终答案"
}}
"""

    def run(self, task: str, resume: bool = False) -> str:
        """
        运行 Agent 完成一个任务

        Args:
            task: 用户输入的任务描述
            resume: 是否从上次断点恢复

        Returns:
            最终答案或错误信息
        """
        # 1. 恢复状态（如果 resume=True）
        if resume:
            saved = self.memory.load(self.agent_id)
            if saved:
                self.history = saved.get("history", [])
                self.step = saved.get("step", 0)
                print(f"[Harness] 从检查点恢复，当前步数: {self.step}")

        # 2. 初始化历史
        if not self.history:
            self.history.append({"role": "system", "content": self._build_system_prompt()})

        self.history.append({"role": "user", "content": task})
        self.logger.log("TASK_START", {"task": task}, self.agent_id)

        # 3. ReAct 主循环
        while not self.halted:
            self.step += 1
            print(f"\n[Harness] Step {self.step}/{self.guard.policy.max_steps}")

            # 3.1 上下文压缩
            context = self.memory.compact_history(self.history, max_items=15)

            # 3.2 模型推理
            try:
                response = self.model_callback(context)
            except Exception as e:
                self.logger.log_error(f"模型调用失败: {e}", self.agent_id)
                self._halt(f"模型调用失败: {e}")
                break

            thought = response.get("thought", "")
            action = response.get("action")
            is_final = response.get("is_final", False)

            self.logger.log_thought(thought, self.agent_id)
            print(f"[Agent Thought] {thought}")

            # 3.3 如果是最终答案，结束循环
            if is_final:
                answer = response.get("answer", "任务完成")
                self.history.append({"role": "assistant", "content": answer})
                self.logger.log("TASK_COMPLETE", {"answer": answer}, self.agent_id)
                self._save_state()
                return answer

            # 3.4 解析工具调用
            if not action:
                self._halt("模型返回了无效的动作")
                break

            tool_name = action.get("tool")
            params = action.get("params", {})

            # 3.5 权限检查（Harness 核心：护栏）
            allowed, reason = self.guard.check(tool_name, params, self.agent_id)
            self.logger.log_permission_decision(tool_name, "ALLOW" if allowed else "DENY", reason, self.agent_id)

            if not allowed:
                error_msg = f"权限拒绝: {reason}"
                print(f"[Harness Guard] ❌ {error_msg}")
                self.history.append({"role": "tool", "content": error_msg, "tool": tool_name})
                self.logger.log_error(error_msg, self.agent_id)
                # 不直接 halt，让模型有机会调整策略
                continue

            print(f"[Harness Guard] ✅ 允许执行: {tool_name}({params})")
            self.logger.log_tool_request(tool_name, params, self.agent_id)

            # 3.6 执行工具
            start_time = time.time()
            try:
                result = self.tools.execute(tool_name, params, sandbox_runner=self.sandbox)
            except Exception as e:
                result = f"[执行错误] {e}"
            duration_ms = (time.time() - start_time) * 1000

            self.logger.log_tool_result(tool_name, result, duration_ms, self.agent_id)
            print(f"[Tool Result] {str(result)[:200]}")

            # 3.7 把结果加入历史，让模型观察
            self.history.append({
                "role": "tool",
                "content": json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                "tool": tool_name,
            })

            # 3.8 创建检查点
            self.memory.checkpoint(self.agent_id, self.step, {
                "history": self.history,
                "step": self.step,
            })

            # 3.9 步数上限检查
            if self.step >= self.guard.policy.max_steps:
                self._halt("达到最大步数限制")
                break

        # 循环结束（被 halt）
        self._save_state()
        return f"任务中止: {self.halt_reason}"

    def _halt(self, reason: str):
        """停止 Agent 执行"""
        self.halted = True
        self.halt_reason = reason
        self.logger.log_halt(reason, self.agent_id)
        print(f"[Harness] 🛑 已停止: {reason}")

    def _save_state(self):
        """保存当前状态"""
        self.memory.save(self.agent_id, {
            "history": self.history,
            "step": self.step,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        })

    def get_transcript(self) -> List[Dict]:
        """获取完整审计记录"""
        return self.logger.get_transcript()

    def get_summary(self) -> Dict:
        """获取会话摘要"""
        return {
            "agent_id": self.agent_id,
            "logger_summary": self.logger.summary(),
            "guard_stats": self.guard.get_stats(),
            "total_steps": self.step,
            "halted": self.halted,
            "halt_reason": self.halt_reason,
        }