#!/usr/bin/env python3
"""无头 QML 检查：加载 Main.qml 并断言 **0 条 QML 警告**。

为什么以「0 警告」为准：字段渲染失败的所有已知形态都会产生警告 ——
  * fld 未注入            -> 12 行 × TypeError（每种 8 次）
  * Repeater 反复重建     -> 旧 delegate 销毁后绑定求值报错
  * 独立组件未声明 required property -> ReferenceError: index is not defined
所以 0 警告是比「数控件个数」更可靠的回归守卫（findChildren 穿不透 Repeater
的 delegate，而 objectCreated 不覆盖组件内部对象）。
"""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from pathlib import Path

# 禁止产生 core dump —— 万一又踩到 QML 崩溃，不要往磁盘写几百 MB
ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True).prctl(4, 0, 0, 0, 0)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Fusion")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QUrl  # noqa: E402
from PyQt6.QtGui import QGuiApplication  # noqa: E402
from PyQt6.QtQml import QQmlApplicationEngine  # noqa: E402

from app import Bridge  # noqa: E402
from core import profiles, schema  # noqa: E402


def main() -> int:
    profiles.ensure_dirs()
    app = QGuiApplication(sys.argv[:1])

    engine = QQmlApplicationEngine()
    warnings: list[str] = []

    def on_warnings(list_) -> None:
        # 这个信号的参数是 QList<QQmlError>（Python list）。
        # 写成 lambda w: w.toString() 会抛 AttributeError，被 PyQt6 升级成 abort。
        for err in list_:
            warnings.append(err.toString())

    engine.warnings.connect(on_warnings)

    bridge = Bridge()
    engine.rootContext().setContextProperty("bridge", bridge)
    engine.load(QUrl.fromLocalFile(str(ROOT / "ui" / "Main.qml")))

    if not engine.rootObjects():
        print("FAIL: QML 未加载")
        for w in warnings:
            print("  -", w)
        return 1

    print(f"Main.qml 已加载; schema {len(schema.GROUPS)} 组 / {len(schema.FIELDS)} 字段")
    print(f"QML 警告: {len(warnings)}")
    for w in warnings[:15]:
        print("  -", w)
    print("\n结果:", "通过 ✓" if not warnings else "失败 ✗")

    engine = None
    bridge = None
    return 0 if not warnings else 1


if __name__ == "__main__":
    sys.exit(main())
