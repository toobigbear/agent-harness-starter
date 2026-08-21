#!/usr/bin/env python3
"""
Agent Harness 启动脚本

用法:
    python run.py <task>
    python run.py "读取 sample_data.txt 并计算平均分"
    python run.py "列出 workspace 中的所有文件"
    python run.py "在沙箱中执行 Python 代码计算 2**20"
    python run.py --transcript   # 查看上次会话审计记录
    python run.py --summary      # 查看上次会话摘要
"""
import sys
import json

from agents.file_analyst import create_file_analyst_agent


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\n示例任务:")
        print('  python run.py "读取 workspace/sample_data.txt"')
        print('  python run.py "计算 85+92+78+88+95 的平均值"')
        print('  python run.py "在沙箱中执行 print(2**20)"')
        print('  python run.py "搜索包含 Alice 的文件"')
        print('  python run.py --transcript')
        print('  python run.py --summary')
        sys.exit(1)

    task = " ".join(sys.argv[1:])

    # 查看审计记录
    if task == "--transcript":
        # 从日志目录读取最新的日志文件
        from pathlib import Path
        log_dir = Path("logs")
        if not log_dir.exists():
            print("暂无日志文件")
            return
        logs = sorted(log_dir.glob("session_*.jsonl"))
        if not logs:
            print("暂无日志文件")
            return
        latest = logs[-1]
        print(f"=== 审计记录: {latest.name} ===\n")
        with open(latest, "r",encoding='utf-8') as f:
            for line in f:
                event = json.loads(line)
                ts = event["timestamp"]
                et = event["event_type"]
                agent = event["agent_id"]
                payload = json.dumps(event["payload"], ensure_ascii=False)[:200]
                print(f"[{ts}] [{et}] [{agent}] {payload}")
        return

    # 查看会话摘要
    if task == "--summary":
        from pathlib import Path
        from harness.memory import MemoryStore
        mem = MemoryStore()
        state = mem.load("file_analyst_v1")
        if not state:
            print("暂无保存的状态")
            return
        print("=== 会话状态 ===")
        print(f"步数: {state.get('step', 0)}")
        print(f"已停止: {state.get('halted', False)}")
        print(f"停止原因: {state.get('halt_reason', 'N/A')}")
        print(f"历史消息数: {len(state.get('history', []))}")
        return

    # 创建 Agent 并运行任务
    print("=" * 60)
    print("🚀 启动 Agent Harness")
    print("=" * 60)

    agent = create_file_analyst_agent()

    print(f"\n📋 任务: {task}")
    print("-" * 60)

    result = agent.run(task)

    print("-" * 60)
    print(f"\n✅ 最终结果:\n{result}")
    print("\n" + "=" * 60)
    print("📊 会话摘要:")
    summary = agent.get_summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("=" * 60)


if __name__ == "__main__":
    main()