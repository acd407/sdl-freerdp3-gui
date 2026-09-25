#!/usr/bin/env python3
"""审计 schema 的默认值是否正确。

问题
----
`AppController._collect()` 只把「与 absent 不同」的字段写进 .rdp。这要求
**schema 默认值 == FreeRDP 在该键缺失时的实际行为**。只要两者不同，用户选择
「默认值」时那个键就会被跳过，行为随之改变（例如 audiomode：键缺失 = 音频全关，
而 schema 默认写的是 0 = 本机播放）。

方法
----
对每个字段比较两份配置的 settings dump：
  A) 只有 full address
  B) 只有 full address + 该字段被设成它的默认值
若两份在某些 setting 上不同（尤其是该字段自己驱动的那些），说明默认值不成立。
"""

from __future__ import annotations

import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

from probeutil import dump_text  # noqa: E402

from core import schema  # noqa: E402
from core.keymap import KEY_SETTINGS  # noqa: E402

BASE = "full address:s:10.0.0.1\n"

# 「无值」的两种表示法语义相同：
#   写入 key:s:（空串） -> setting == ""
#   完全省略该键        -> setting == NULL
# 对主机名/路径这类可选项，两者都表示「未设置」。
NULLISH = {"", "<null>"}

# 已确认无害的差异，附理由（改这里必须写清楚为什么）
BENIGN: dict[str, str] = {
    "dynamic resolution": (
        "写成 :i:0 会顺带把 SupportDisplayControl 置 FALSE，省略则保持默认 TRUE。"
        "两种情况下 DynamicResolutionUpdate 都是 FALSE（即动态分辨率确实关闭），"
        "用户可见行为一致。"
    ),
}

# 基线锚点，不做审计：它本身就在 BASE 里，再追加一次空值测的是「重复键取哪个」，
# 不是「键缺失 vs 键存在」。真实使用中它永远非空且必定写入。
SKIP = {"full address"}

# 这些 setting 会随 connection type 一起变，属于基线噪声
CONN_NOISE = {
    "FreeRDP_SupportGraphicsPipeline",
    "FreeRDP_RemoteFxCodec",
    "FreeRDP_GfxH264",
    "FreeRDP_GfxAVC444",
    "FreeRDP_GfxAVC444v2",
    "FreeRDP_AllowDesktopComposition",
    "FreeRDP_DisableFullWindowDrag",
    "FreeRDP_DisableMenuAnims",
    "FreeRDP_ConnectionType",
}


def main() -> int:
    base = dump_text(BASE)
    if base is None:
        raise SystemExit("基线解析失败")

    mismatched: list[tuple[str, str, list[str]]] = []
    for f in schema.FIELDS:
        if f.key in schema.VIRTUAL_KEYS or f.key in SKIP:
            continue
        raw = schema.ui_to_file(f, f.default)
        typ = "i" if isinstance(raw, bool) or isinstance(raw, int) else "s"
        text = BASE + f"{f.key}:{typ}:{1 if raw is True else 0 if raw is False else raw}\n"
        got = dump_text(text)
        if got is None:
            mismatched.append((f.key, "PARSE-FAIL", []))
            continue

        # _collect() 会不会写出这一项？
        will_write = (
            not (f.widget == schema.WIDGET_TEXT and not str(f.default).strip())
            and f.default != f.absent_value
        )
        if will_write:
            continue  # 会写进文件，行为必然正确

        # 不写：必须验证「省略」等价于「写入默认值」
        diff = [
            n
            for n, v in got.items()
            if base.get(n) != v
            and n not in CONN_NOISE
            and {str(base.get(n, "")), str(v)} - NULLISH
        ]
        if diff and f.key in BENIGN:
            print(f"已知无害: {f.key} — {BENIGN[f.key]}")
            diff = []
        if diff:
            mismatched.append((f.key, str(f.default), diff))
            print(f"BUG: {f.key:32s} default={str(f.default):8s} "
                  f"省略后行为不同 -> {', '.join(diff)}")

    checked = len(schema.FIELDS) - len(schema.VIRTUAL_KEYS) - len(SKIP)
    print(f"\n共检查 {checked} 个字段，"
          f"{len(mismatched)} 个默认值不等价于「键缺失」")
    return 1 if mismatched else 0


if __name__ == "__main__":
    sys.exit(main())
