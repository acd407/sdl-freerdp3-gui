#!/usr/bin/env python3
"""从 FreeRDP 自身生成 core/keymap.py。

原理
----
`probe.c` 链接本机 FreeRDP 的头/库，解析一个 .rdp 文件后把**全部 settings**
dump 出来。本脚本对 100 个 .rdp 键逐个取值后与基线对比，得出：

* 该键解析为 int 还是 string
* 它实际驱动了哪些 FreeRDP settings
* 哪些键在 FreeRDP 里是死键（无任何 effect）

这比手抄文档可靠，因为它是从**本机这个版本的 FreeRDP** 实测出来的。
换 FreeRDP 版本后重跑即可更新。

用法:  python3 tools/genschema.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
KEYS_FILE = os.path.join(HERE, "keys.txt")

BASE_LINE = "full address:s:10.0.0.1\n"
CANDIDATE_VALUES = [("i", "0"), ("i", "1"), ("i", "2"), ("i", "3"), ("i", "5"), ("s", "ZZTEST")]

sys.path.insert(0, HERE)
from probeutil import dump_file as dump  # noqa: E402
from probeutil import dump_text  # noqa: E402


def main() -> None:
    keys = [k.strip() for k in open(KEYS_FILE, encoding="utf-8") if k.strip()]

    ref = dump_text(BASE_LINE)
    if ref is None:
        raise SystemExit("基线解析失败")
    print(f"[genschema] 基线 settings: {len(ref)}", file=sys.stderr)

    result: dict[str, dict] = {}
    for key in keys:
        hits: dict[str, dict] = {}
        for typ, val in CANDIDATE_VALUES:
            got = dump_text(BASE_LINE + f"{key}:{typ}:{val}\n")
            if got is None:
                continue
            diff = {n: [ref.get(n), v] for n, v in got.items() if ref.get(n) != v}
            if diff:
                hits[f"{typ}:{val}"] = diff
        result[key] = hits

    # 写出 Python 模块
    lines = [
        '"""自动生成 —— 请勿手工编辑。来源: tools/genschema.py（实测本机 FreeRDP）。"""',
        "",
        "# .rdp 键 -> 解析类型 ('i' / 's')。None 表示探针未能定出类型。",
        "KEY_TYPE: dict[str, str | None] = {",
    ]
    for key, hits in result.items():
        typ = None
        for tag in hits:
            typ = tag.split(":", 1)[0]
            break
        lines.append(f"    {key!r}: {typ!r},")
    lines.append("}")
    lines.append("")
    lines.append("# .rdp 键 -> 它驱动的 FreeRDP settings 名列表（死键为空列表）")
    lines.append("KEY_SETTINGS: dict[str, list[str]] = {")
    for key, hits in result.items():
        names: list[str] = []
        for diff in hits.values():
            for n in diff:
                if n not in names:
                    names.append(n)
        lines.append(f"    {key!r}: {names!r},")
    lines.append("}")
    lines.append("")
    lines.append("# 需要特定取值才生效的键 -> 该取值")
    lines.append("KEY_NEEDS_VALUE: dict[str, str] = {")
    for key, hits in result.items():
        if not hits:
            continue
        tags = sorted(hits)
        lines.append(f"    {key!r}: {tags[0]!r},")
    lines.append("}")
    lines.append("")
    dead = [k for k, v in result.items() if not v]
    lines.append(f"# 在 FreeRDP 中无任何 effect 的键（{len(dead)} 个）")
    lines.append("DEAD_KEYS: list[str] = " + repr(sorted(dead)))
    lines.append("")

    out = os.path.join(ROOT, "core", "keymap.py")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"[genschema] 写出 {out}: 有效 {len(keys) - len(dead)} / {len(keys)}", file=sys.stderr)


if __name__ == "__main__":
    main()
