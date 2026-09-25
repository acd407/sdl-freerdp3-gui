"""extraargs — ``gui_extra_args`` 里命令行 token 的读写。

为什么需要这一层
----------------
FreeRDP 的 103 个 ``.rdp`` 键里**没有任何安全层 / 证书相关的键**，所以
``/sec:tls``、``/cert:ignore`` 这类只能放在自定义键 ``gui_extra_args`` 里
（FreeRDP 会静默忽略未知键，实测）。

GUI 把其中常用的几项做成了下拉框，因此需要一个「只替换某一个 token、其余
原样保留」的工具——不能用 shlex.split + shlex.join，那会重排引号、破坏用户
手写的格式。
"""

from __future__ import annotations

import re

__all__ = ["get_token", "set_token", "has_token", "SECURITY_OPTIONS", "SECURITY_PREFIX"]

SECURITY_PREFIX = "/sec:"

# (下拉索引, 显示文本, 要写入的 token)  —— token 为空表示「不指定」
SECURITY_OPTIONS: tuple[tuple[int, str, str], ...] = (
    (0, "自动协商（不指定 /sec:）", ""),
    (1, "仅 TLS", "/sec:tls"),
    (2, "仅 NLA", "/sec:nla"),
    (3, "NLA + 扩展安全", "/sec:nla,ext"),
    (4, "仅 RDP", "/sec:rdp"),
)


def _pattern(prefix: str) -> re.Pattern[str]:
    # token 前必须是字符串开头或空白，避免误伤 /cert:ignore 之类里的片段
    return re.compile(r"(?<!\S)" + re.escape(prefix) + r"\S*")


def has_token(args: str, prefix: str) -> bool:
    return bool(args) and _pattern(prefix).search(args) is not None


def get_token(args: str, prefix: str) -> str | None:
    """取出第一个 ``prefix...`` token，取不到返回 None。"""
    if not args:
        return None
    m = _pattern(prefix).search(args)
    return m.group(0) if m else None


def set_token(args: str, prefix: str, value: str | None) -> str:
    """替换（或删除/追加）指定前缀的 token，其余内容与空白原样保留。"""
    args = args or ""
    pat = _pattern(prefix)
    exists = pat.search(args) is not None

    if value is None or value == "":
        out = pat.sub("", args)
        return re.sub(r"\s{2,}", " ", out).strip()

    if exists:
        return pat.sub(value, args, count=1).strip()
    return (args.rstrip() + " " + value).strip() if args.strip() else value


def security_index(args: str) -> int:
    """从 ``gui_extra_args`` 反推下拉框应选中哪一项。"""
    tok = get_token(args, SECURITY_PREFIX)
    if tok is None:
        return 0
    for idx, _label, value in SECURITY_OPTIONS:
        if value and value == tok:
            return idx
    return 0  # 无法识别的手写值：显示为「自动协商」，不动它直到用户主动改


def security_token(index: int) -> str:
    for idx, _label, value in SECURITY_OPTIONS:
        if idx == index:
            return value
    return ""
