"""
沙箱层：Docker 容器隔离工具执行，限制资源、网络、文件系统访问
"""
import os
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional


class SandboxRunner:
    """
    Docker 沙箱执行器
    用 docker-py 在隔离容器中运行不可信代码/命令
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        workspace_mount: str = "workspace",
        memory_limit: str = "128m",
        cpu_limit: float = 0.5,
        timeout_seconds: int = 30,
        network_disabled: bool = True,
    ):
        self.image = image
        self.workspace_mount = Path(workspace_mount).resolve()
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.timeout_seconds = timeout_seconds
        self.network_disabled = network_disabled
        self._client = None
        self._ensure_image()

    def _get_client(self):
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except ImportError:
                raise RuntimeError("请先安装 docker-py: pip install docker")
            except Exception as e:
                raise RuntimeError(f"Docker 连接失败: {e}")
        return self._client

    def _ensure_image(self):
        """确保镜像存在，不存在则尝试拉取"""
        try:
            client = self._get_client()
            client.images.get(self.image)
        except Exception:
            print(f"[Sandbox] 拉取镜像 {self.image} ...")
            client = self._get_client()
            client.images.pull(self.image)
            print(f"[Sandbox] 镜像拉取完成")

    def run_command(
        self,
        command: List[str],
        working_dir: str = "/workspace",
        env_vars: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """
        在 Docker 容器中执行命令

        Returns:
            {
                "stdout": str,
                "stderr": str,
                "exit_code": int,
                "duration_ms": float,
            }
        """
        client = self._get_client()

        # 确保工作目录挂载点存在
        self.workspace_mount.mkdir(parents=True, exist_ok=True)

        volumes = {
            str(self.workspace_mount): {
                "bind": working_dir,
                "mode": "rw" if self.network_disabled else "rw",
            }
        }

        start = time.time()
        container = None
        try:
            container = client.containers.run(
                image=self.image,
                command=command,
                volumes=volumes,
                working_dir=working_dir,
                environment=env_vars or {},
                network_disabled=self.network_disabled,
                mem_limit=self.memory_limit,
                cpu_quota=int(self.cpu_limit * 100000),
                cpu_period=100000,
                detach=True,
                stdout=True,
                stderr=True,
            )

            result = container.wait(timeout=self.timeout_seconds)
            exit_code = result.get("StatusCode", -1)

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

            duration_ms = (time.time() - start) * 1000

            return {
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "duration_ms": round(duration_ms, 2),
            }

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            return {
                "stdout": "",
                "stderr": str(e),
                "exit_code": -1,
                "duration_ms": round(duration_ms, 2),
            }

        finally:
            if container:
                try:
                    container.stop(timeout=1)
                    container.remove(force=True)
                except Exception:
                    pass

    def run_python_code(self, code: str, working_dir: str = "/workspace") -> Dict:
        """在沙箱中执行 Python 代码"""
        # 把代码写入临时文件，再在沙箱中执行
        tmp_file = self.workspace_mount / f"_sandbox_{os.urandom(4).hex()}.py"
        tmp_file.write_text(code, encoding="utf-8")

        rel_path = f"{working_dir}/{tmp_file.name}"
        result = self.run_command(
            command=["python", rel_path],
            working_dir=working_dir,
        )

        # 清理临时文件
        try:
            tmp_file.unlink()
        except Exception:
            pass

        return result

    def run_shell_command(self, command: str, working_dir: str = "/workspace") -> Dict:
        """在沙箱中执行 shell 命令"""
        return self.run_command(
            command=["sh", "-c", command],
            working_dir=working_dir,
        )