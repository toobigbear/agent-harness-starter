# AGENTS.md — Agent 上下文规范

## 项目概述
本项目是一个 AI Agent Harness 原型，演示如何给 AI Agent 套上控制层（Harness）。

## 技术栈
- Python 3.11+
- Docker（沙箱隔离）
- 文件系统持久化（JSON）

## 目录约定
- `workspace/` — Agent 可读写的唯一工作目录
- `memory/` — 状态持久化和检查点
- `logs/` — 审计日志（JSONL 格式）
- `harness/` — 控制层核心代码，Agent 不可修改
- `agents/` — Agent 业务逻辑定义

## 敏感路径（禁止操作）
- `/etc/`
- `/root/`
- `~/.ssh/`
- `../`（跳出项目目录）

## 如何验证
运行 `python run.py` 启动示例任务。

## 可用工具
参见 `harness/tools.py` 中的 `create_default_registry()` 函数。