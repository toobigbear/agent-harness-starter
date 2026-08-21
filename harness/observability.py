"""
可观测性层：审计日志、结构化记录、事后追溯
"""
import json
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class AuditLogger:
    """结构化审计日志：记录 Agent 每一步的决策与执行"""

    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = str(uuid.uuid4())[:8]
        self.log_file = self.log_dir / f"session_{self.session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl"
        self.events: List[Dict[str, Any]] = []

    def _now(self) -> str:
        return datetime.now().isoformat()

    def log(self, event_type: str, payload: Dict[str, Any], agent_id: str = "default"):
        """记录一个事件"""
        event = {
            "timestamp": self._now(),
            "session_id": self.session_id,
            "agent_id": agent_id,
            "event_type": event_type,
            "payload": payload,
        }
        self.events.append(event)
        with open(self.log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def log_thought(self, thought: str, agent_id: str = "default"):
        self.log("THOUGHT", {"content": thought}, agent_id)

    def log_tool_request(self, tool_name: str, params: Dict, agent_id: str = "default"):
        self.log("TOOL_REQUEST", {"tool": tool_name, "params": params}, agent_id)

    def log_tool_result(self, tool_name: str, result: Any, duration_ms: float, agent_id: str = "default"):
        self.log("TOOL_RESULT", {"tool": tool_name, "result": result, "duration_ms": duration_ms}, agent_id)

    def log_permission_decision(self, tool_name: str, decision: str, reason: str, agent_id: str = "default"):
        self.log("PERMISSION", {"tool": tool_name, "decision": decision, "reason": reason}, agent_id)

    def log_halt(self, reason: str, agent_id: str = "default"):
        self.log("HALT", {"reason": reason}, agent_id)

    def log_error(self, error: str, agent_id: str = "default"):
        self.log("ERROR", {"error": error}, agent_id)

    def get_transcript(self) -> List[Dict[str, Any]]:
        """获取完整会话记录，用于复盘"""
        return self.events.copy()

    def summary(self) -> Dict[str, Any]:
        """会话摘要统计"""
        types = [e["event_type"] for e in self.events]
        return {
            "session_id": self.session_id,
            "total_events": len(self.events),
            "event_breakdown": {t: types.count(t) for t in set(types)},
            "log_file": str(self.log_file),
        }