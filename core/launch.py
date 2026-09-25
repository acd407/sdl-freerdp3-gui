"""launch — 启动 sdl-freerdp3。

设计要点（全部来自 Phase 0 实测）
--------------------------------
* **fire-and-forget**：不监控输出，不做错误分类。GUI 常驻，连接在独立进程里跑。
* **密码**：默认不传，``sdl-freerdp3`` 自带凭据对话框。若调用方给出
  ``secret_attrs``（钥匙串条目的属性集合），则设置环境变量 ``FREERDP_ASKPASS``
  指向 ``core/askpass.py``，让客户端自己从钥匙串取密码（见 core/secrets.py）。
  密码既不进 argv，也不进环境变量。
* ``/cert:ignore`` 这类参数**无法写进 .rdp**（FreeRDP 的 100 个键里没有任何证书
  相关键），所以走 ``gui_extra_args`` 自定义键，在这里拼到命令行上。
* 用 ``setsid`` 派生，让客户端脱离 GUI 的进程组，GUI 退出不影响它。
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
from collections.abc import Mapping
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


def askpass_env(attrs: Mapping[str, str]) -> dict[str, str]:
    """构造让客户端从钥匙串取密码所需的环境变量。

    FreeRDP 会把 ``FREERDP_ASKPASS`` 的值原样拼进 ``sh -c``（后面再跟一个被单引号
    包起来的提示语），所以这里用 ``shlex.join`` 生成安全、无单引号冲突的命令。
    值里只含脚本路径和查询属性，**不含密码**。
    """
    python = sys.executable or "python3"
    script = os.fspath(Path(__file__).resolve().parent / "askpass.py")
    return {
        "FREERDP_ASKPASS": shlex.join([python, script]),
        "SFLGUI_SECRET_ATTRS": json.dumps(dict(attrs), ensure_ascii=False),
    }


def launch(rdp_path: Path, extra_args: str = "", secret_attrs: Mapping[str, str] | None = None) -> int:
    """启动客户端，立即返回子进程 pid。

    ``secret_attrs`` 非空时，子进程环境里会带上 ``FREERDP_ASKPASS``，客户端会先
    尝试从钥匙串取密码，失败再回退到自带凭据窗口。
    """
    if not Path(rdp_path).is_file():
        raise LaunchError(f"找不到配置文件: {rdp_path}")

    cmd = build_command(rdp_path, extra_args)

    env: dict[str, str] | None = None
    if secret_attrs:
        env = {**os.environ, **askpass_env(secret_attrs)}

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
            env=env,
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
