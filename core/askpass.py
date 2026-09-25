#!/usr/bin/env python3
"""askpass — 供 ``sdl-freerdp3`` 通过 ``FREERDP_ASKPASS`` 调用的密码提供程序。

FreeRDP 的调用约定（见 ``libfreerdp/utils/passphrase.c``）::

    FREERDP_ASKPASS "<prompt>"        # prompt 是 FreeRDP 追加的第一个参数

它对 ``FREERDP_ASKPASS`` 的值执行 ``popen``，读取 **stdout 第一行**作为密码；
退出码非 0 或没有输出时，会回退到自带的凭据窗口。

本脚本：

* 忽略 argv（FreeRDP 塞进来的提示语）
* 从环境变量 ``SFLGUI_SECRET_ATTRS``（JSON）拿到要查的属性集合
* 去系统钥匙串取密码，打印到 stdout，退出 0
* 查不到 / 出错则退出 1，让 FreeRDP 回退 GUI

它不接收也不打印任何参数以外的秘密；密码只经过进程 stdout。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 允许以绝对路径被调用（cwd 任意），同时能用 core.secrets
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    raw = os.environ.get("SFLGUI_SECRET_ATTRS", "")
    if not raw:
        return 1
    try:
        attrs = json.loads(raw)
    except ValueError:
        return 1
    if not isinstance(attrs, dict) or not attrs:
        return 1

    # 延迟导入，且吞掉任何异常：helper 崩溃只会让 FreeRDP 回退弹窗，不应打印堆栈
    try:
        from core.secrets import get_backend

        pw = get_backend().get(attrs)
    except Exception:  # noqa: BLE001 - 任何异常都视为「取不到」
        return 1

    if not pw:
        return 1
    sys.stdout.write(pw + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
