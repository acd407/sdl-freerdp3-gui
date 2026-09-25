"""secrets — 用系统钥匙串（Secret Service）保存 RDP 密码。

为什么是这个方案
----------------
FreeRDP 3.28+ 的 SDL 客户端在弹出自己的凭据窗口**之前**会先走
``freerdp_passphrase_from_env()``，它会去读环境变量 ``FREERDP_ASKPASS`` 并把
提示语作为参数执行该程序（见 ``libfreerdp/utils/passphrase.c`` 和
``client/SDL/SDL3/dialogs/sdl_dialogs.cpp``）。所以「GUI 供密码」的正确入口就是
``FREERDP_ASKPASS``（AGENTS §13 也是这么写的），不需要 stdin，也不需要
``+force-console-callbacks``。

数据只存在两处：

* 密码本体 → 系统钥匙串（本模块 + ``askpass.py``）
* 「这份配置存过密码」这个事实 → .rdp 里的 ``gui_save_password`` 标记

密码**绝不**写进 .rdp，也**绝不**进 argv / 环境变量。

后端
----
优先 ``secret-tool``（libsecret 的命令行工具，走 ``org.freedesktop.secrets``；
GNOME Keyring / KWallet / oo7 都能用）。抽象成 ``SecretBackend`` 协议，测试时可
注入内存实现，将来要加 python-keyring 也只是多一个实现。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

__all__ = [
    "APP_ATTR",
    "Identity",
    "SecretBackend",
    "SecretToolBackend",
    "NullBackend",
    "get_backend",
    "identity_from_values",
    "build_attrs",
    "label",
    "session_bus_available",
]

# application 属性的值：本程序所有钥匙串条目的命名空间
APP_ATTR = "sdl-freerdp3-gui"

# secret-tool 等待用户解锁钥匙串时可能停很久，给一个宽松的上限
_DEFAULT_TIMEOUT = 120.0


@dataclass(frozen=True)
class Identity:
    """一条连接的身份。钥匙串条目就按它索引，而不是按 .rdp 文件名。

    这样重命名 / 复制 .rdp 都不会丢密码；同一服务器同一用户的多份配置共用一条。
    """

    host: str
    port: int
    username: str
    domain: str = ""

    def is_usable(self) -> bool:
        """信息够不够去钥匙串存取（至少要地址和用户名）。"""
        return bool(self.host.strip() and self.username.strip())


def identity_from_values(values: Mapping[str, object]) -> Identity:
    """从 controller 的字段值构造 ``Identity``。"""
    host = str(values.get("full address", "") or "").strip()
    username = str(values.get("username", "") or "").strip()
    domain = str(values.get("domain", "") or "").strip()
    try:
        port = int(values.get("server port", 3389) or 3389)
    except (TypeError, ValueError):
        port = 3389
    return Identity(host=host, port=port, username=username, domain=domain)


def _norm(value: str) -> str:
    """空属性统一成 ``-``：secret-tool 的空值匹配行为不可靠，归一更稳。"""
    value = (value or "").strip()
    return value if value else "-"


def build_attrs(ident: Identity) -> dict[str, str]:
    """构造钥匙串条目的属性集合。存 / 查 / 删必须用同一套。"""
    return {
        "application": APP_ATTR,
        "host": _norm(ident.host),
        "port": str(ident.port),
        "username": _norm(ident.username),
        "domain": _norm(ident.domain),
    }


def label(ident: Identity) -> str:
    """钥匙串 GUI 里显示的人类可读标签。"""
    return f"RDP {_norm(ident.username)}@{_norm(ident.host)}:{ident.port}"


def session_bus_available(env: Mapping[str, str] | None = None) -> bool:
    """会话 DBus 是否**可能**可用。

    不能只看 ``DBUS_SESSION_BUS_ADDRESS``：``secret-tool`` 底层的 GDBus 在
    环境变量缺失时会回退到 ``$XDG_RUNTIME_DIR/bus``（systemd user 会话的标准
    位置）。实测在只有该 socket、没有环境变量的环境里 ``secret-tool`` 依然
    正常工作，而程序却因为查不到环境变量而误判「钥匙串不可用」、把密码行整个
    禁用掉（踩过）。

    这里只做「存在性」判断；总线真的连不上时，``get/set`` 会失败并降级，
    不会造成误报以外的问题。
    """
    environ = os.environ if env is None else env
    if environ.get("DBUS_SESSION_BUS_ADDRESS"):
        return True
    runtime = environ.get("XDG_RUNTIME_DIR")
    return bool(runtime) and os.path.exists(os.path.join(runtime, "bus"))


@runtime_checkable
class SecretBackend(Protocol):
    """钥匙串后端接口。所有方法都不允许把密码写进日志。"""

    name: str

    @property
    def available(self) -> bool: ...

    def get(self, attrs: Mapping[str, str]) -> str | None: ...

    def set(self, attrs: Mapping[str, str], secret: str, label: str) -> bool: ...

    def delete(self, attrs: Mapping[str, str]) -> bool: ...

    def purge(self) -> bool: ...


class SecretToolBackend:
    """基于 ``secret-tool``（libsecret）的后端。

    密码只经 stdin（存）/ stdout（取）传递，从不出现在 argv 里。
    """

    name = "secret-tool"

    def __init__(self, binary: str | None = None, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._binary = binary if binary is not None else (shutil.which("secret-tool") or "")
        self._timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self._binary) and session_bus_available()

    @staticmethod
    def _args(attrs: Mapping[str, str]) -> list[str]:
        # secret-tool 的属性是位置参数：key value key value ...
        args: list[str] = []
        for key, value in attrs.items():
            args.extend([str(key), str(value)])
        return args

    def _run(self, argv: list[str], secret: str | None = None) -> subprocess.CompletedProcess[bytes] | None:
        try:
            return subprocess.run(
                [self._binary, *argv],
                input=secret.encode("utf-8") if secret is not None else None,
                capture_output=True,
                timeout=self._timeout,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None

    def get(self, attrs: Mapping[str, str]) -> str | None:
        if not self.available:
            return None
        proc = self._run(["lookup", *self._args(attrs)])
        if proc is None or proc.returncode != 0:
            return None
        pw = proc.stdout.decode("utf-8", "replace").rstrip("\n")
        if pw.endswith("\r"):
            pw = pw[:-1]
        return pw or None

    def set(self, attrs: Mapping[str, str], secret: str, label: str) -> bool:
        if not self.available or secret == "":
            return False
        proc = self._run(["store", "--label", label, *self._args(attrs)], secret=secret)
        return proc is not None and proc.returncode == 0

    def delete(self, attrs: Mapping[str, str]) -> bool:
        if not self.available:
            return False
        proc = self._run(["clear", *self._args(attrs)])
        return proc is not None and proc.returncode == 0

    def purge(self) -> bool:
        """清掉本程序在钥匙串里的**全部**条目（按 application 属性）。"""
        if not self.available:
            return False
        proc = self._run(["clear", "application", APP_ATTR])
        return proc is not None and proc.returncode == 0


class NullBackend:
    """钥匙串不可用时的空实现（UI 会显示「不可用」）。"""

    name = "unavailable"

    @property
    def available(self) -> bool:
        return False

    def get(self, attrs: Mapping[str, str]) -> str | None:
        return None

    def set(self, attrs: Mapping[str, str], secret: str, label: str) -> bool:
        return False

    def delete(self, attrs: Mapping[str, str]) -> bool:
        return False

    def purge(self) -> bool:
        return False


def get_backend() -> SecretBackend:
    """选一个可用后端。

    ``SFLGUI_SECRET_BACKEND=none`` 可强制禁用（便于排查 / 测试）。
    """
    forced = os.environ.get("SFLGUI_SECRET_BACKEND", "").strip().lower()
    if forced in ("none", "off", "0"):
        return NullBackend()
    backend = SecretToolBackend()
    return backend if backend.available else NullBackend()
