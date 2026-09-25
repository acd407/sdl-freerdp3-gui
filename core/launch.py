"""launch — 启动 sdl-freerdp3。

设计要点（全部来自 Phase 0 实测）
--------------------------------
* **fire-and-forget**：不监控输出，不做错误分类。GUI 常驻，连接在独立进程里跑。
* **密码不传**：``sdl-freerdp3`` 自带凭据对话框（实测会出现
  ``app-id="com.freerdp.client.sdl3"``、标题 ``Credentials required for <host>``
  的窗口），所以 GUI 不需要实现密码输入。
* ``/cert:ignore`` 这类参数**无法写进 .rdp**（FreeRDP 的 100 个键里没有任何证书
  相关键），所以走 ``gui_extra_args`` 自定义键，在这里拼到命令行上。
* 用 ``setsid`` 派生，让客户端脱离 GUI 的进程组，GUI 退出不影响它。
"""

from __future__ import annotations

import os
import shlex
import shutil
import signal
import subprocess
from pathlib import Path

# 优先 SDL 客户端（Wayland 下表现最好），其次 wl，最后 x
CANDIDATES = ("sdl-freerdp3", "wlfreerdp3", "xfreerdp3")


class LaunchError(RuntimeError):
    pass


def find_binary() -> str:
    for name in CANDIDATES:
        path = shutil.which(name)
        if path:
            return path
    raise LaunchError("找不到 sdl-freerdp3 / wlfreerdp3 / xfreerdp3")


def build_command(rdp_path: Path, extra_args: str = "") -> list[str]:
    """构造命令行。``extra_args`` 会被 shell 风格拆分，支持引号里的空格。"""
    cmd = [find_binary(), os.fspath(rdp_path)]
    if extra_args.strip():
        try:
            cmd.extend(shlex.split(extra_args))
        except ValueError:
            # 引号不配对时退化为空白拆分，总比报错好
            cmd.extend(extra_args.split())
    return cmd


def launch(rdp_path: Path, extra_args: str = "") -> int:
    """启动客户端，立即返回子进程 pid。"""
    if not Path(rdp_path).is_file():
        raise LaunchError(f"找不到配置文件: {rdp_path}")

    cmd = build_command(rdp_path, extra_args)

    # 不要在子进程里继承我们的 stdin/stdout/stderr，
    # 否则客户端的输出会污染 GUI 的终端。
    devnull = subprocess.DEVNULL
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=devnull,
            stdout=devnull,
            stderr=devnull,
            start_new_session=True,  # ≈ setsid，脱离 GUI 的进程组
            close_fds=True,
        )
    except OSError as exc:  # pragma: no cover
        raise LaunchError(f"启动失败: {exc}") from exc
    return proc.pid


def terminate(pid: int) -> None:
    """尽力结束一个由 launch() 启动的进程。"""
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
