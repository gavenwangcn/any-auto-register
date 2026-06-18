"""Local Turnstile solver (Camoufox / patchright)."""
from core.base_captcha import BaseCaptcha
from providers.registry import register_provider


@register_provider("captcha", "local_solver")
class LocalSolverCaptcha(BaseCaptcha):
    """调用本地 api_solver 服务解 Turnstile（Camoufox/patchright）"""

    def __init__(self, solver_url: str = ""):
        from services.solver_manager import SOLVER_URL

        resolved = str(solver_url or "").strip() or SOLVER_URL
        self.solver_url = resolved.rstrip("/")

    @classmethod
    def from_config(cls, config: dict) -> 'LocalSolverCaptcha':
        return cls(str(config.get("solver_url", "") or ""))

    def solve_turnstile(self, page_url: str, site_key: str) -> str:
        import requests, time

        if not self.solver_url:
            raise RuntimeError(
                "本地 Turnstile Solver 地址未配置，请在设置 -> 验证服务 -> 本地验证码求解器中填写 Solver 地址（默认 http://localhost:8889）"
            )
        # 提交任务
        r = requests.get(
            f"{self.solver_url}/turnstile",
            params={"url": page_url, "sitekey": site_key},
            timeout=15,
        )
        r.raise_for_status()
        task_id = r.json().get("taskId")
        if not task_id:
            raise RuntimeError(f"LocalSolver 未返回 taskId: {r.text}")
        # 轮询结果
        for _ in range(60):
            time.sleep(2)
            res = requests.get(
                f"{self.solver_url}/result",
                params={"id": task_id},
                timeout=10,
            )
            if res.status_code == 200:
                data = res.json()
                if data.get("errorId"):
                    message = data.get("errorDescription") or data.get("errorCode") or data
                    raise RuntimeError(f"LocalSolver Turnstile 失败: {message}")
                status = data.get("status")
                if status == "ready":
                    token = data.get("solution", {}).get("token")
                    if token:
                        return token
                elif status == "CAPTCHA_FAIL":
                    raise RuntimeError("LocalSolver Turnstile 失败")
        raise TimeoutError("LocalSolver Turnstile 超时")

    def solve_image(self, image_b64: str) -> str:
        raise NotImplementedError

    @staticmethod
    def start_solver(headless: bool = True, browser_type: str = "camoufox",
                     port: int = 8889) -> None:
        """在后台线程启动本地 solver 服务"""
        import subprocess, sys, os
        solver_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "services", "turnstile_solver", "start.py"
        )
        cmd = [
            sys.executable, solver_path,
            "--port", str(port),
            "--browser_type", browser_type,
        ]
        if not headless:
            cmd.append("--no-headless")
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # 等待服务启动
        import time, requests
        for _ in range(20):
            time.sleep(1)
            try:
                requests.get(f"http://localhost:{port}/", timeout=2)
                return
            except Exception:
                pass
        raise RuntimeError("LocalSolver 启动超时")
