"""profiles — 连接配置的存放、列举、读写、软删除。

布局
----
``~/.config/sdl-freerdp3-gui/``

* ``profiles/<名称>.rdp``   每个配置一个文件（**单文件方案**，GUI 元数据用
  ``gui_`` 前缀的自定义键存在同一个文件里）
* ``trash/``                删除的配置移到这里，不是真删
* ``config.json``           GUI 自己的状态（窗口尺寸、上次选中项等）

草稿（快速连接）写到 ``$XDG_RUNTIME_DIR/sdl-freerdp3-gui/``，不落盘到配置文件目录。
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from .rdpfile import RdpFile

APP_DIR_NAME = "sdl-freerdp3-gui"
SUFFIX = ".rdp"

# 文件名里不允许出现的字符（Windows 和 POSIX 都要安全）
_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / APP_DIR_NAME


def _runtime_dir() -> Path:
    base = os.environ.get("XDG_RUNTIME_DIR") or "/tmp"
    d = Path(base) / APP_DIR_NAME
    try:
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)
        return d
    except OSError:
        fallback = Path("/tmp") / APP_DIR_NAME
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


CONFIG_DIR = _config_dir()
PROFILE_DIR = CONFIG_DIR / "profiles"
TRASH_DIR = CONFIG_DIR / "trash"
RUNTIME_DIR = _runtime_dir()
STATE_FILE = CONFIG_DIR / "config.json"


@dataclass(frozen=True)
class ProfileInfo:
    name: str
    path: Path
    host: str
    username: str
    port: int

    @property
    def subtitle(self) -> str:
        bits = [self.host or "(未填地址)"]
        if self.port and self.port != 3389:
            bits.append(f":{self.port}")
        if self.username:
            bits.append(f"· {self.username}")
        return " ".join(bits)


def ensure_dirs() -> None:
    for d in (CONFIG_DIR, PROFILE_DIR, TRASH_DIR):
        d.mkdir(parents=True, exist_ok=True)


def sanitize(name: str) -> str:
    """把用户输入的名称变成安全的文件名（允许中文）。"""
    name = _ILLEGAL.sub("_", name).strip().strip(".")
    name = name.replace("\n", " ")
    return name or "未命名"


def available_name(base: str) -> str:
    """若同名已存在，追加 -2 / -3 …"""
    ensure_dirs()
    base = sanitize(base)
    if not (PROFILE_DIR / f"{base}{SUFFIX}").exists():
        return base
    n = 2
    while (PROFILE_DIR / f"{base}-{n}{SUFFIX}").exists():
        n += 1
    return f"{base}-{n}"


def list_profiles() -> list[ProfileInfo]:
    ensure_dirs()
    out: list[ProfileInfo] = []
    for p in sorted(PROFILE_DIR.glob(f"*{SUFFIX}"), key=lambda x: x.stem.lower()):
        try:
            f = RdpFile.load(p)
            out.append(
                ProfileInfo(
                    name=p.stem,
                    path=p,
                    host=f.get_str("full address"),
                    username=f.get_str("username"),
                    port=f.get_int("server port", 3389),
                )
            )
        except OSError:
            continue
    return out


def path_for(name: str) -> Path:
    return PROFILE_DIR / f"{sanitize(name)}{SUFFIX}"


def load(name: str) -> RdpFile:
    return RdpFile.load(path_for(name))


def save(name: str, rdp: RdpFile) -> Path:
    ensure_dirs()
    path = path_for(name)
    rdp.save(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def delete(name: str) -> Path | None:
    """软删除：移到 trash/，同名则加时间戳。"""
    src = path_for(name)
    if not src.exists():
        return None
    ensure_dirs()
    dst = TRASH_DIR / src.name
    if dst.exists():
        import time

        dst = TRASH_DIR / f"{src.stem}.{int(time.time())}{SUFFIX}"
    shutil.move(str(src), str(dst))
    return dst


def rename(old: str, new: str) -> Path:
    src, dst = path_for(old), path_for(new)
    if src.exists() and src != dst:
        ensure_dirs()
        if dst.exists():
            raise FileExistsError(new)
        shutil.move(str(src), str(dst))
    return dst


# --------------------------------------------------------------- 草稿


def draft_path() -> Path:
    return RUNTIME_DIR / "quick.rdp"


def write_draft(rdp: RdpFile) -> Path:
    """把草稿写到运行目录（不污染配置目录）。"""
    p = draft_path()
    rdp.save(p)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return p


# --------------------------------------------------------------- GUI 状态


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(state: dict) -> None:
    ensure_dirs()
    tmp = STATE_FILE.with_suffix(".json.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, STATE_FILE)
    except OSError:
        pass
