"""rdpfile — 极简的 Microsoft .rdp 连接文件读写库（零依赖）。

格式
----
每行 ``key:type:value``：

* ``type`` 是 ``i``（整数）或 ``s``（字符串）
* ``key`` 可以含空格（如 ``full address``）
* ``value`` 可以含冒号（如 ``C:\\;D:\\``），因此只按**前两个**冒号切分

关于未知键
----------
实测（FreeRDP 3.31.1）：FreeRDP 解析 .rdp 时会静默接受任何未知键，把它们存进
``rdpFile.lines[]``，应用设置时完全忽略，并在 ``freerdp_client_write_rdp_file``
时原样写回。因此本库可以安全地用自定义键（本项目的 GUI 用 ``gui_`` 前缀）存放
自己的元数据，而不会影响 FreeRDP 的行为。

用法
----
>>> f = RdpFile.load("office.rdp")
>>> f.get_str("full address")
'192.168.1.10'
>>> f.set("server port", 3390)
>>> f.get_bool("redirectclipboard", True)
True
>>> print(f.dumps())
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

__all__ = ["Entry", "RdpFile", "RdpParseError"]

# 我们自己的键前缀。FreeRDP 会忽略它们。
GUI_PREFIX = "gui_"

# 本项目存放「额外命令行参数」的自定义键
KEY_EXTRA_ARGS = "gui_extra_args"


class RdpParseError(ValueError):
    """文件存在但无法解析。"""


@dataclass
class Entry:
    """一条 ``key:type:value`` 记录。``raw`` 保存无法识别的行。"""

    key: str
    type: str | None = None  # 'i' | 's' | None（无法识别的行）
    value: str = ""

    @property
    def is_int(self) -> bool:
        return self.type == "i"

    @property
    def is_str(self) -> bool:
        return self.type == "s"

    def render(self) -> str:
        if self.type is None:
            return self.key
        return f"{self.key}:{self.type}:{self.value}"


def _as_int(value: Any) -> int:
    if isinstance(value, bool):
        return 1 if value else 0
    return int(value)


class RdpFile:
    """一个 .rdp 文件。保留行顺序，未知键原样往返。"""

    def __init__(self, entries: list[Entry] | None = None) -> None:
        self.entries: list[Entry] = entries or []

    # ---------- 读取 ----------

    @classmethod
    def loads(cls, text: str) -> "RdpFile":
        # 去掉 UTF-8 BOM（mstsc 有时会写）
        if text.startswith("\ufeff"):
            text = text[1:]

        entries: list[Entry] = []
        seen: set[str] = set()
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            parts = line.split(":", 2)
            if len(parts) < 3 or parts[1] not in ("i", "s"):
                # 无法识别的行（注释、空行、损坏行）——保留以便往返
                entries.append(Entry(key=line, type=None))
                continue
            key, typ, value = parts[0].strip(), parts[1], parts[2]
            if key in seen:
                # 重复键：后面的覆盖前面的（与 FreeRDP 一致）
                for i, e in enumerate(entries):
                    if e.key == key:
                        entries[i] = Entry(key, typ, value)
                        break
                continue
            seen.add(key)
            entries.append(Entry(key=key, type=typ, value=value))
        return cls(entries)

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "RdpFile":
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return cls.loads(fh.read())

    # ---------- 写出 ----------

    def dumps(self) -> str:
        return "\n".join(e.render() for e in self.entries) + "\n"

    def save(self, path: str | os.PathLike[str]) -> None:
        path = os.fspath(path)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(self.dumps())
        os.replace(tmp, path)

    # ---------- 访问 ----------

    def _find(self, key: str) -> Entry | None:
        for e in self.entries:
            if e.key == key and e.type is not None:
                return e
        return None

    def has(self, key: str) -> bool:
        return self._find(key) is not None

    def raw(self, key: str) -> str | None:
        e = self._find(key)
        return e.value if e else None

    def get_str(self, key: str, default: str = "") -> str:
        e = self._find(key)
        return e.value if e else default

    def get_int(self, key: str, default: int = 0) -> int:
        e = self._find(key)
        if e is None:
            return default
        try:
            return int(e.value.strip())
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        e = self._find(key)
        if e is None:
            return default
        try:
            return int(e.value.strip()) != 0
        except ValueError:
            return default

    def set(self, key: str, value: Any) -> None:
        """按 Python 值类型推断 ``:i:`` / ``:s:``。"""
        if isinstance(value, bool):
            typ, text = "i", "1" if value else "0"
        elif isinstance(value, int):
            typ, text = "i", str(value)
        else:
            typ, text = "s", str(value)

        e = self._find(key)
        if e is not None:
            e.type, e.value = typ, text
            return
        self.entries.append(Entry(key=key, type=typ, value=text))

    def unset(self, key: str) -> None:
        self.entries = [e for e in self.entries if e.key != key]

    # ---------- 便利 ----------

    def keys(self) -> Iterator[str]:
        for e in self.entries:
            if e.type is not None:
                yield e.key

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for e in self.entries:
            if e.type is None:
                continue
            if e.is_int:
                try:
                    out[e.key] = int(e.value)
                    continue
                except ValueError:
                    pass
            out[e.key] = e.value
        return out

    def gui_dict(self) -> dict[str, str]:
        """取出所有 ``gui_`` 前缀的自定义键。"""
        return {k: self.get_str(k) for k in self.keys() if k.startswith(GUI_PREFIX)}

    def copy(self) -> "RdpFile":
        return RdpFile([Entry(e.key, e.type, e.value) for e in self.entries])

    def __contains__(self, key: str) -> bool:
        return self.has(key)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RdpFile {len(list(self.keys()))} keys>"
