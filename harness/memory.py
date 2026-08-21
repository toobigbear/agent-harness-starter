"""
记忆层：跨会话状态持久化、上下文压缩、断点恢复
"""
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional


class MemoryStore:
    """基于文件系统的持久化记忆存储，支持原子写入防损坏"""

    def __init__(self, memory_dir: str = "memory"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, agent_id: str) -> Path:
        return self.memory_dir / f"{agent_id}_state.json"

    def save(self, agent_id: str, state: Dict[str, Any]):
        """原子写入：先写 .tmp 再 mv，防止并发写损坏"""
        path = self._path(agent_id)
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        shutil.move(str(tmp_path), str(path))

    def load(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """加载状态，损坏时返回 None 让上层恢复"""
        path = self._path(agent_id)
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    def compact_history(self, history: List[Dict[str, Any]], max_items: int = 20) -> List[Dict[str, Any]]:
        """上下文压缩：保留最近 N 条，旧的做摘要（这里简化：直接截断）"""
        if len(history) <= max_items:
            return history
        # 保留系统提示 + 最近 N-1 条
        compacted = [history[0]] if history and history[0].get("role") == "system" else []
        compacted.extend(history[-(max_items - 1):])
        return compacted

    def checkpoint(self, agent_id: str, step: int, state: Dict[str, Any]):
        """创建检查点，支持回滚"""
        checkpoint_dir = self.memory_dir / "checkpoints" / agent_id
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        cp_path = checkpoint_dir / f"step_{step}.json"
        with open(cp_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return str(cp_path)

    def rollback(self, agent_id: str, step: int) -> Optional[Dict[str, Any]]:
        """回滚到指定检查点"""
        cp_path = self.memory_dir / "checkpoints" / agent_id / f"step_{step}.json"
        if not cp_path.exists():
            return None
        with open(cp_path, "r", encoding="utf-8") as f:
            return json.load(f)